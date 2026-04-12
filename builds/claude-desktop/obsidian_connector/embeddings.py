"""Local embedding generation and similarity search for obsidian-connector.

Provides optional semantic search via sentence-transformers. Falls back
gracefully when sentence-transformers is not installed -- retrieval.py
skips semantic scoring entirely in that case.

This module never writes to vault files.
"""

from __future__ import annotations

import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional dependency: sentence-transformers (and numpy via it)
# ---------------------------------------------------------------------------

_ST_AVAILABLE = False
_SentenceTransformer: Any = None
_np: Any = None

try:
    from sentence_transformers import SentenceTransformer as _ST  # type: ignore[import-untyped]
    import numpy as _numpy  # type: ignore[import-untyped]

    _SentenceTransformer = _ST
    _np = _numpy
    _ST_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# SQLite schema for embeddings
# ---------------------------------------------------------------------------

_EMBEDDINGS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS embeddings (
    note_path TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

_SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules"}


# ---------------------------------------------------------------------------
# Cosine similarity (pure Python fallback + numpy fast path)
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Uses numpy when available for speed, falls back to pure Python.

    Parameters
    ----------
    a, b:
        Equal-length numeric vectors.

    Returns
    -------
    float
        Cosine similarity in [-1, 1].  Returns 0.0 if either vector
        has zero magnitude.
    """
    if _np is not None:
        va = _np.asarray(a, dtype=_np.float32)
        vb = _np.asarray(b, dtype=_np.float32)
        dot = float(_np.dot(va, vb))
        norm_a = float(_np.linalg.norm(va))
        norm_b = float(_np.linalg.norm(vb))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    # Pure Python fallback.
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# EmbeddingsIndex
# ---------------------------------------------------------------------------

class EmbeddingsIndex:
    """Local embedding index backed by SQLite.

    Stores embedding vectors for vault notes and provides similarity
    search.  Requires ``sentence-transformers`` and ``numpy`` to be
    installed -- all methods that need them raise ``ImportError`` with
    a helpful message when the packages are missing.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Can share a database with
        :class:`~obsidian_connector.index_store.IndexStore` or use a
        separate file.  Defaults to
        ``~/.obsidian-connector/embeddings.sqlite``.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".obsidian-connector" / "embeddings.sqlite"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._model: Any = None
        self._model_name: str = ""

    # -- Connection management -----------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open (or reuse) a SQLite connection with WAL mode."""
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(_EMBEDDINGS_SCHEMA)
        conn.commit()
        self._conn = conn
        return conn

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- Availability check --------------------------------------------------

    @staticmethod
    def is_available() -> bool:
        """Return ``True`` if sentence-transformers is installed."""
        return _ST_AVAILABLE

    # -- Model loading -------------------------------------------------------

    def _load_model(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Load the sentence-transformers model (lazy, cached)."""
        if not _ST_AVAILABLE:
            raise ImportError(
                "sentence-transformers is required for embedding generation. "
                "Install it with: pip install 'sentence-transformers>=3.0,<4.0'"
            )
        if self._model is None or self._model_name != model_name:
            self._model = _SentenceTransformer(model_name)
            self._model_name = model_name

    # -- Public API ----------------------------------------------------------

    def embed_text(self, text: str, model_name: str = "all-MiniLM-L6-v2") -> list[float]:
        """Generate an embedding vector for the given text.

        Parameters
        ----------
        text:
            Input text to embed.
        model_name:
            Sentence-transformers model name.

        Returns
        -------
        list[float]
            Embedding vector.

        Raises
        ------
        ImportError
            If sentence-transformers is not installed.
        """
        self._load_model(model_name)
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def build(
        self,
        vault_path: str | Path,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> int:
        """Generate embeddings for all ``.md`` files in a vault.

        Parameters
        ----------
        vault_path:
            Absolute path to the vault directory.
        model_name:
            Sentence-transformers model name.

        Returns
        -------
        int
            Number of notes embedded.

        Raises
        ------
        ImportError
            If sentence-transformers is not installed.
        """
        if not _ST_AVAILABLE:
            raise ImportError(
                "sentence-transformers is required for building the embedding index. "
                "Install it with: pip install 'sentence-transformers>=3.0,<4.0'"
            )

        self._load_model(model_name)
        root = Path(vault_path)
        conn = self._connect()
        count = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if not fname.endswith(".md"):
                    continue
                full = Path(dirpath) / fname
                rel = full.relative_to(root).as_posix()
                try:
                    content = full.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                embedding = self._model.encode(content, convert_to_numpy=True)
                blob = embedding.tobytes()

                conn.execute(
                    "INSERT OR REPLACE INTO embeddings "
                    "(note_path, embedding, model, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (rel, blob, model_name, time.time()),
                )
                count += 1

        conn.commit()
        return count

    def update(self, file_path: str, content: str, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Update the embedding for a single file.

        Parameters
        ----------
        file_path:
            Vault-relative path of the note.
        content:
            Full text content of the note.
        model_name:
            Sentence-transformers model name.

        Raises
        ------
        ImportError
            If sentence-transformers is not installed.
        """
        self._load_model(model_name)
        conn = self._connect()
        embedding = self._model.encode(content, convert_to_numpy=True)
        blob = embedding.tobytes()
        conn.execute(
            "INSERT OR REPLACE INTO embeddings "
            "(note_path, embedding, model, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (file_path, blob, model_name, time.time()),
        )
        conn.commit()

    def remove(self, file_path: str) -> None:
        """Remove the embedding for a deleted file.

        Parameters
        ----------
        file_path:
            Vault-relative path of the note.
        """
        conn = self._connect()
        conn.execute("DELETE FROM embeddings WHERE note_path = ?", (file_path,))
        conn.commit()

    def similar(
        self,
        query_text: str,
        top_k: int = 20,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> list[tuple[str, float]]:
        """Find notes most similar to the query text.

        Parameters
        ----------
        query_text:
            Text to compare against stored embeddings.
        top_k:
            Maximum number of results to return.
        model_name:
            Sentence-transformers model name.

        Returns
        -------
        list[tuple[str, float]]
            List of ``(note_path, similarity_score)`` sorted by
            descending similarity.

        Raises
        ------
        ImportError
            If sentence-transformers is not installed.
        """
        if not _ST_AVAILABLE:
            raise ImportError(
                "sentence-transformers is required for semantic similarity search. "
                "Install it with: pip install 'sentence-transformers>=3.0,<4.0'"
            )

        self._load_model(model_name)
        conn = self._connect()

        query_embedding = self._model.encode(query_text, convert_to_numpy=True)
        query_list = query_embedding.tolist()

        rows = conn.execute("SELECT note_path, embedding FROM embeddings").fetchall()
        if not rows:
            return []

        scored: list[tuple[str, float]] = []
        for note_path, blob in rows:
            stored = _np.frombuffer(blob, dtype=_np.float32).tolist()
            sim = _cosine_similarity(query_list, stored)
            scored.append((note_path, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
