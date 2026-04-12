#!/usr/bin/env python3
"""Tests for the commitment notes module (commitment_notes.py).

Uses tempfile for test vaults and plain assert statements.
Run with: python3 scripts/commitment_notes_test.py
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.commitment_notes import (
    ActionInput,
    FOLLOWUP_BEGIN,
    FOLLOWUP_END,
    USER_NOTES_BEGIN,
    USER_NOTES_END,
    find_commitment_note,
    parse_frontmatter,
    render_commitment_note,
    resolve_commitment_path,
    write_commitment_note,
)

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
        traceback.print_exc(limit=3)
        FAIL += 1


def _make_vault() -> tuple[Path, tempfile.TemporaryDirectory]:
    td = tempfile.TemporaryDirectory(prefix="obsx_cn_test_")
    vault = Path(td.name)
    return vault, td


def _sample_action(**overrides) -> ActionInput:
    base = dict(
        action_id="ACT01HXYZABCDE12345",
        capture_id="CAP01HXYZABCDE99999",
        title="Ship the commitment notes renderer",
        created_at="2026-04-12T17:30:00+00:00",
        project="obsidian-connector",
        status="open",
        priority="normal",
        due_at="2026-04-15T17:00:00+00:00",
        postponed_until=None,
        requires_ack=True,
        escalation_policy="push-then-sms",
        channels=["push", "sms"],
        source_note="Inbox/Voice Captures/2026/04/2026-04-12T17-00-00Z_capture.md",
        description="Implement the renderer so Task 6 can push commitments into the vault.",
    )
    base.update(overrides)
    return ActionInput(**base)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def test_resolve_path_open_uses_created_month():
    vault, _td = _make_vault()
    action = _sample_action()
    path = resolve_commitment_path(vault, action)
    rel = path.relative_to(vault).as_posix()
    assert rel.startswith("Commitments/Open/2026/04/"), rel
    assert rel.endswith(".md"), rel


def test_resolve_path_done_branch():
    vault, _td = _make_vault()
    action = _sample_action(status="done", completed_at="2026-05-01T09:00:00+00:00")
    path = resolve_commitment_path(vault, action)
    rel = path.relative_to(vault).as_posix()
    assert rel.startswith("Commitments/Done/2026/04/"), rel


def test_resolve_path_includes_slug_and_action_suffix():
    vault, _td = _make_vault()
    action = _sample_action(title="A totally new commitment")
    path = resolve_commitment_path(vault, action)
    fname = path.name
    assert "a-totally-new-commitment" in fname, fname
    # last 7 chars of action_id (lowercased) used as suffix for uniqueness
    suffix = "de12345"  # lowercased last 7 of the sample id
    assert suffix in fname.lower(), fname


def test_resolve_path_handles_emojis_and_punctuation():
    vault, _td = _make_vault()
    action = _sample_action(title="Review 🚀 the Q2/Q3 plan!!")
    path = resolve_commitment_path(vault, action)
    fname = path.name
    assert "review" in fname.lower()
    assert "q2-q3" in fname.lower() or "q2q3" in fname.lower()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def test_render_contains_all_required_frontmatter_fields():
    action = _sample_action()
    content = render_commitment_note(action, existing_content=None)
    fm = parse_frontmatter(content)
    required = [
        "type", "action_id", "capture_id", "title", "project", "status",
        "priority", "due_at", "postponed_until", "requires_ack",
        "escalation_policy", "channels", "source_note",
        "service_last_synced_at",
    ]
    for key in required:
        assert key in fm, f"missing frontmatter key: {key}"
    assert fm["type"] == "commitment"
    assert fm["action_id"] == action.action_id
    assert fm["status"] == "open"
    assert fm["requires_ack"] == "true"


def test_render_serializes_none_as_null():
    action = _sample_action(due_at=None, postponed_until=None, project=None)
    content = render_commitment_note(action, existing_content=None)
    fm = parse_frontmatter(content)
    assert fm["due_at"] == "null"
    assert fm["postponed_until"] == "null"
    assert fm["project"] == "null"


def test_render_channels_as_yaml_flow_list():
    action = _sample_action(channels=["push", "sms", "email"])
    content = render_commitment_note(action, existing_content=None)
    assert "channels: [push, sms, email]" in content, content


def test_render_channels_empty_list():
    action = _sample_action(channels=[])
    content = render_commitment_note(action, existing_content=None)
    assert "channels: []" in content, content


def test_render_title_escapes_double_quotes():
    action = _sample_action(title='He said "ship it"')
    content = render_commitment_note(action, existing_content=None)
    fm = parse_frontmatter(content)
    assert fm["title"] == 'He said "ship it"', fm["title"]


def test_render_title_with_colon_is_quoted():
    action = _sample_action(title="Urgent: ship the thing")
    content = render_commitment_note(action, existing_content=None)
    fm = parse_frontmatter(content)
    assert fm["title"] == "Urgent: ship the thing"


def test_render_body_has_h1_title():
    action = _sample_action()
    content = render_commitment_note(action, existing_content=None)
    assert "\n# Ship the commitment notes renderer\n" in content


def test_render_body_has_metadata_section():
    action = _sample_action()
    content = render_commitment_note(action, existing_content=None)
    assert "## Metadata" in content
    assert "Priority: normal" in content
    assert "Due: 2026-04-15T17:00:00+00:00" in content


def test_render_body_links_source_capture():
    action = _sample_action()
    content = render_commitment_note(action, existing_content=None)
    assert "## Source Capture" in content
    # Wikilink without the .md extension
    assert (
        "[[Inbox/Voice Captures/2026/04/2026-04-12T17-00-00Z_capture|Source capture]]"
        in content
    )


def test_render_body_has_followup_log_fences():
    action = _sample_action()
    content = render_commitment_note(action, existing_content=None)
    assert FOLLOWUP_BEGIN in content
    assert FOLLOWUP_END in content
    # Seed entry for creation
    assert "note created" in content
    assert "status=open" in content


def test_render_body_has_user_notes_fences():
    action = _sample_action()
    content = render_commitment_note(action, existing_content=None)
    assert USER_NOTES_BEGIN in content
    assert USER_NOTES_END in content


def test_render_preserves_user_notes_section_on_update():
    action = _sample_action()
    initial = render_commitment_note(action, existing_content=None)
    # Splice user-edited content into the user notes block
    user_block = (
        USER_NOTES_BEGIN
        + "\n- Reminder: coordinate with Mario on timing.\n- Blocked by Task 4 first.\n"
        + USER_NOTES_END
    )
    old_block_start = initial.index(USER_NOTES_BEGIN)
    old_block_end = initial.index(USER_NOTES_END) + len(USER_NOTES_END)
    edited = initial[:old_block_start] + user_block + initial[old_block_end:]

    # Re-render with updated action (priority change) against the edited file
    updated_action = _sample_action(priority="high")
    rerendered = render_commitment_note(updated_action, existing_content=edited)
    assert "Reminder: coordinate with Mario" in rerendered
    assert "Blocked by Task 4 first." in rerendered


def test_render_preserves_followup_log_entries_on_update():
    action = _sample_action()
    first = render_commitment_note(action, existing_content=None)
    # Now change status and re-render
    done_action = _sample_action(
        status="done",
        completed_at="2026-04-13T10:00:00+00:00",
    )
    second = render_commitment_note(done_action, existing_content=first)
    # The seed "note created" entry must still appear
    assert second.count("note created") == 1, second
    # Plus a new entry for the transition
    assert "status change: open -> done" in second, second


def test_render_followup_entries_appear_in_chronological_order():
    action = _sample_action()
    content_v1 = render_commitment_note(action, existing_content=None)
    action_v2 = _sample_action(priority="high")
    content_v2 = render_commitment_note(action_v2, existing_content=content_v1)
    action_v3 = _sample_action(priority="high", status="done")
    content_v3 = render_commitment_note(action_v3, existing_content=content_v2)

    # Extract the follow-up log block
    start = content_v3.index(FOLLOWUP_BEGIN) + len(FOLLOWUP_BEGIN)
    end = content_v3.index(FOLLOWUP_END)
    block = content_v3[start:end]
    # created -> priority -> status transition ordering
    i_created = block.index("note created")
    i_priority = block.index("priority change")
    i_status = block.index("status change")
    assert i_created < i_priority < i_status, block


def test_render_no_noop_log_entry_on_identical_resync():
    action = _sample_action()
    first = render_commitment_note(action, existing_content=None)
    second = render_commitment_note(action, existing_content=first)
    # Nothing changed -> no new log entry; sync timestamp updates in frontmatter
    assert second.count("note created") == 1
    assert "priority change" not in second
    assert "status change" not in second


def test_render_sync_timestamp_updates():
    action_v1 = _sample_action()
    content_v1 = render_commitment_note(
        action_v1, existing_content=None, now_iso="2026-04-12T17:30:00+00:00"
    )
    content_v2 = render_commitment_note(
        action_v1, existing_content=content_v1, now_iso="2026-04-13T09:00:00+00:00"
    )
    fm1 = parse_frontmatter(content_v1)
    fm2 = parse_frontmatter(content_v2)
    assert fm1["service_last_synced_at"] == "2026-04-12T17:30:00+00:00"
    assert fm2["service_last_synced_at"] == "2026-04-13T09:00:00+00:00"


# ---------------------------------------------------------------------------
# Writer (end-to-end)
# ---------------------------------------------------------------------------

def test_write_creates_file_on_first_call():
    vault, _td = _make_vault()
    action = _sample_action()
    result = write_commitment_note(vault, action)
    assert result.path.is_file()
    assert result.created is True
    assert result.moved_from is None
    rel = result.path.relative_to(vault).as_posix()
    assert rel.startswith("Commitments/Open/2026/04/")


def test_write_idempotent_on_repeated_call():
    vault, _td = _make_vault()
    action = _sample_action()
    first = write_commitment_note(vault, action)
    second = write_commitment_note(vault, action)
    assert first.path == second.path
    assert second.created is False
    # No duplicate file anywhere in the Commitments tree
    all_notes = list((vault / "Commitments").rglob("*.md"))
    assert len(all_notes) == 1, [str(p) for p in all_notes]


def test_write_moves_file_on_status_transition():
    vault, _td = _make_vault()
    action_open = _sample_action()
    first = write_commitment_note(vault, action_open)
    action_done = _sample_action(
        status="done", completed_at="2026-04-13T10:00:00+00:00"
    )
    second = write_commitment_note(vault, action_done)
    assert first.path != second.path, (first.path, second.path)
    assert not first.path.exists(), "old Open file should be gone"
    assert second.path.is_file()
    assert second.moved_from == first.path
    rel = second.path.relative_to(vault).as_posix()
    assert rel.startswith("Commitments/Done/")


def test_write_preserves_user_notes_across_sync():
    vault, _td = _make_vault()
    action = _sample_action()
    first = write_commitment_note(vault, action)
    # User edits the note notes section
    text = first.path.read_text(encoding="utf-8")
    injected = text.replace(
        USER_NOTES_BEGIN,
        USER_NOTES_BEGIN + "\n- user added this line\n",
        1,
    )
    first.path.write_text(injected, encoding="utf-8")

    # Resync with a status change
    action_done = _sample_action(
        status="done", completed_at="2026-04-13T10:00:00+00:00"
    )
    second = write_commitment_note(vault, action_done)
    final_text = second.path.read_text(encoding="utf-8")
    assert "user added this line" in final_text


def test_write_appends_log_entry_on_change():
    vault, _td = _make_vault()
    action = _sample_action()
    write_commitment_note(vault, action)
    action_v2 = _sample_action(priority="high")
    second = write_commitment_note(vault, action_v2)
    text = second.path.read_text(encoding="utf-8")
    assert "priority change: normal -> high" in text


def test_find_commitment_note_by_action_id():
    vault, _td = _make_vault()
    action = _sample_action()
    res = write_commitment_note(vault, action)
    found = find_commitment_note(vault, action.action_id)
    assert found == res.path


def test_find_commitment_note_returns_none_when_missing():
    vault, _td = _make_vault()
    assert find_commitment_note(vault, "ACT_DOES_NOT_EXIST") is None


def test_write_rejects_blank_action_id():
    vault, _td = _make_vault()
    action = _sample_action(action_id="")
    try:
        write_commitment_note(vault, action)
    except ValueError:
        return
    raise AssertionError("expected ValueError for blank action_id")


def test_write_rejects_unknown_status():
    vault, _td = _make_vault()
    action = _sample_action(status="archived")
    try:
        write_commitment_note(vault, action)
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown status")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    test("resolve_path Open uses created month", test_resolve_path_open_uses_created_month)
    test("resolve_path Done branch", test_resolve_path_done_branch)
    test("resolve_path includes slug + action id suffix", test_resolve_path_includes_slug_and_action_suffix)
    test("resolve_path handles emojis and punctuation", test_resolve_path_handles_emojis_and_punctuation)
    test("render contains all required frontmatter fields", test_render_contains_all_required_frontmatter_fields)
    test("render serializes None as null", test_render_serializes_none_as_null)
    test("render channels as flow list", test_render_channels_as_yaml_flow_list)
    test("render channels empty list", test_render_channels_empty_list)
    test("render title escapes double quotes", test_render_title_escapes_double_quotes)
    test("render title with colon is quoted", test_render_title_with_colon_is_quoted)
    test("render body has H1 title", test_render_body_has_h1_title)
    test("render body has Metadata section", test_render_body_has_metadata_section)
    test("render body links source capture", test_render_body_links_source_capture)
    test("render body has follow-up log fences", test_render_body_has_followup_log_fences)
    test("render body has user notes fences", test_render_body_has_user_notes_fences)
    test("render preserves user notes section on update", test_render_preserves_user_notes_section_on_update)
    test("render preserves follow-up log entries on update", test_render_preserves_followup_log_entries_on_update)
    test("render follow-up entries in chronological order", test_render_followup_entries_appear_in_chronological_order)
    test("render no-op log on identical resync", test_render_no_noop_log_entry_on_identical_resync)
    test("render sync timestamp updates", test_render_sync_timestamp_updates)
    test("write creates file on first call", test_write_creates_file_on_first_call)
    test("write idempotent on repeated call", test_write_idempotent_on_repeated_call)
    test("write moves file on status transition", test_write_moves_file_on_status_transition)
    test("write preserves user notes across sync", test_write_preserves_user_notes_across_sync)
    test("write appends log entry on change", test_write_appends_log_entry_on_change)
    test("find_commitment_note by action_id", test_find_commitment_note_by_action_id)
    test("find_commitment_note returns None when missing", test_find_commitment_note_returns_none_when_missing)
    test("write rejects blank action_id", test_write_rejects_blank_action_id)
    test("write rejects unknown status", test_write_rejects_unknown_status)

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed ({PASS + FAIL} total assertions)")
    print(f"{'=' * 60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
