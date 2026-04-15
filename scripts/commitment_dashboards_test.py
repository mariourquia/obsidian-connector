#!/usr/bin/env python3
"""Tests for commitment_dashboards.py.

Covers:
- All four dashboards created from an empty vault (no-crash, no empty-content)
- Wikilinks are vault-relative and drop the .md extension
- Link validity: every wikilink target file exists in the vault
- Grouped-by-project ordering in Commitments.md
- Due Soon separates overdue vs upcoming; excludes items beyond the window
- Waiting On Me only shows requires_ack=True items
- Postponed only shows items with postponed_until set
- Done items appear in Commitments.md Done section
- No duplicate entries when the same action_id exists
- Idempotent: same vault state + same now_iso -> identical file content
- update_all_dashboards writes exactly four files
- Table wikilinks use \\| (pipe escaped for Markdown tables)
- DashboardResult.written counts match rendered items

Run with: python3 scripts/commitment_dashboards_test.py
"""

from __future__ import annotations

import re
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.commitment_notes import ActionInput, write_commitment_note
from obsidian_connector.commitment_dashboards import (
    DASHBOARDS_DIR,
    DashboardResult,
    generate_commitments_dashboard,
    generate_due_soon_dashboard,
    generate_postponed_dashboard,
    generate_waiting_on_me_dashboard,
    update_all_dashboards,
)

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0


def test(label: str, fn):
    global PASS, FAIL
    print(f"\n{'=' * 60}")
    print(f"TEST: {label}")
    print(f"{'=' * 60}")
    try:
        fn()
        print("  OK")
        PASS += 1
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=6)
        FAIL += 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_vault():
    td = tempfile.TemporaryDirectory(prefix="obsx_dash_test_")
    return Path(td.name), td


NOW = "2026-04-12T10:00:00+00:00"

# Due dates relative to NOW (2026-04-12T10:00:00+00:00)
PAST_DUE = "2026-04-10T10:00:00+00:00"      # 2 days ago -- overdue
SOON_DUE = "2026-04-15T10:00:00+00:00"       # 3 days out -- within 7-day window
FAR_DUE = "2026-04-25T10:00:00+00:00"        # 13 days out -- outside 7-day window
FUTURE_POSTPONE = "2026-05-01T00:00:00+00:00"


def _action(**overrides) -> ActionInput:
    base = dict(
        action_id="ACT-DASH-0000001",
        capture_id="CAP-DASH-9999999",
        title="Default task",
        created_at="2026-04-12T08:00:00+00:00",
        project="test-project",
        status="open",
        priority="normal",
        due_at=None,
        postponed_until=None,
        requires_ack=False,
        escalation_policy=None,
        channels=[],
        source_note=None,
        description="",
    )
    base.update(overrides)
    return ActionInput(**base)


def _write(vault: Path, **overrides) -> ActionInput:
    a = _action(**overrides)
    write_commitment_note(vault, a)
    return a


# ---------------------------------------------------------------------------
# Helper: extract wikilink targets from content
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[([^\]|\\]+?)(?:\\?\|[^\]]+)?\]\]")


def _extract_wikilink_targets(content: str) -> list[str]:
    """Return vault-relative target paths (no .md) from all [[...]] links."""
    return _WIKILINK_RE.findall(content)


def _assert_links_valid(vault: Path, content: str):
    """Assert every wikilink target resolves to an existing file in vault."""
    targets = _extract_wikilink_targets(content)
    assert targets, "dashboard contains no wikilinks -- expected at least one"
    for target in targets:
        resolved = vault / (target + ".md")
        assert resolved.exists(), (
            f"wikilink target not found: {target!r}\n"
            f"  expected file: {resolved}"
        )


# ---------------------------------------------------------------------------
# 1. Empty vault: all dashboards (commitment + review) created without error
# ---------------------------------------------------------------------------

# Task 26: update_all_dashboards now also writes the four Review dashboards,
# so the result list grew from 4 to 8.  The prefix (first 4) is stable.


