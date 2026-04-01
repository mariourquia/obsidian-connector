"""Unified hybrid retrieval engine for obsidian-connector.

Combines multiple scoring signals -- lexical, semantic, graph, and
recency -- into a single ranked result list.  Supports retrieval
profiles that re-weight signals for different use cases (journal,
project, research, review).

Semantic scoring requires ``sentence-transformers`` (optional).
When unavailable, the engine degrades gracefully to lexical + graph +
recency only.

This module never writes to vault files.
"""

from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from obsidian_connector.graph import NoteIndex, extract_tags


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """A single search result with scoring breakdown."""

    path: str
    title: str
    score: float
    match_reasons: list[str] = field(default_factory=list)
    snippet: str = ""


# ---------------------------------------------------------------------------
# Retrieval profiles -- signal weight overrides
# ---------------------------------------------------------------------------

PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
    "journal": {"lexical": 0.3, "semantic": 0.1, "graph": 0.1, "recency": 0.5},
    "project": {"lexical": 0.2, "semantic": 0.2, "graph": 0.4, "recency": 0.2},
    "research": {"lexical": 0.2, "semantic": 0.5, "graph": 0.2, "recency": 0.1},
    "review": {"lexical": 0.25, "semantic": 0.25, "graph": 0.25, "recency": 0.25},
    "default": {"lexical": 0.4, "semantic": 0.2, "graph": 0.2, "recency": 0.2},
}


# ---------------------------------------------------------------------------
# Recency decay constant
# ---------------------------------------------------------------------------

_RECENCY_HALF_LIFE_SECONDS = 7 * 24 * 60 * 60  # 7 days in seconds


# ---------------------------------------------------------------------------
# BM25-style constants
# ---------------------------------------------------------------------------

_BM25_K1 = 1.2
_BM25_B = 0.75
_TITLE_BOOST = 2.0


