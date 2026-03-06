#!/usr/bin/env python3
"""Tests for delegation detection, context load, and rebuild-index."""

from __future__ import annotations

import sys
import tempfile
import time
import traceback
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.client import ObsidianCLIError

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
# Unit tests (no Obsidian required)
# ---------------------------------------------------------------------------

def test_delegation_patterns() -> None:
    """Test the regex patterns used by detect_delegations."""
    import re
    from obsidian_connector.workflows import (
        _DELEGATION_CALLOUT_RE,
        _DELEGATION_PREFIX_RE,
        _DONE_MARKER_RE,
    )

    print("\n--- Delegation regex patterns ---")

    # @agent: prefix
    m = _DELEGATION_PREFIX_RE.match("@agent: do the thing")
    check("@agent: matches", m is not None)
    if m:
        check("@agent: captures instruction", m.group(2).strip() == "do the thing")

    # @claude: prefix (case insensitive)
    m = _DELEGATION_PREFIX_RE.match("@Claude: summarize notes")
    check("@Claude: matches (case insensitive)", m is not None)
    if m:
        check("@Claude: captures instruction", m.group(2).strip() == "summarize notes")

    # Callout format
    m = _DELEGATION_CALLOUT_RE.match("> [!agent] review this section")
    check("> [!agent] matches", m is not None)
    if m:
        check("> [!agent] captures instruction", m.group(1).strip() == "review this section")

    # Done marker
    check("[done] matches", bool(_DONE_MARKER_RE.search("[done]")))
    check("[completed] matches", bool(_DONE_MARKER_RE.search("[completed]")))
    check("[Done] matches (case insensitive)", bool(_DONE_MARKER_RE.search("[Done]")))
    check("random text does not match done", not bool(_DONE_MARKER_RE.search("still pending")))

    # Non-matching
    check("plain text does not match prefix", _DELEGATION_PREFIX_RE.match("plain text") is None)
    check("plain text does not match callout", _DELEGATION_CALLOUT_RE.match("plain text") is None)


def test_delegation_line_scan() -> None:
    """Test scanning lines for delegation patterns."""
    import re
    from obsidian_connector.workflows import (
        _DELEGATION_CALLOUT_RE,
        _DELEGATION_PREFIX_RE,
        _DONE_MARKER_RE,
    )

    print("\n--- Delegation line scanning ---")

    content = """# Daily Note
Some text here.

@agent: update the architecture docs
[done]

@claude: Review PR #42
still pending

> [!agent] check test coverage
[completed]

Normal text here.
"""
    lines = content.split("\n")
    delegations = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        instruction = None

        prefix_match = _DELEGATION_PREFIX_RE.match(stripped)
        if prefix_match:
            instruction = prefix_match.group(2).strip()
        else:
            callout_match = _DELEGATION_CALLOUT_RE.match(stripped)
            if callout_match:
                instruction = callout_match.group(1).strip()

        if instruction is None:
            continue

        status = "pending"
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if _DONE_MARKER_RE.search(next_line):
                status = "done"

        delegations.append({
            "line_number": i + 1,
            "instruction": instruction,
            "status": status,
        })

    check("found 3 delegations", len(delegations) == 3)
    if len(delegations) >= 3:
        check("first is done", delegations[0]["status"] == "done")
        check("first instruction correct", delegations[0]["instruction"] == "update the architecture docs")
        check("second is pending", delegations[1]["status"] == "pending")
        check("second instruction correct", delegations[1]["instruction"] == "Review PR #42")
        check("third is done", delegations[2]["status"] == "done")
        check("third instruction correct", delegations[2]["instruction"] == "check test coverage")


def test_rebuild_index_with_temp_vault() -> None:
    """Test IndexStore.build_full with a temporary vault."""
    from obsidian_connector.index_store import IndexStore

    print("\n--- Rebuild index (temp vault) ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        vault.mkdir()

        # Create test notes
        (vault / "Alpha.md").write_text(
            "---\ntitle: Alpha\n---\n[[Beta]] #topic\nSome content.",
            encoding="utf-8",
        )
        (vault / "Beta.md").write_text(
            "# Beta\n[[Alpha]]\n#topic #another",
            encoding="utf-8",
        )
        (vault / "Orphan.md").write_text(
            "# Orphan\nNo links here.",
            encoding="utf-8",
        )

        db_path = Path(tmp) / "test.sqlite"
        store = IndexStore(db_path=db_path)
        try:
            t0 = time.monotonic()
            index = store.build_full(vault_path=vault)
            duration_ms = int((time.monotonic() - t0) * 1000)

            check("3 notes indexed", len(index.notes) == 3)
            check("1 orphan detected", len(index.orphans) == 1)
            check("Orphan.md is the orphan", "Orphan.md" in index.orphans)
            check("2 tags found", len(index.tags) >= 2)
            check("duration is positive", duration_ms >= 0)
            print(f"  Index built in {duration_ms}ms")
        finally:
            store.close()


def test_detect_delegations_live() -> None:
    """Test detect_delegations against the live vault (requires Obsidian)."""
    from obsidian_connector.workflows import detect_delegations

    print("\n--- detect_delegations (live vault) ---")

    try:
        result = detect_delegations(lookback_days=1)
        check("returns a list", isinstance(result, list))
        print(f"  Found {len(result)} delegation(s)")
        for d in result[:3]:
            print(f"    [{d.get('status')}] {d.get('instruction', '')[:60]}  ({d.get('file')})")
    except ObsidianCLIError as exc:
        print(f"  SKIP  (Obsidian not available: {exc})")


def test_context_load_full_live() -> None:
    """Test context_load_full against the live vault (requires Obsidian)."""
    from obsidian_connector.workflows import context_load_full

    print("\n--- context_load_full (live vault) ---")

    try:
        result = context_load_full()
        check("returns a dict", isinstance(result, dict))
        check("has context_files key", "context_files" in result)
        check("has daily_note key", "daily_note" in result)
        check("has recent_dailies key", "recent_dailies" in result)
        check("has tasks key", "tasks" in result)
        check("has open_loops key", "open_loops" in result)
        check("has read_count key", "read_count" in result)
        check("read_count <= 20", result.get("read_count", 0) <= 20)
        print(f"  read_count: {result.get('read_count', 0)}")
        print(f"  context_files: {len(result.get('context_files', []))}")
        print(f"  recent_dailies: {len(result.get('recent_dailies', []))}")
        print(f"  tasks: {len(result.get('tasks', []))}")
        print(f"  open_loops: {len(result.get('open_loops', []))}")
    except ObsidianCLIError as exc:
        print(f"  SKIP  (Obsidian not available: {exc})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # Unit tests (always run, no Obsidian needed)
    test_delegation_patterns()
    test_delegation_line_scan()
    test_rebuild_index_with_temp_vault()

    # Live vault tests (may skip if Obsidian is not running)
    test_detect_delegations_live()
    test_context_load_full_live()

    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