def test_empty_vault_all_four_dashboards():
    vault, _td = _make_vault()
    results = update_all_dashboards(vault, now_iso=NOW)
    assert len(results) == 8, f"expected 8 results (4 commitment + 4 review), got {len(results)}"
    for r in results:
        assert isinstance(r, DashboardResult)
        assert r.path.exists(), f"dashboard file not created: {r.path}"
        content = r.path.read_text()
        assert len(content) > 0


def test_empty_vault_written_counts_are_zero():
    vault, _td = _make_vault()
    results = update_all_dashboards(vault, now_iso=NOW)
    for r in results:
        assert r.written == 0, f"{r.path.name}: expected written=0, got {r.written}"


# ---------------------------------------------------------------------------
# 2. Wikilinks: no .md extension, vault-relative path
# ---------------------------------------------------------------------------

def test_wikilinks_have_no_md_extension():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-WL-001", title="Link check task")
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    targets = _extract_wikilink_targets(content)
    assert targets, "expected at least one wikilink"
    for t in targets:
        assert not t.endswith(".md"), f"wikilink target still has .md: {t!r}"


def test_wikilinks_include_full_vault_relative_path():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-WL-002", title="Path check")
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    targets = _extract_wikilink_targets(content)
    assert any("Commitments" in t for t in targets), (
        f"expected path containing 'Commitments', got: {targets}"
    )


# ---------------------------------------------------------------------------
# 3. Link validity: wikilink targets exist on disk
# ---------------------------------------------------------------------------

def test_commitments_dashboard_links_are_valid():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-LV-001", title="Valid link 1")
    _write(vault, action_id="ACT-LV-002", title="Valid link 2", status="done")
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    _assert_links_valid(vault, r.path.read_text())


def test_due_soon_dashboard_links_are_valid():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-LV-003", title="Due soon link", due_at=SOON_DUE)
    r = generate_due_soon_dashboard(vault, within_days=7, now_iso=NOW)
    _assert_links_valid(vault, r.path.read_text())


def test_waiting_on_me_dashboard_links_are_valid():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-LV-004", title="Waiting link", requires_ack=True)
    r = generate_waiting_on_me_dashboard(vault, now_iso=NOW)
    _assert_links_valid(vault, r.path.read_text())


def test_postponed_dashboard_links_are_valid():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-LV-005", title="Postponed link", postponed_until=FUTURE_POSTPONE)
    r = generate_postponed_dashboard(vault, now_iso=NOW)
    _assert_links_valid(vault, r.path.read_text())


# ---------------------------------------------------------------------------
# 4. Commitments.md: project grouping
# ---------------------------------------------------------------------------

def test_commitments_groups_by_project():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-GP-001", title="Alpha task", project="alpha")
    _write(vault, action_id="ACT-GP-002", title="Beta task", project="beta")
    _write(vault, action_id="ACT-GP-003", title="No project task", project=None)
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert "### alpha" in content
    assert "### beta" in content
    assert "### No Project" in content


def test_commitments_projects_sorted_alphabetically():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-GP-010", title="Z project task", project="zzz")
    _write(vault, action_id="ACT-GP-011", title="A project task", project="aaa")
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    pos_aaa = content.index("### aaa")
    pos_zzz = content.index("### zzz")
    assert pos_aaa < pos_zzz, "expected 'aaa' project before 'zzz'"


def test_commitments_none_project_last():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-GP-020", title="Named project", project="alpha")
    _write(vault, action_id="ACT-GP-021", title="No project", project=None)
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    pos_alpha = content.index("### alpha")
    pos_none = content.index("### No Project")
    assert pos_alpha < pos_none, "expected named project before 'No Project'"


# ---------------------------------------------------------------------------
# 5. Commitments.md: done items
# ---------------------------------------------------------------------------

def test_commitments_done_section_contains_done_items():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-DN-001", title="Done item", status="done")
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert "## Done (1)" in content
    assert "Done item" in content


def test_commitments_open_not_in_done_section():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-DN-002", title="Open only item")
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    done_section = content.split("## Done")[1]
    assert "Open only item" not in done_section