# ---------------------------------------------------------------------------
# Internal scoring helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Split text into lowercase alphanumeric tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _lexical_score(query: str, content: str, title: str) -> float:
    """BM25-inspired lexical scoring with title boost.

    Computes a simplified BM25 score for each query term against the
    document content, with title matches receiving a 2x boost.

    Parameters
    ----------
    query:
        Raw query string.
    content:
        Full text content of the note.
    title:
        Note title (filename without .md).

    Returns
    -------
    float
        Score in [0, 1].  Returns 0.0 when no query terms match.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0

    content_tokens = _tokenize(content)
    title_tokens = _tokenize(title)

    if not content_tokens:
        return 0.0

    # Term frequency in content.
    tf_map: dict[str, int] = {}
    for t in content_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1

    # Term frequency in title.
    title_tf_map: dict[str, int] = {}
    for t in title_tokens:
        title_tf_map[t] = title_tf_map.get(t, 0) + 1

    doc_len = len(content_tokens)
    # Assume average doc length ~ current doc for single-doc scoring.
    avg_dl = max(doc_len, 1)

    total_score = 0.0
    matched_terms = 0

    for term in query_tokens:
        tf = tf_map.get(term, 0)
        title_tf = title_tf_map.get(term, 0)

        if tf == 0 and title_tf == 0:
            continue

        matched_terms += 1

        # BM25 TF component for content.
        bm25_tf = (tf * (_BM25_K1 + 1)) / (
            tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * (doc_len / avg_dl))
        )
        total_score += bm25_tf

        # Title boost.
        if title_tf > 0:
            total_score += _TITLE_BOOST

    if matched_terms == 0:
        return 0.0

    # Normalize: divide by the number of query terms to keep score
    # proportional regardless of query length.  Then clamp to [0, 1].
    normalized = total_score / len(query_tokens)
    # BM25 TF maxes around K1+1 = 2.2, plus title boost = 2.0, so
    # max per term is ~4.2.  Divide by ~4.2 to normalize to [0, 1].
    max_per_term = (_BM25_K1 + 1) + _TITLE_BOOST
    return min(1.0, normalized / max_per_term)


def _semantic_score(
    query: str,
    note_path: str,
    embeddings_index: Any | None,
) -> float:
    """Compute semantic similarity using embeddings.

    Parameters
    ----------
    query:
        Raw query string.
    note_path:
        Vault-relative path of the note.
    embeddings_index:
        An :class:`~obsidian_connector.embeddings.EmbeddingsIndex`
        instance, or ``None`` if embeddings are unavailable.

    Returns
    -------
    float
        Cosine similarity score in [0, 1], or 0.0 if embeddings are
        unavailable.
    """
    if embeddings_index is None:
        return 0.0

    try:
        if not embeddings_index.is_available():
            return 0.0
    except Exception:
        return 0.0

    try:
        results = embeddings_index.similar(query)
        for path, sim in results:
            if path == note_path:
                return max(0.0, min(1.0, sim))
    except (ImportError, Exception):
        pass

    return 0.0


def _graph_score(note_path: str, index: NoteIndex | None) -> float:
    """Compute graph-based score from backlink count and tag diversity.

    Parameters
    ----------
    note_path:
        Vault-relative path of the note.
    index:
        A populated :class:`~obsidian_connector.graph.NoteIndex`, or
        ``None``.

    Returns
    -------
    float
        Score in [0, 1].  Combines normalized backlink count (70%) and
        tag diversity bonus (30%).
    """
    if index is None:
        return 0.0

    # Backlink score: note's backlink count / max backlink count.
    backlinks = index.backlinks.get(note_path, set())
    bl_count = len(backlinks)

    max_bl = 0
    for bl_set in index.backlinks.values():
        count = len(bl_set)
        if count > max_bl:
            max_bl = count

    bl_score = bl_count / max_bl if max_bl > 0 else 0.0

    # Tag diversity bonus: number of distinct tags / max tags across notes.
    entry = index.notes.get(note_path)
    if entry is None:
        return bl_score * 0.7

    tag_count = len(entry.tags)
    max_tags = 0
    for e in index.notes.values():
        t = len(e.tags)
        if t > max_tags:
            max_tags = t

    tag_score = tag_count / max_tags if max_tags > 0 else 0.0

    return bl_score * 0.7 + tag_score * 0.3


def _recency_score(mtime: float, now: float | None = None) -> float:
    """Compute recency score using exponential decay.

    Uses a half-life of 7 days: a note modified 7 days ago scores 0.5,
    a note modified 14 days ago scores 0.25, etc.

    Parameters
    ----------
    mtime:
        File modification time (epoch seconds).
    now:
        Current time (epoch seconds).  Uses ``time.time()`` if ``None``.

    Returns
    -------
    float
        Score in [0, 1].  1.0 for just-modified files, decaying
        exponentially.
    """
    if now is None:
        now = time.time()
    age = max(0.0, now - mtime)
    # Exponential decay: score = 2^(-age / half_life) = e^(-age * ln2 / half_life)
    decay = math.log(2) / _RECENCY_HALF_LIFE_SECONDS
    return math.exp(-decay * age)


def _merge_scores(
    scores_dict: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Compute weighted sum of signal scores, normalized to [0, 1].

    Parameters
    ----------
    scores_dict:
        Mapping of signal name to raw score (each in [0, 1]).
    weights:
        Mapping of signal name to weight.

    Returns
    -------
    float
        Weighted sum.  If all weights are zero, returns 0.0.
    """
    total_weight = sum(weights.get(k, 0.0) for k in scores_dict)
    if total_weight == 0.0:
        return 0.0

    weighted_sum = sum(
        scores_dict.get(k, 0.0) * weights.get(k, 0.0) for k in scores_dict
    )
    return min(1.0, weighted_sum / total_weight) * total_weight


def _explain_scores(
    scores_dict: dict[str, float],
    weights: dict[str, float],
) -> list[str]:
    """Generate human-readable match reason strings.

    Parameters
    ----------
    scores_dict:
        Mapping of signal name to raw score.
    weights:
        Mapping of signal name to weight.

    Returns
    -------
    list[str]
        One explanation string per non-zero signal.
    """
    reasons: list[str] = []

    signal_labels = {
        "lexical": "keyword match",
        "semantic": "semantic similarity",
        "graph": "graph connectivity",
        "recency": "recency",
    }

    for signal, label in signal_labels.items():
        raw = scores_dict.get(signal, 0.0)
        weight = weights.get(signal, 0.0)
        if raw > 0.001 and weight > 0.001:
            weighted = raw * weight
            reasons.append(
                f"{label}: {raw:.2f} (weight {weight:.0%}, contribution {weighted:.3f})"
            )

    return reasons


