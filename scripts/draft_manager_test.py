#!/usr/bin/env python3
"""Tests for draft_manager module -- draft lifecycle management (A3)."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.draft_manager import (
    DraftInfo,
    _add_datestamp_suffix,
    _parse_frontmatter,
    _strip_generated_by,
    approve_draft,
    clean_stale_drafts,
    draft_summary,
    list_drafts,
    reject_draft,
)

_PASS = 0
_FAIL = 0


def _check(label: str, ok: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        msg = f"  FAIL  {label}"
        if detail:
            msg += f" -- {detail}"
        print(msg)


def _assert_eq(label: str, got, expected) -> None:
    _check(label, got == expected, f"got {got!r}, expected {expected!r}")


# ---------------------------------------------------------------------------
# Helpers to set up a temp vault
# ---------------------------------------------------------------------------

def _make_draft(vault: Path, name: str, generated_by: str, extra_fm: str = "",
                age_days: int = 0) -> Path:
    """Create a draft .md file with generated_by frontmatter."""
    drafts_dir = vault / "Inbox" / "Agent Drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    created = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    fm_lines = [
        "---",
        f"title: {name}",
        f"generated_by: {generated_by}",
        f"created: {created}",
    ]
    if extra_fm:
        fm_lines.append(extra_fm)
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(f"# {name}")
    fm_lines.append("")
    fm_lines.append("Body content here.")

    path = drafts_dir / f"{name}.md"
    path.write_text("\n".join(fm_lines), encoding="utf-8")

    # Back-date the mtime to match age_days for stat-based fallback.
    if age_days > 0:
        ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).timestamp()
        os.utime(str(path), (ts, ts))

    return path


def _make_non_draft(vault: Path, name: str) -> Path:
    """Create a .md file WITHOUT generated_by frontmatter."""
    drafts_dir = vault / "Inbox" / "Agent Drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    path = drafts_dir / f"{name}.md"
    content = f"---\ntitle: {name}\ntags: [note]\n---\n\n# {name}\n\nUser content.\n"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def main() -> int:
    # == Test 1: _parse_frontmatter with valid YAML ==
    print("\n--- _parse_frontmatter: valid frontmatter ---")
    content = "---\ntitle: My Note\ngenerated_by: obsidian-connector\ntags: ideas\n---\n\n# Body"
    fm = _parse_frontmatter(content)
    _assert_eq("title parsed", fm.get("title"), "My Note")
    _assert_eq("generated_by parsed", fm.get("generated_by"), "obsidian-connector")

    # == Test 2: _parse_frontmatter with no frontmatter ==
    print("\n--- _parse_frontmatter: no frontmatter ---")
    fm_empty = _parse_frontmatter("# Just a heading\n\nSome body text.")
    _assert_eq("returns empty dict", fm_empty, {})

    # == Test 3: _strip_generated_by preserves other frontmatter ==
    print("\n--- _strip_generated_by: preserves other fields ---")
    src = "---\ntitle: Keep Me\ngenerated_by: obsidian-connector\ntags: draft\n---\n\nBody."
    stripped = _strip_generated_by(src)
    _check("generated_by removed", "generated_by" not in stripped)
    _check("title preserved", "title: Keep Me" in stripped)
    _check("tags preserved", "tags: draft" in stripped)
    _check("body preserved", "Body." in stripped)

    # == Test 4: _strip_generated_by on content without frontmatter ==
    print("\n--- _strip_generated_by: no frontmatter ---")
    plain = "# No FM\n\nText."
    _assert_eq("unchanged when no FM", _strip_generated_by(plain), plain)

    # == Test 5: _add_datestamp_suffix ==
    print("\n--- _add_datestamp_suffix ---")
    result = _add_datestamp_suffix("my-note.md")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _assert_eq("datestamp in filename", result, f"my-note_{today}.md")

    # == Temp vault tests ==
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)

        # Create drafts with varying ages.
        _make_draft(vault, "fresh-idea", "obsidian-connector", age_days=1)
        _make_draft(vault, "old-draft", "obsidian-connector", age_days=20)
        _make_draft(vault, "mid-draft", "obsidian-connector", age_days=7,
                    extra_fm="priority: high")
        _make_non_draft(vault, "user-note")

        # == Test 6: list_drafts finds generated_by files ==
        print("\n--- list_drafts: finds drafts ---")
        drafts = list_drafts(vault)
        _assert_eq("found 3 drafts (ignores non-draft)", len(drafts), 3)

        # == Test 7: list_drafts ignores non-generated_by files ==
        print("\n--- list_drafts: ignores non-drafts ---")
        names = [d.title for d in drafts]
        _check("user-note not in results", "user-note" not in names)

        # == Test 8: list_drafts correct age_days ==
        print("\n--- list_drafts: age_days calculation ---")
        old = [d for d in drafts if d.title == "old-draft"][0]
        _check("old-draft age >= 20", old.age_days >= 20,
               f"got {old.age_days}")

        # == Test 9: list_drafts sorted by age descending ==
        print("\n--- list_drafts: sorted by age desc ---")
        ages = [d.age_days for d in drafts]
        _check("ages descending", ages == sorted(ages, reverse=True),
               f"got {ages}")

        # == Test 10: draft_summary returns correct counts ==
        print("\n--- draft_summary ---")
        summary = draft_summary(vault)
        _assert_eq("total is 3", summary["total"], 3)
        _check("pending_review >= 1", summary["pending_review"] >= 1)
        _check("stale >= 1", summary["stale"] >= 1)

        # == Test 11: approve_draft moves and strips generated_by ==
        print("\n--- approve_draft ---")
        result = approve_draft(vault, "Inbox/Agent Drafts/fresh-idea.md", "Research")
        _assert_eq("approve moved", result["moved"], True)
        dest_path = vault / "Research" / "fresh-idea.md"
        _check("file exists in target", dest_path.is_file())

        approved_content = dest_path.read_text(encoding="utf-8")
        _check("generated_by stripped", "generated_by" not in approved_content)
        _check("title preserved after approve", "title: fresh-idea" in approved_content)

        # == Test 12: reject_draft moves to archive with datestamp ==
        print("\n--- reject_draft ---")
        result_rej = reject_draft(vault, "Inbox/Agent Drafts/mid-draft.md")
        _assert_eq("reject moved", result_rej["moved"], True)
        archive_dir = vault / "Archive" / "Rejected Drafts"
        archived_files = list(archive_dir.iterdir())
        _check("archive has file", len(archived_files) == 1)
        _check("datestamp in filename", today in archived_files[0].name)

        # == Test 13: clean_stale_drafts dry_run does not move ==
        print("\n--- clean_stale_drafts: dry_run ---")
        # old-draft is still there and is stale (age 20 > default 14).
        would_move = clean_stale_drafts(vault, max_age_days=14, dry_run=True)
        _check("dry_run reports stale", len(would_move) >= 1,
               f"got {len(would_move)}")
        old_still = (vault / "Inbox" / "Agent Drafts" / "old-draft.md")
        _check("dry_run did not move file", old_still.is_file())

        # == Test 14: clean_stale_drafts moves old drafts only ==
        print("\n--- clean_stale_drafts: moves stale ---")
        moved = clean_stale_drafts(vault, max_age_days=14)
        _check("moved stale drafts", len(moved) >= 1, f"got {len(moved)}")
        _check("old-draft removed from inbox", not old_still.is_file())
        stale_dir = vault / "Archive" / "Stale Drafts"
        _check("stale archive dir exists", stale_dir.is_dir())

        # == Test 15: clean_stale_drafts respects max_age_days ==
        print("\n--- clean_stale_drafts: respects max_age_days ---")
        # Create a new draft aged 5 days, clean with max_age_days=3.
        _make_draft(vault, "short-lived", "test-tool", age_days=5)
        moved2 = clean_stale_drafts(vault, max_age_days=3)
        _check("moved with lower threshold", len(moved2) >= 1)

    # == Test 16: path traversal in target_folder is rejected ==
    print("\n--- path traversal protection ---")
    with tempfile.TemporaryDirectory() as tmp2:
        vault2 = Path(tmp2)
        _make_draft(vault2, "traversal-test", "test-tool")
        try:
            approve_draft(vault2, "Inbox/Agent Drafts/traversal-test.md",
                          "../../etc/evil")
            _check("path traversal rejected", False, "no exception raised")
        except ValueError as exc:
            _check("path traversal rejected", "traversal" in str(exc).lower())

    # -- Summary ---------------------------------------------------------------
    print(f"\n{'='*50}")
    print(f"RESULTS: {_PASS} passed, {_FAIL} failed")
    print(f"{'='*50}")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
