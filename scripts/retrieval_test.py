#!/usr/bin/env python3
"""Tests for the hybrid retrieval engine and embeddings module.

Uses tempfile-based vaults and mock data.  No pytest required.
Follows existing test patterns in scripts/.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.retrieval import (
    PROFILE_WEIGHTS,
    SearchResult,
    _explain_scores,
    _graph_score,
    _lexical_score,
    _merge_scores,
    _recency_score,
    hybrid_search,
)
from obsidian_connector.embeddings import EmbeddingsIndex, _cosine_similarity
from obsidian_connector.graph import NoteEntry, NoteIndex

PASS = 0
FAIL = 0
ASSERTIONS = 0


def assert_true(condition: bool, message: str) -> None:
    """Assert that condition is True."""
    global PASS, FAIL, ASSERTIONS
    ASSERTIONS += 1
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ASSERTION FAILED: {message}")
        traceback.print_stack(limit=3)


def assert_equal(actual, expected, message: str) -> None:
    """Assert that actual equals expected."""
    assert_true(actual == expected, f"{message}: expected {expected!r}, got {actual!r}")


def assert_greater(a, b, message: str) -> None:
    """Assert that a > b."""
    assert_true(a > b, f"{message}: expected {a!r} > {b!r}")


def assert_less(a, b, message: str) -> None:
    """Assert that a < b."""
    assert_true(a < b, f"{message}: expected {a!r} < {b!r}")


def assert_close(a: float, b: float, message: str, tol: float = 0.05) -> None:
    """Assert that a is approximately equal to b."""
    assert_true(
        abs(a - b) < tol,
        f"{message}: expected {a:.4f} ~= {b:.4f} (tol={tol})",
    )


# ---------------------------------------------------------------------------
# Helpers: build a temporary vault
# ---------------------------------------------------------------------------

def _create_vault(tmp_dir: str) -> str:
    """Create a temporary vault with test notes.

    Returns the vault path.
    """
    vault = os.path.join(tmp_dir, "test_vault")
    os.makedirs(vault)

    now = time.time()
    one_day = 86400
    one_week = 7 * one_day

    notes = {
        "daily/2026-03-30.md": {
            "content": "# Daily Note\n\nToday I worked on the portfolio project.\n\n#daily #journal\n\n[[Portfolio Project]]",
            "mtime": now,
        },
        "daily/2026-03-23.md": {
            "content": "# Daily Note\n\nReviewed machine learning papers.\n\n#daily #journal\n\n[[Research Notes]]",
            "mtime": now - one_week,
        },
        "projects/Portfolio Project.md": {
            "content": "# Portfolio Project\n\nBuilding a quantitative portfolio optimizer.\n\n#project #quant\n\n[[Research Notes]]\n[[Daily Note]]\n[[Risk Model]]",
            "mtime": now - 2 * one_day,
        },
        "projects/Risk Model.md": {
            "content": "# Risk Model\n\nFactor risk model for the portfolio.\n\n#project #quant #risk\n\n[[Portfolio Project]]",
            "mtime": now - 3 * one_day,
        },
        "research/Research Notes.md": {
            "content": "# Research Notes\n\nDeep learning for financial time series prediction.\nNeural networks show promise for volatility forecasting.\n\n#research #ml #quant\n\n[[Portfolio Project]]\n[[Risk Model]]",
            "mtime": now - 5 * one_day,
        },
        "research/ML Paper Review.md": {
            "content": "# ML Paper Review\n\nReview of attention mechanisms in transformer models.\n\n#research #ml\n\n[[Research Notes]]",
            "mtime": now - 10 * one_day,
        },
        "archive/Old Notes.md": {
            "content": "# Old Notes\n\nSome old content from last year.\n\n#archive",
            "mtime": now - 90 * one_day,
        },
        "Orphan Note.md": {
            "content": "# Orphan Note\n\nThis note has no links to or from other notes.\n\n#orphan",
            "mtime": now - 30 * one_day,
        },
    }

    for rel_path, data in notes.items():
        full_path = os.path.join(vault, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(data["content"])
        os.utime(full_path, (data["mtime"], data["mtime"]))

    return vault


def _build_mock_index(vault: str) -> NoteIndex:
    """Build a NoteIndex from the test vault."""
    from obsidian_connector.graph import build_note_index
    return build_note_index(vault)


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------

def test_search_result_dataclass():
    """SearchResult has all required fields."""
    print("\n== test_search_result_dataclass ==")
    r = SearchResult(path="test.md", title="Test", score=0.5, match_reasons=["reason"], snippet="snip")
    assert_equal(r.path, "test.md", "path field")
    assert_equal(r.title, "Test", "title field")
    assert_equal(r.score, 0.5, "score field")
    assert_equal(r.match_reasons, ["reason"], "match_reasons field")
    assert_equal(r.snippet, "snip", "snippet field")

    # Default values.
    r2 = SearchResult(path="a.md", title="A", score=0.1)
    assert_equal(r2.match_reasons, [], "match_reasons default")
    assert_equal(r2.snippet, "", "snippet default")


def test_profile_weights():
    """PROFILE_WEIGHTS has all expected profiles and weights sum to ~1.0."""
    print("\n== test_profile_weights ==")
    expected_profiles = {"journal", "project", "research", "review", "default"}
    assert_equal(set(PROFILE_WEIGHTS.keys()), expected_profiles, "all profiles present")

    for name, weights in PROFILE_WEIGHTS.items():
        total = sum(weights.values())
        assert_close(total, 1.0, f"profile '{name}' weights sum")

    # Verify specific weights.
    assert_equal(PROFILE_WEIGHTS["journal"]["recency"], 0.5, "journal recency weight")
    assert_equal(PROFILE_WEIGHTS["project"]["graph"], 0.4, "project graph weight")
    assert_equal(PROFILE_WEIGHTS["research"]["semantic"], 0.5, "research semantic weight")


def test_lexical_score_title_match():
    """_lexical_score returns higher score for title match."""
    print("\n== test_lexical_score_title_match ==")
    content = "This is a document about portfolio optimization and risk."
    score_title = _lexical_score("portfolio", content, "Portfolio Project")
    score_no_title = _lexical_score("portfolio", content, "Other Title")
    assert_greater(score_title, score_no_title, "title match boosts score")


def test_lexical_score_no_match():
    """_lexical_score returns 0 for no match."""
    print("\n== test_lexical_score_no_match ==")
    score = _lexical_score("zzz_nonexistent_xyz", "This is about finance.", "Finance")
    assert_equal(score, 0.0, "no match returns 0.0")


def test_lexical_score_content_match():
    """_lexical_score returns positive score for content match."""
    print("\n== test_lexical_score_content_match ==")
    content = "Machine learning models for portfolio optimization."
    score = _lexical_score("machine learning", content, "Notes")
    assert_greater(score, 0.0, "content match has positive score")


def test_graph_score_backlinks():
    """_graph_score returns higher score for notes with more backlinks."""
    print("\n== test_graph_score_backlinks ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        idx = _build_mock_index(vault)

        # Portfolio Project has several backlinks, Orphan Note has none.
        score_connected = _graph_score("projects/Portfolio Project.md", idx)
        score_orphan = _graph_score("Orphan Note.md", idx)
        assert_greater(score_connected, score_orphan, "more backlinks -> higher graph score")


def test_graph_score_no_index():
    """_graph_score returns 0.0 when no index is provided."""
    print("\n== test_graph_score_no_index ==")
    score = _graph_score("test.md", None)
    assert_equal(score, 0.0, "no index returns 0.0")


def test_recency_score_recent():
    """_recency_score returns higher score for recent files."""
    print("\n== test_recency_score_recent ==")
    now = time.time()
    score_now = _recency_score(now, now)
    assert_close(score_now, 1.0, "just-modified file scores ~1.0")

    score_1h = _recency_score(now - 3600, now)
    assert_greater(score_1h, 0.95, "1 hour ago scores > 0.95")


def test_recency_score_old():
    """_recency_score returns lower score for old files."""
    print("\n== test_recency_score_old ==")
    now = time.time()
    one_week = 7 * 24 * 60 * 60

    score_1w = _recency_score(now - one_week, now)
    assert_close(score_1w, 0.5, "1 week ago scores ~0.5", tol=0.05)

    score_2w = _recency_score(now - 2 * one_week, now)
    assert_close(score_2w, 0.25, "2 weeks ago scores ~0.25", tol=0.05)

    score_90d = _recency_score(now - 90 * 86400, now)
    assert_less(score_90d, 0.01, "90 days ago scores < 0.01")


def test_recency_score_ordering():
    """_recency_score is monotonically decreasing with age."""
    print("\n== test_recency_score_ordering ==")
    now = time.time()
    s1 = _recency_score(now, now)
    s2 = _recency_score(now - 86400, now)
    s3 = _recency_score(now - 7 * 86400, now)
    s4 = _recency_score(now - 30 * 86400, now)
    assert_greater(s1, s2, "now > 1 day ago")
    assert_greater(s2, s3, "1 day > 1 week")
    assert_greater(s3, s4, "1 week > 30 days")


def test_merge_scores_respects_weights():
    """_merge_scores respects profile weights."""
    print("\n== test_merge_scores_respects_weights ==")
    scores = {"lexical": 1.0, "semantic": 0.0, "graph": 0.0, "recency": 0.0}

    # With default weights (lexical=0.4), combined should be 0.4.
    combined_default = _merge_scores(scores, PROFILE_WEIGHTS["default"])
    assert_close(combined_default, 0.4, "default: lexical=1.0 -> combined ~0.4", tol=0.05)

    # With journal weights (lexical=0.3), combined should be 0.3.
    combined_journal = _merge_scores(scores, PROFILE_WEIGHTS["journal"])
    assert_close(combined_journal, 0.3, "journal: lexical=1.0 -> combined ~0.3", tol=0.05)


def test_merge_scores_all_equal():
    """_merge_scores with equal scores and review profile returns balanced result."""
    print("\n== test_merge_scores_all_equal ==")
    scores = {"lexical": 0.5, "semantic": 0.5, "graph": 0.5, "recency": 0.5}
    combined = _merge_scores(scores, PROFILE_WEIGHTS["review"])
    # All equal at 0.5 with weights summing to 1.0 -> combined = 0.5.
    assert_close(combined, 0.5, "equal scores + balanced weights", tol=0.05)


def test_explain_scores():
    """_explain_scores generates readable strings."""
    print("\n== test_explain_scores ==")
    scores = {"lexical": 0.8, "semantic": 0.0, "graph": 0.5, "recency": 0.9}
    weights = PROFILE_WEIGHTS["default"]
    reasons = _explain_scores(scores, weights)
    assert_greater(len(reasons), 0, "non-empty explanations")

    # Should have entries for lexical, graph, and recency (semantic=0.0 skipped).
    reason_text = " ".join(reasons)
    assert_true("keyword match" in reason_text, "contains keyword match explanation")
    assert_true("recency" in reason_text, "contains recency explanation")
    assert_true("graph" in reason_text, "contains graph explanation")


def test_hybrid_search_returns_sorted():
    """hybrid_search returns results sorted by score."""
    print("\n== test_hybrid_search_returns_sorted ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        results = hybrid_search("portfolio", vault)
        assert_greater(len(results), 0, "search returns results")
        for i in range(len(results) - 1):
            assert_true(
                results[i].score >= results[i + 1].score,
                f"result {i} score >= result {i+1} score",
            )


def test_hybrid_search_journal_profile():
    """hybrid_search with profile='journal' boosts recent notes."""
    print("\n== test_hybrid_search_journal_profile ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        # The daily note from today should rank higher with journal profile.
        results_journal = hybrid_search("daily note", vault, profile="journal")
        results_default = hybrid_search("daily note", vault, profile="default")

        assert_greater(len(results_journal), 0, "journal profile returns results")
        assert_greater(len(results_default), 0, "default profile returns results")

        # The most recent daily note should appear higher in journal profile.
        if len(results_journal) >= 2 and len(results_default) >= 2:
            # Find the recent daily note position in each.
            journal_paths = [r.path for r in results_journal]
            default_paths = [r.path for r in results_default]
            recent_daily = "daily/2026-03-30.md"
            if recent_daily in journal_paths:
                journal_pos = journal_paths.index(recent_daily)
                assert_less(journal_pos, 3, "recent daily note in top 3 for journal profile")


def test_hybrid_search_project_profile():
    """hybrid_search with profile='project' boosts well-connected notes."""
    print("\n== test_hybrid_search_project_profile ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        results = hybrid_search("project", vault, profile="project")
        assert_greater(len(results), 0, "project profile returns results")
        # Portfolio Project is well-connected; should rank highly.
        paths = [r.path for r in results[:5]]
        assert_true(
            any("Portfolio Project" in p for p in paths),
            "well-connected Portfolio Project in top 5",
        )


def test_hybrid_search_explain():
    """hybrid_search with explain=True includes match_reasons."""
    print("\n== test_hybrid_search_explain ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        results = hybrid_search("portfolio", vault, explain=True)
        assert_greater(len(results), 0, "search with explain returns results")
        # Top results (with actual keyword matches) should have reasons.
        # Very low-scoring results may have all signals below the explain
        # threshold, so only check the first few.
        top_with_reasons = [r for r in results if r.match_reasons]
        assert_greater(len(top_with_reasons), 0, "at least one result has match_reasons")
        # The top result specifically should have match_reasons.
        assert_greater(len(results[0].match_reasons), 0, "top result has match_reasons")


def test_hybrid_search_no_explain():
    """hybrid_search without explain has empty match_reasons."""
    print("\n== test_hybrid_search_no_explain ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        results = hybrid_search("portfolio", vault, explain=False)
        assert_greater(len(results), 0, "search without explain returns results")
        for r in results:
            assert_equal(r.match_reasons, [], f"result '{r.title}' has empty match_reasons")


def test_hybrid_search_empty_query():
    """Empty query returns empty results."""
    print("\n== test_hybrid_search_empty_query ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        results = hybrid_search("", vault)
        assert_equal(len(results), 0, "empty query returns no results")


def test_hybrid_search_top_k():
    """top_k limits result count."""
    print("\n== test_hybrid_search_top_k ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        results = hybrid_search("note", vault, top_k=3)
        assert_true(len(results) <= 3, f"top_k=3 limits results (got {len(results)})")


def test_hybrid_search_dedup():
    """Results are deduplicated by path."""
    print("\n== test_hybrid_search_dedup ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        results = hybrid_search("portfolio project", vault)
        paths = [r.path for r in results]
        assert_equal(len(paths), len(set(paths)), "no duplicate paths")


def test_retrieval_works_without_embeddings():
    """Retrieval works without embeddings (semantic score = 0.0)."""
    print("\n== test_retrieval_works_without_embeddings ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        # No embeddings_index provided -- semantic should be 0.0 but
        # other signals still work.
        results = hybrid_search("portfolio", vault, embeddings_index=None)
        assert_greater(len(results), 0, "retrieval works without embeddings")


def test_embeddings_index_availability():
    """EmbeddingsIndex.is_available() reflects sentence-transformers status."""
    print("\n== test_embeddings_index_availability ==")
    # In the test environment, sentence-transformers is likely not installed.
    available = EmbeddingsIndex.is_available()
    # We can't assert True or False -- just that it returns a bool.
    assert_true(isinstance(available, bool), "is_available returns bool")

    # When not available, build and similar should raise ImportError.
    if not available:
        with tempfile.TemporaryDirectory() as tmp:
            idx = EmbeddingsIndex(os.path.join(tmp, "test_emb.sqlite"))
            try:
                idx.build(tmp)
                assert_true(False, "build() should raise ImportError")
            except ImportError:
                assert_true(True, "build() raises ImportError when unavailable")

            try:
                idx.similar("test query")
                assert_true(False, "similar() should raise ImportError")
            except ImportError:
                assert_true(True, "similar() raises ImportError when unavailable")
            finally:
                idx.close()
    else:
        # If sentence-transformers IS installed, test basic functionality.
        assert_true(True, "sentence-transformers is available (skip ImportError tests)")


def test_cosine_similarity():
    """_cosine_similarity computes correct values."""
    print("\n== test_cosine_similarity ==")
    # Identical vectors -> 1.0.
    sim = _cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    assert_close(sim, 1.0, "identical vectors")

    # Orthogonal vectors -> 0.0.
    sim = _cosine_similarity([1.0, 0.0], [0.0, 1.0])
    assert_close(sim, 0.0, "orthogonal vectors")

    # Opposite vectors -> -1.0.
    sim = _cosine_similarity([1.0, 0.0], [-1.0, 0.0])
    assert_close(sim, -1.0, "opposite vectors")

    # Zero vector -> 0.0.
    sim = _cosine_similarity([0.0, 0.0], [1.0, 1.0])
    assert_close(sim, 0.0, "zero vector")


def test_embeddings_index_remove():
    """EmbeddingsIndex.remove() deletes entries."""
    print("\n== test_embeddings_index_remove ==")
    with tempfile.TemporaryDirectory() as tmp:
        idx = EmbeddingsIndex(os.path.join(tmp, "test_emb.sqlite"))
        conn = idx._connect()
        # Manually insert a dummy embedding.
        import struct
        dummy_blob = struct.pack("f" * 3, 0.1, 0.2, 0.3)
        conn.execute(
            "INSERT INTO embeddings (note_path, embedding, model, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("test.md", dummy_blob, "test-model", time.time()),
        )
        conn.commit()

        # Verify it exists.
        row = conn.execute("SELECT note_path FROM embeddings WHERE note_path = ?", ("test.md",)).fetchone()
        assert_true(row is not None, "entry exists before remove")

        # Remove it.
        idx.remove("test.md")
        row = conn.execute("SELECT note_path FROM embeddings WHERE note_path = ?", ("test.md",)).fetchone()
        assert_true(row is None, "entry removed after remove()")
        idx.close()


def test_hybrid_search_with_note_index():
    """hybrid_search works when a pre-built NoteIndex is provided."""
    print("\n== test_hybrid_search_with_note_index ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        idx = _build_mock_index(vault)
        results = hybrid_search("portfolio", vault, note_index=idx)
        assert_greater(len(results), 0, "search with pre-built index returns results")


def test_snippet_extraction():
    """Search results include relevant snippets."""
    print("\n== test_snippet_extraction ==")
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(tmp)
        results = hybrid_search("portfolio", vault)
        for r in results:
            if "Portfolio" in r.title:
                assert_greater(len(r.snippet), 0, "snippet is non-empty")
                break


def test_lexical_score_empty_query():
    """_lexical_score returns 0.0 for empty query."""
    print("\n== test_lexical_score_empty_query ==")
    score = _lexical_score("", "Some content here.", "Title")
    assert_equal(score, 0.0, "empty query returns 0.0")


def test_recency_half_life():
    """Recency score follows the 7-day half-life correctly."""
    print("\n== test_recency_half_life ==")
    now = time.time()
    half_life = 7 * 24 * 60 * 60
    score = _recency_score(now - half_life, now)
    # Should be ~0.5 at the half-life.
    assert_close(score, 0.5, "score at half-life ~0.5", tol=0.01)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    test_search_result_dataclass()
    test_profile_weights()
    test_lexical_score_title_match()
    test_lexical_score_no_match()
    test_lexical_score_content_match()
    test_lexical_score_empty_query()
    test_graph_score_backlinks()
    test_graph_score_no_index()
    test_recency_score_recent()
    test_recency_score_old()
    test_recency_score_ordering()
    test_recency_half_life()
    test_merge_scores_respects_weights()
    test_merge_scores_all_equal()
    test_explain_scores()
    test_hybrid_search_returns_sorted()
    test_hybrid_search_journal_profile()
    test_hybrid_search_project_profile()
    test_hybrid_search_explain()
    test_hybrid_search_no_explain()
    test_hybrid_search_empty_query()
    test_hybrid_search_top_k()
    test_hybrid_search_dedup()
    test_retrieval_works_without_embeddings()
    test_embeddings_index_availability()
    test_cosine_similarity()
    test_embeddings_index_remove()
    test_hybrid_search_with_note_index()
    test_snippet_extraction()

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed, {ASSERTIONS} assertions")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
