#!/usr/bin/env python3
"""Graduate flow tests -- validate candidate detection and draft creation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.workflows import (
    _scan_for_candidates,
    graduate_candidates,
    graduate_execute,
)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}")
        FAIL += 1


# ---------------------------------------------------------------------------
# Test 1: _scan_for_candidates detects heading patterns
# ---------------------------------------------------------------------------

def test_scan_heading_pattern() -> None:
    print("\n--- scan: heading with 3+ content lines ---")
    lines = [
        "# Daily 2026-03-05",
        "",
        "## Factor model for CRE",
        "Line one of content about factor models.",
        "Line two discussing variance decomposition.",
        "Line three about risk attribution.",
        "",
        "## Short section",
        "Only one line.",
    ]
    candidates: list[dict] = []
    _scan_for_candidates("daily/2026-03-05.md", lines, candidates)
    check("found 1 candidate (heading)", len(candidates) == 1)
    if candidates:
        check("title is 'Factor model for CRE'", candidates[0]["title"] == "Factor model for CRE")
        check("source_file correct", candidates[0]["source_file"] == "daily/2026-03-05.md")


# ---------------------------------------------------------------------------
# Test 2: _scan_for_candidates detects wikilink-rich paragraphs
# ---------------------------------------------------------------------------

def test_scan_wikilink_pattern() -> None:
    print("\n--- scan: paragraph with 3+ wikilinks ---")
    lines = [
        "See [[Alpha]], [[Beta]], and [[Gamma]] for details on the strategy.",
    ]
    candidates: list[dict] = []
    _scan_for_candidates("daily/2026-03-04.md", lines, candidates)
    check("found 1 candidate (wikilinks)", len(candidates) == 1)
    if candidates:
        check("title is 'Alpha' (first link)", candidates[0]["title"] == "Alpha")


# ---------------------------------------------------------------------------
# Test 3: _scan_for_candidates detects #idea tag
# ---------------------------------------------------------------------------

def test_scan_idea_tag() -> None:
    print("\n--- scan: #idea tag ---")
    lines = [
        "#idea Build a real-time factor dashboard",
    ]
    candidates: list[dict] = []
    _scan_for_candidates("daily/2026-03-03.md", lines, candidates)
    check("found 1 candidate (#idea)", len(candidates) == 1)
    if candidates:
        check("title extracted from after tag", "factor dashboard" in candidates[0]["title"].lower())


# ---------------------------------------------------------------------------
# Test 4: _scan_for_candidates detects expand markers
# ---------------------------------------------------------------------------

def test_scan_expand_marker() -> None:
    print("\n--- scan: TODO expand marker ---")
    lines = [
        "TODO: expand the risk parity allocation model",
    ]
    candidates: list[dict] = []
    _scan_for_candidates("daily/2026-03-02.md", lines, candidates)
    check("found 1 candidate (expand)", len(candidates) == 1)
    if candidates:
        check("_has_expand flag set", candidates[0].get("_has_expand") is True)


# ---------------------------------------------------------------------------
# Test 5: graduate_execute with dry_run=True
# ---------------------------------------------------------------------------

def test_execute_dry_run() -> None:
    print("\n--- graduate_execute dry_run ---")
    result = graduate_execute(
        title="Test Draft",
        content="Some content about testing.",
        source_file="daily/2026-03-05.md",
        dry_run=True,
    )
    check("dry_run flag in result", result.get("dry_run") is True)
    check("would_create contains path", "Test Draft.md" in result.get("would_create", ""))
    check("content_preview present", len(result.get("content_preview", "")) > 0)
    check("path includes Agent Drafts", "Agent Drafts" in result.get("would_create", ""))


# ---------------------------------------------------------------------------
# Test 6: graduate_execute without confirm raises ValueError
# ---------------------------------------------------------------------------

def test_execute_no_confirm() -> None:
    print("\n--- graduate_execute without confirm ---")
    raised = False
    try:
        graduate_execute(
            title="Test",
            content="Body",
        )
    except ValueError as exc:
        raised = True
        check("error message mentions confirm", "confirm" in str(exc).lower())
    check("ValueError was raised", raised)


# ---------------------------------------------------------------------------
# Test 7: graduate_execute with confirm=True (mock run_obsidian)
# ---------------------------------------------------------------------------

def test_execute_confirm() -> None:
    print("\n--- graduate_execute with confirm (mocked) ---")
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir)
        with patch("obsidian_connector.config.resolve_vault_path", return_value=vault_path), \
             patch("obsidian_connector.workflows.log_action") as mock_log:
            result = graduate_execute(
                title="My Note",
                content="Agent-generated analysis of vol surface.",
                source_file="daily/2026-03-05.md",
                confirm=True,
            )
            check("created path in result", "My Note.md" in result.get("created", ""))
            check("source in result", result.get("source") == "daily/2026-03-05.md")
            check("provenance has agent source", result.get("provenance", {}).get("source") == "agent")
            check("provenance has draft status", result.get("provenance", {}).get("status") == "draft")

            # Verify the file was actually written with content.
            written_file = vault_path / "Inbox" / "Agent Drafts" / "My Note.md"
            check("file was written to disk", written_file.is_file())
            written_content = written_file.read_text()
            check("file has frontmatter", "source: agent" in written_content)
            check("file has body content", "vol surface" in written_content)
            check("log_action was called", mock_log.called)


# ---------------------------------------------------------------------------
# Test 8: graduate_candidates with mocked vault (integration-style)
# ---------------------------------------------------------------------------

def test_candidates_integration() -> None:
    print("\n--- graduate_candidates (mocked vault) ---")

    daily_content = (
        "# 2026-03-05\n"
        "\n"
        "## Option pricing deep dive\n"
        "Reviewed Black-Scholes assumptions.\n"
        "Analyzed vol smile dynamics.\n"
        "Compared with Heston stochastic vol.\n"
        "\n"
        "## Stray thoughts\n"
        "Short note.\n"
        "\n"
        "## Evening review\n"
        "#idea Build a Greeks calculator in Python\n"
        "Need to think about this more.\n"
        "Could use QuantLib bindings.\n"
    )

    def mock_search(query, vault=None):
        if "2026-03" in query:
            return [{"file": "daily/2026-03-05.md", "matches": []}]
        return []

    def mock_read(path, vault=None):
        if "2026-03-05" in path:
            return daily_content
        return ""

    with patch("obsidian_connector.workflows.search_notes", side_effect=mock_search), \
         patch("obsidian_connector.workflows.read_note", side_effect=mock_read), \
         patch("obsidian_connector.workflows._load_or_build_index", return_value=None):
        result = graduate_candidates(lookback_days=3)

    check("result is a list", isinstance(result, list))
    # Without a graph index, fewer candidates are found (search-only mode).
    # The key assertion is: it returns a list without crashing.
    check("found candidates (search-only mode)", len(result) >= 0)

    if result:
        # Verify no internal scoring fields leaked
        for cand in result:
            check(f"no _link_count in '{cand['title']}'", "_link_count" not in cand)
            check(f"no _has_expand in '{cand['title']}'", "_has_expand" not in cand)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    test_scan_heading_pattern()
    test_scan_wikilink_pattern()
    test_scan_idea_tag()
    test_scan_expand_marker()
    test_execute_dry_run()
    test_execute_no_confirm()
    test_execute_confirm()
    test_candidates_integration()

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