# ---------------------------------------------------------------------------
# 6. Due Soon: overdue vs upcoming, window exclusion
# ---------------------------------------------------------------------------

def test_due_soon_overdue_appears_in_overdue_section():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-DS-001", title="Past due item", due_at=PAST_DUE)
    r = generate_due_soon_dashboard(vault, within_days=7, now_iso=NOW)
    content = r.path.read_text()
    overdue_section = content.split("## Overdue")[1].split("## Due within")[0]
    assert "Past due item" in overdue_section, "overdue item missing from Overdue section"


def test_due_soon_upcoming_appears_in_upcoming_section():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-DS-002", title="Soon due item", due_at=SOON_DUE)
    r = generate_due_soon_dashboard(vault, within_days=7, now_iso=NOW)
    content = r.path.read_text()
    # SOON_DUE is 3 days out, within 7 days but not overdue
    upcoming_section = content.split("## Due within")[1]
    assert "Soon due item" in upcoming_section, "upcoming item missing from Due within section"
    overdue_section = content.split("## Overdue")[1].split("## Due within")[0]
    assert "Soon due item" not in overdue_section


def test_due_soon_excludes_items_beyond_window():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-DS-003", title="Far future item", due_at=FAR_DUE)
    r = generate_due_soon_dashboard(vault, within_days=7, now_iso=NOW)
    content = r.path.read_text()
    assert "Far future item" not in content


def test_due_soon_excludes_done_items():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-DS-004", title="Done soon", due_at=SOON_DUE, status="done")
    r = generate_due_soon_dashboard(vault, within_days=7, now_iso=NOW)
    content = r.path.read_text()
    assert "Done soon" not in content


def test_due_soon_excludes_no_due_date():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-DS-005", title="No due date item", due_at=None)
    r = generate_due_soon_dashboard(vault, within_days=7, now_iso=NOW)
    content = r.path.read_text()
    assert "No due date item" not in content


def test_due_soon_written_count():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-DS-006", title="Overdue", due_at=PAST_DUE)
    _write(vault, action_id="ACT-DS-007", title="Soon", due_at=SOON_DUE)
    _write(vault, action_id="ACT-DS-008", title="Far", due_at=FAR_DUE)
    r = generate_due_soon_dashboard(vault, within_days=7, now_iso=NOW)
    assert r.written == 2, f"expected 2, got {r.written}"


# ---------------------------------------------------------------------------
# 7. Waiting On Me: requires_ack filter
# ---------------------------------------------------------------------------

def test_waiting_on_me_shows_requires_ack_items():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-WM-001", title="Needs ack", requires_ack=True)
    r = generate_waiting_on_me_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert "Needs ack" in content


def test_waiting_on_me_excludes_no_ack_items():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-WM-002", title="No ack required", requires_ack=False)
    r = generate_waiting_on_me_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert "No ack required" not in content


def test_waiting_on_me_excludes_done_items():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-WM-003", title="Done ack item", requires_ack=True, status="done")
    r = generate_waiting_on_me_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert "Done ack item" not in content


def test_waiting_on_me_written_count():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-WM-004", title="Ack 1", requires_ack=True)
    _write(vault, action_id="ACT-WM-005", title="Ack 2", requires_ack=True)
    _write(vault, action_id="ACT-WM-006", title="No ack", requires_ack=False)
    r = generate_waiting_on_me_dashboard(vault, now_iso=NOW)
    assert r.written == 2, f"expected 2, got {r.written}"


# ---------------------------------------------------------------------------
# 8. Postponed: postponed_until filter
# ---------------------------------------------------------------------------

def test_postponed_shows_postponed_items():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-PP-001", title="Snoozed task", postponed_until=FUTURE_POSTPONE)
    r = generate_postponed_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert "Snoozed task" in content


def test_postponed_excludes_non_postponed():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-PP-002", title="Active task", postponed_until=None)
    r = generate_postponed_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert "Active task" not in content