def _extract_snippet(content: str, query: str, max_len: int = 200) -> str:
    """Extract a relevant snippet from content around the first query match.

    Parameters
    ----------
    content:
        Full note text.
    query:
        Query string.
    max_len:
        Maximum snippet length.

    Returns
    -------
    str
        Snippet text, or the first ``max_len`` characters if no match.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return content[:max_len]

    lower_content = content.lower()
    best_pos = -1

    for token in query_tokens:
        pos = lower_content.find(token)
        if pos >= 0:
            best_pos = pos
            break

    if best_pos < 0:
        return content[:max_len]

    # Center snippet around the match.
    start = max(0, best_pos - max_len // 4)
    end = min(len(content), start + max_len)
    snippet = content[start:end].strip()

    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    return snippet


# ---------------------------------------------------------------------------
# Main retrieval function
# ---------------------------------------------------------------------------

_SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules"}


def hybrid_search(
    query: str,
    vault_path: str | Path,
    index_store: Any | None = None,
    profile: str = "default",
    top_k: int = 10,
    explain: bool = False,
    embeddings_index: Any | None = None,
    note_index: NoteIndex | None = None,
) -> list[SearchResult]:
    """Run hybrid retrieval across all vault notes.

    Combines lexical (BM25-style), semantic (embedding similarity),
    graph (backlink density), and recency (mtime decay) signals with
    weights determined by the retrieval profile.

    Parameters
    ----------
    query:
        Search query string.
    vault_path:
        Absolute path to the vault directory.
    index_store:
        Optional :class:`~obsidian_connector.index_store.IndexStore`.
        Used to load the NoteIndex if ``note_index`` is not provided.
    profile:
        Retrieval profile name (``journal``, ``project``, ``research``,
        ``review``, or ``default``).
    top_k:
        Maximum number of results to return.
    explain:
        If ``True``, populate ``match_reasons`` on each result.
    embeddings_index:
        Optional :class:`~obsidian_connector.embeddings.EmbeddingsIndex`.
    note_index:
        Optional pre-built :class:`~obsidian_connector.graph.NoteIndex`.
        If ``None``, loaded from ``index_store`` or built from disk.

    Returns
    -------
    list[SearchResult]
        Ranked results sorted by combined score (descending).
        Empty list if the query is empty.
    """
    query = query.strip()
    if not query:
        return []

    root = Path(vault_path)
    weights = PROFILE_WEIGHTS.get(profile, PROFILE_WEIGHTS["default"])

    # Load or build the NoteIndex.
    idx = note_index
    if idx is None and index_store is not None:
        try:
            idx = index_store.get_index()
        except Exception:
            idx = None

    # Scan vault files for content.
    note_data: dict[str, dict[str, Any]] = {}
    now = time.time()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            full = Path(dirpath) / fname
            rel = full.relative_to(root).as_posix()
            title = fname[:-3]

            try:
                stat = full.stat()
                content = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            note_data[rel] = {
                "title": title,
                "content": content,
                "mtime": stat.st_mtime,
            }

    if not note_data:
        return []

    # Score each note.
    scored: list[SearchResult] = []
    seen_paths: set[str] = set()

    for rel, data in note_data.items():
        if rel in seen_paths:
            continue
        seen_paths.add(rel)

        title = data["title"]
        content = data["content"]
        mtime = data["mtime"]

        signals: dict[str, float] = {
            "lexical": _lexical_score(query, content, title),
            "semantic": _semantic_score(query, rel, embeddings_index),
            "graph": _graph_score(rel, idx),
            "recency": _recency_score(mtime, now),
        }

        combined = _merge_scores(signals, weights)

        # Skip notes with zero combined score.
        if combined <= 0.0:
            continue

        match_reasons: list[str] = []
        if explain:
            match_reasons = _explain_scores(signals, weights)

        snippet = _extract_snippet(content, query)

        scored.append(
            SearchResult(
                path=rel,
                title=title,
                score=combined,
                match_reasons=match_reasons,
                snippet=snippet,
            )
        )

    # Sort by score descending.
    scored.sort(key=lambda r: r.score, reverse=True)

    # Limit to top_k.
    return scored[:top_k]