def test_postponed_excludes_done():
    vault, _td = _make_vault()
    _write(
        vault,
        action_id="ACT-PP-003",
        title="Done snoozed",
        postponed_until=FUTURE_POSTPONE,
        status="done",
    )
    r = generate_postponed_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert "Done snoozed" not in content


def test_postponed_table_shows_date():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-PP-004", title="Table date", postponed_until=FUTURE_POSTPONE)
    r = generate_postponed_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert "2026-05-01" in content  # formatted date from FUTURE_POSTPONE


def test_postponed_written_count():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-PP-005", title="P1", postponed_until=FUTURE_POSTPONE)
    _write(vault, action_id="ACT-PP-006", title="P2", postponed_until=FUTURE_POSTPONE)
    _write(vault, action_id="ACT-PP-007", title="Not postponed")
    r = generate_postponed_dashboard(vault, now_iso=NOW)
    assert r.written == 2, f"expected 2, got {r.written}"


# ---------------------------------------------------------------------------
# 9. No duplicates
# ---------------------------------------------------------------------------

def test_no_duplicate_entries_in_commitments():
    vault, _td = _make_vault()
    # Write the same action twice (second write updates; should still be one file)
    a = _write(vault, action_id="ACT-ND-001", title="Unique task", priority="normal")
    write_commitment_note(vault, ActionInput(
        action_id=a.action_id,
        capture_id=a.capture_id,
        title=a.title,
        created_at=a.created_at,
        project=a.project,
        status="open",
        priority="high",  # change to trigger update
        due_at=a.due_at,
        postponed_until=a.postponed_until,
        requires_ack=a.requires_ack,
        escalation_policy=a.escalation_policy,
        channels=a.channels,
        source_note=a.source_note,
    ))
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    # Count occurrences of the title in the Open section
    open_section = content.split("## Open")[1].split("## Done")[0]
    count = open_section.count("Unique task")
    assert count == 1, f"expected 1 occurrence, found {count}"


# ---------------------------------------------------------------------------
# 10. Idempotency
# ---------------------------------------------------------------------------

def test_idempotent_same_output_for_same_state():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-ID-001", title="Idem task", due_at=SOON_DUE)
    _write(vault, action_id="ACT-ID-002", title="Idem task 2", requires_ack=True)
    results_a = update_all_dashboards(vault, now_iso=NOW)
    results_b = update_all_dashboards(vault, now_iso=NOW)
    for ra, rb in zip(results_a, results_b):
        ca = ra.path.read_text()
        cb = rb.path.read_text()
        assert ca == cb, f"dashboard not idempotent: {ra.path.name}"


# ---------------------------------------------------------------------------
# 11. update_all_dashboards creates four files
# ---------------------------------------------------------------------------

def test_update_all_creates_four_files():
    # Task 26: update_all_dashboards now emits 8 files total.
    vault, _td = _make_vault()
    results = update_all_dashboards(vault, now_iso=NOW)
    assert len(results) == 8
    expected_names = {
        "Commitments.md",
        "Due Soon.md",
        "Waiting On Me.md",
        "Postponed.md",
        "Daily.md",
        "Weekly.md",
        "Stale.md",
        "Merge Candidates.md",
    }
    created = {r.path.name for r in results}
    assert created == expected_names, f"unexpected files: {created}"


def test_dashboards_dir_is_created():
    vault, _td = _make_vault()
    dashboards_dir = vault / DASHBOARDS_DIR
    assert not dashboards_dir.exists()
    update_all_dashboards(vault, now_iso=NOW)
    assert dashboards_dir.is_dir()


# ---------------------------------------------------------------------------
# 12. Table wikilinks escape the pipe
# ---------------------------------------------------------------------------

def test_table_wikilinks_escape_pipe_in_done_section():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-TBL-001", title="Done table link", status="done")
    r = generate_commitments_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    done_section = content.split("## Done")[1]
    # In a table cell the wikilink must use \| not |
    assert r"\\|" in done_section or r"\|" in done_section, (
        "table wikilink missing escaped pipe (\\|) in Done section"
    )


def test_table_wikilinks_escape_pipe_in_postponed():
    vault, _td = _make_vault()
    _write(vault, action_id="ACT-TBL-002", title="Postponed table link", postponed_until=FUTURE_POSTPONE)
    r = generate_postponed_dashboard(vault, now_iso=NOW)
    content = r.path.read_text()
    assert r"\|" in content, "table wikilink missing escaped pipe (\\|) in Postponed"


# ---------------------------------------------------------------------------
# 13. Frontmatter structure
# ---------------------------------------------------------------------------

def test_frontmatter_generated_at_matches_injected_now():
    vault, _td = _make_vault()
    results = update_all_dashboards(vault, now_iso=NOW)
    for r in results:
        content = r.path.read_text()
        assert f"generated_at: {NOW}" in content, (
            f"{r.path.name}: generated_at mismatch\n{content[:300]}"
        )


def test_frontmatter_type_is_dashboard():
    vault, _td = _make_vault()
    results = update_all_dashboards(vault, now_iso=NOW)
    for r in results:
        content = r.path.read_text()
        assert "type: dashboard" in content, f"{r.path.name}: missing 'type: dashboard'"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test("empty vault: all four dashboards created", test_empty_vault_all_four_dashboards)
    test("empty vault: written counts are zero", test_empty_vault_written_counts_are_zero)
    test("wikilinks have no .md extension", test_wikilinks_have_no_md_extension)
    test("wikilinks include full vault-relative path", test_wikilinks_include_full_vault_relative_path)
    test("commitments dashboard links are valid", test_commitments_dashboard_links_are_valid)
    test("due soon dashboard links are valid", test_due_soon_dashboard_links_are_valid)
    test("waiting on me dashboard links are valid", test_waiting_on_me_dashboard_links_are_valid)
    test("postponed dashboard links are valid", test_postponed_dashboard_links_are_valid)
    test("commitments groups by project", test_commitments_groups_by_project)
    test("commitments projects sorted alphabetically", test_commitments_projects_sorted_alphabetically)
    test("commitments None project last", test_commitments_none_project_last)
    test("commitments done section contains done items", test_commitments_done_section_contains_done_items)
    test("commitments open not in done section", test_commitments_open_not_in_done_section)
    test("due soon overdue in overdue section", test_due_soon_overdue_appears_in_overdue_section)
    test("due soon upcoming in upcoming section", test_due_soon_upcoming_appears_in_upcoming_section)
    test("due soon excludes items beyond window", test_due_soon_excludes_items_beyond_window)
    test("due soon excludes done items", test_due_soon_excludes_done_items)
    test("due soon excludes no due date", test_due_soon_excludes_no_due_date)
    test("due soon written count", test_due_soon_written_count)
    test("waiting on me shows requires_ack items", test_waiting_on_me_shows_requires_ack_items)
    test("waiting on me excludes no-ack items", test_waiting_on_me_excludes_no_ack_items)
    test("waiting on me excludes done items", test_waiting_on_me_excludes_done_items)
    test("waiting on me written count", test_waiting_on_me_written_count)
    test("postponed shows postponed items", test_postponed_shows_postponed_items)
    test("postponed excludes non-postponed", test_postponed_excludes_non_postponed)
    test("postponed excludes done", test_postponed_excludes_done)
    test("postponed table shows date", test_postponed_table_shows_date)
    test("postponed written count", test_postponed_written_count)
    test("no duplicate entries in commitments", test_no_duplicate_entries_in_commitments)
    test("idempotent: same output for same state", test_idempotent_same_output_for_same_state)
    test("update_all creates four files", test_update_all_creates_four_files)
    test("Dashboards/ dir is created", test_dashboards_dir_is_created)
    test("table wikilinks escape pipe in done section", test_table_wikilinks_escape_pipe_in_done_section)
    test("table wikilinks escape pipe in postponed", test_table_wikilinks_escape_pipe_in_postponed)
    test("frontmatter generated_at matches injected now", test_frontmatter_generated_at_matches_injected_now)
    test("frontmatter type is dashboard", test_frontmatter_type_is_dashboard)

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")
    sys.exit(0 if FAIL == 0 else 1)
