#!/usr/bin/env python3
"""Tests for commitment_ops.py.

Covers:
- list_commitments (all, status filter, project filter, priority filter)
- get_commitment (found, not found)
- list_due_soon (within window, overdue, no results)
- mark_commitment_done (status transition, file move, idempotent)
- postpone_commitment (sets field, follow-up log entry)
- add_commitment_reason (appends to user-notes block)
- sync_commitments_from_service (service not configured, service unavailable,
  service returns malformed payload, well-formed payload written to vault)

Run with: python3 scripts/commitment_ops_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.commitment_notes import (
    USER_NOTES_BEGIN,
    USER_NOTES_END,
    find_commitment_note,
    parse_frontmatter,
    write_commitment_note,
    ActionInput,
)
from obsidian_connector.commitment_ops import (
    add_commitment_reason,
    get_commitment,
    list_commitments,
    list_due_soon,
    mark_commitment_done,
    postpone_commitment,
    sync_commitments_from_service,
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
        traceback.print_exc(limit=4)
        FAIL += 1


def _make_vault():
    td = tempfile.TemporaryDirectory(prefix="obsx_ops_test_")
    return Path(td.name), td


def _sample_action(**overrides) -> ActionInput:
    now = datetime.now(timezone.utc).isoformat()
    base = dict(
        action_id="ACT-OPS-TEST-0000001",
        capture_id="CAP-OPS-TEST-9999999",
        title="Deploy the ops module",
        created_at="2026-04-12T10:00:00+00:00",
        project="obsidian-connector",
        status="open",
        priority="normal",
        due_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        postponed_until=None,
        requires_ack=False,
        escalation_policy=None,
        channels=[],
        source_note=None,
        description="Wire up the commitment ops module.",
    )
    base.update(overrides)
    return ActionInput(**base)


def _write_sample(vault: Path, **overrides) -> ActionInput:
    action = _sample_action(**overrides)
    write_commitment_note(vault, action)
    return action


# ---------------------------------------------------------------------------
# list_commitments
# ---------------------------------------------------------------------------

def test_list_returns_empty_when_no_commitments_dir():
    vault, _td = _make_vault()
    result = list_commitments(vault)
    assert result == [], result


def test_list_returns_all_items():
    vault, _td = _make_vault()
    a1 = _write_sample(vault, action_id="ACT001", title="First task")
    a2 = _write_sample(vault, action_id="ACT002", title="Second task", project="other")
    result = list_commitments(vault)
    ids = {r["action_id"] for r in result}
    assert "ACT001" in ids
    assert "ACT002" in ids


def test_list_filters_by_status():
    vault, _td = _make_vault()
    _write_sample(vault, action_id="ACT-OPEN", status="open")
    _write_sample(vault, action_id="ACT-DONE", status="done", completed_at="2026-04-13T09:00:00+00:00")
    open_items = list_commitments(vault, status="open")
    done_items = list_commitments(vault, status="done")
    assert all(i["status"] == "open" for i in open_items)
    assert all(i["status"] == "done" for i in done_items)
    assert len(open_items) == 1
    assert len(done_items) == 1


def test_list_filters_by_project():
    vault, _td = _make_vault()
    _write_sample(vault, action_id="ACT-P1", project="alpha")
    _write_sample(vault, action_id="ACT-P2", project="beta")
    result = list_commitments(vault, project="alpha")
    assert len(result) == 1
    assert result[0]["action_id"] == "ACT-P1"


def test_list_filters_by_project_case_insensitive():
    vault, _td = _make_vault()
    _write_sample(vault, action_id="ACT-CASE", project="Obsidian-Connector")
    result = list_commitments(vault, project="obsidian-connector")
    assert len(result) == 1


def test_list_filters_by_priority():
    vault, _td = _make_vault()
    _write_sample(vault, action_id="ACT-HIGH", priority="high")
    _write_sample(vault, action_id="ACT-NORM", priority="normal")
    result = list_commitments(vault, priority="high")
    assert len(result) == 1
    assert result[0]["priority"] == "high"


def test_list_summary_has_expected_keys():
    vault, _td = _make_vault()
    _write_sample(vault)
    result = list_commitments(vault)
    assert len(result) == 1
    keys = set(result[0].keys())
    expected = {"action_id", "title", "status", "priority", "project", "due_at",
                "postponed_until", "requires_ack", "path"}
    assert expected <= keys, f"missing keys: {expected - keys}"


# ---------------------------------------------------------------------------
# get_commitment
# ---------------------------------------------------------------------------

def test_get_returns_none_when_not_found():
    vault, _td = _make_vault()
    assert get_commitment(vault, "NONEXISTENT") is None


def test_get_returns_correct_item():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    item = get_commitment(vault, action.action_id)
    assert item is not None
    assert item["action_id"] == action.action_id
    assert item["title"] == action.title
    assert item["status"] == "open"


# ---------------------------------------------------------------------------
# list_due_soon
# ---------------------------------------------------------------------------

def test_due_soon_returns_empty_when_nothing_due():
    vault, _td = _make_vault()
    far_future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    _write_sample(vault, due_at=far_future)
    result = list_due_soon(vault, within_days=3)
    assert result == [], result


def test_due_soon_returns_item_within_window():
    vault, _td = _make_vault()
    soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    _write_sample(vault, action_id="ACT-SOON", due_at=soon)
    result = list_due_soon(vault, within_days=2)
    assert len(result) == 1
    assert result[0]["action_id"] == "ACT-SOON"


def test_due_soon_marks_overdue():
    vault, _td = _make_vault()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_sample(vault, action_id="ACT-PAST", due_at=past)
    result = list_due_soon(vault, within_days=1)
    assert len(result) == 1
    assert result[0]["overdue"] is True


def test_due_soon_excludes_done_items():
    vault, _td = _make_vault()
    soon = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    _write_sample(vault, action_id="ACT-DONE-DUE", status="done",
                  completed_at="2026-04-13T09:00:00+00:00", due_at=soon)
    result = list_due_soon(vault, within_days=2)
    assert all(r["action_id"] != "ACT-DONE-DUE" for r in result)


def test_due_soon_sorted_earliest_first():
    vault, _td = _make_vault()
    t1 = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    t2 = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    _write_sample(vault, action_id="ACT-LATER", due_at=t1)
    _write_sample(vault, action_id="ACT-SOONER", due_at=t2)
    result = list_due_soon(vault, within_days=2)
    assert result[0]["action_id"] == "ACT-SOONER"
    assert result[1]["action_id"] == "ACT-LATER"


# ---------------------------------------------------------------------------
# mark_commitment_done
# ---------------------------------------------------------------------------

def test_mark_done_raises_when_not_found():
    vault, _td = _make_vault()
    try:
        mark_commitment_done(vault, "NONEXISTENT")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_mark_done_updates_status_and_moves_file():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    open_path = find_commitment_note(vault, action.action_id)
    assert open_path is not None
    assert "Open" in str(open_path)

    result = mark_commitment_done(vault, action.action_id)
    assert result["status"] == "done"
    assert result["previous_status"] == "open"
    assert result["moved_from"] is not None

    done_path = find_commitment_note(vault, action.action_id)
    assert done_path is not None
    assert "Done" in str(done_path)
    assert not open_path.exists()


def test_mark_done_records_completed_at():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    ts = "2026-04-13T10:00:00+00:00"
    result = mark_commitment_done(vault, action.action_id, completed_at=ts)
    assert result["completed_at"] == ts


def test_mark_done_appends_followup_log_entry():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    mark_commitment_done(vault, action.action_id)
    done_path = find_commitment_note(vault, action.action_id)
    content = done_path.read_text(encoding="utf-8")
    assert "status change: open -> done" in content


def test_mark_done_no_service_sync_when_not_configured():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    saved_url = os.environ.pop("OBSIDIAN_CAPTURE_SERVICE_URL", None)
    try:
        result = mark_commitment_done(vault, action.action_id)
        assert "service_sync" not in result
    finally:
        if saved_url:
            os.environ["OBSIDIAN_CAPTURE_SERVICE_URL"] = saved_url


# ---------------------------------------------------------------------------
# postpone_commitment
# ---------------------------------------------------------------------------

def test_postpone_raises_when_not_found():
    vault, _td = _make_vault()
    try:
        postpone_commitment(vault, "NONEXISTENT", "2026-05-01T00:00:00+00:00")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_postpone_updates_frontmatter():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    until = "2026-05-01T00:00:00+00:00"
    result = postpone_commitment(vault, action.action_id, postponed_until=until)
    assert result["postponed_until"] == until

    path = find_commitment_note(vault, action.action_id)
    content = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    assert fm["postponed_until"] == until


def test_postpone_appends_followup_log_entry():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    until = "2026-05-01T00:00:00+00:00"
    postpone_commitment(vault, action.action_id, postponed_until=until)
    path = find_commitment_note(vault, action.action_id)
    content = path.read_text(encoding="utf-8")
    assert "postponed_until change" in content


def test_postpone_no_service_sync_when_not_configured():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    saved_url = os.environ.pop("OBSIDIAN_CAPTURE_SERVICE_URL", None)
    try:
        result = postpone_commitment(vault, action.action_id, "2026-05-01T00:00:00+00:00")
        assert "service_sync" not in result
    finally:
        if saved_url:
            os.environ["OBSIDIAN_CAPTURE_SERVICE_URL"] = saved_url


# ---------------------------------------------------------------------------
# add_commitment_reason
# ---------------------------------------------------------------------------

def test_add_reason_raises_on_empty_reason():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    try:
        add_commitment_reason(vault, action.action_id, "")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_add_reason_raises_when_not_found():
    vault, _td = _make_vault()
    try:
        add_commitment_reason(vault, "NONEXISTENT", "some reason")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_add_reason_appends_to_user_notes():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    result = add_commitment_reason(vault, action.action_id, "Blocked by external review")
    assert result["reason_added"] == "Blocked by external review"

    path = find_commitment_note(vault, action.action_id)
    content = path.read_text(encoding="utf-8")
    assert "Blocked by external review" in content
    # Must be inside the user-notes block
    begin = content.find(USER_NOTES_BEGIN)
    end = content.find(USER_NOTES_END)
    block = content[begin:end]
    assert "Blocked by external review" in block


def test_add_reason_preserves_existing_user_notes():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    add_commitment_reason(vault, action.action_id, "First note")
    add_commitment_reason(vault, action.action_id, "Second note")

    path = find_commitment_note(vault, action.action_id)
    content = path.read_text(encoding="utf-8")
    assert "First note" in content
    assert "Second note" in content


def test_add_reason_result_has_expected_keys():
    vault, _td = _make_vault()
    action = _write_sample(vault)
    result = add_commitment_reason(vault, action.action_id, "test reason")
    for key in ("action_id", "reason_added", "timestamp", "path", "status"):
        assert key in result, f"missing key: {key}"


# ---------------------------------------------------------------------------
# sync_commitments_from_service (local/degraded paths only -- no live HTTP)
# ---------------------------------------------------------------------------

def test_sync_returns_error_when_not_configured():
    saved_url = os.environ.pop("OBSIDIAN_CAPTURE_SERVICE_URL", None)
    vault, _td = _make_vault()
    try:
        result = sync_commitments_from_service(vault)
        assert result["ok"] is False
        assert "not configured" in result["error"]
    finally:
        if saved_url:
            os.environ["OBSIDIAN_CAPTURE_SERVICE_URL"] = saved_url


def test_sync_rejects_non_http_scheme():
    vault, _td = _make_vault()
    result = sync_commitments_from_service(vault, service_url="file:///etc/passwd")
    assert result["ok"] is False
    assert "http" in result["error"].lower() or "scheme" in result["error"].lower()


def test_sync_returns_error_on_unreachable_service():
    vault, _td = _make_vault()
    # Use a localhost port that should not be listening
    result = sync_commitments_from_service(vault, service_url="http://127.0.0.1:19999")
    assert result["ok"] is False
    assert "error" in result


def test_sync_writes_actions_from_payload(monkeypatch_env=None):
    """Simulate a service response by monkey-patching http.client."""
    import http.client
    import json as _json
    import io

    vault, _td = _make_vault()

    fake_actions = [
        {
            "action_id": "ACT-SYNC-001",
            "capture_id": "CAP-SYNC-001",
            "title": "Synced action one",
            "created_at": "2026-04-12T10:00:00+00:00",
            "status": "open",
            "priority": "normal",
        },
        {
            "action_id": "ACT-SYNC-002",
            "capture_id": "CAP-SYNC-002",
            "title": "Synced action two",
            "created_at": "2026-04-12T11:00:00+00:00",
            "status": "open",
            "priority": "high",
        },
    ]

    class _FakeResponse:
        status = 200
        def read(self):
            return _json.dumps(fake_actions).encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class _FakeConn:
        def __init__(self, *a, **kw): pass
        def request(self, *a, **kw): pass
        def getresponse(self): return _FakeResponse()
        def close(self): pass

    orig_http = http.client.HTTPConnection
    http.client.HTTPConnection = _FakeConn
    try:
        result = sync_commitments_from_service(vault, service_url="http://fake-service.local")
        assert result["ok"] is True, result
        assert result["synced"] == 2
        assert result["errors"] == []
        # Verify notes were written to vault
        assert find_commitment_note(vault, "ACT-SYNC-001") is not None
        assert find_commitment_note(vault, "ACT-SYNC-002") is not None
    finally:
        http.client.HTTPConnection = orig_http


def test_sync_partial_failure_does_not_abort():
    """A bad action in the payload should record an error but continue writing others."""
    import http.client
    import json as _json

    vault, _td = _make_vault()

    fake_payload = [
        # Invalid: missing action_id
        {"title": "Bad action -- no id", "status": "open"},
        {
            "action_id": "ACT-PARTIAL-GOOD",
            "capture_id": "CAP-PARTIAL-GOOD",
            "title": "Good action",
            "created_at": "2026-04-12T10:00:00+00:00",
            "status": "open",
            "priority": "normal",
        },
    ]

    class _FakeResponse:
        status = 200
        def read(self):
            return _json.dumps(fake_payload).encode("utf-8")

    class _FakeConn:
        def __init__(self, *a, **kw): pass
        def request(self, *a, **kw): pass
        def getresponse(self): return _FakeResponse()
        def close(self): pass

    orig_http = http.client.HTTPConnection
    http.client.HTTPConnection = _FakeConn
    try:
        result = sync_commitments_from_service(vault, service_url="http://fake-service.local")
        assert result["ok"] is True, result
        assert result["synced"] == 1
        assert len(result["errors"]) == 1
        assert find_commitment_note(vault, "ACT-PARTIAL-GOOD") is not None
    finally:
        http.client.HTTPConnection = orig_http


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    test("list empty vault", test_list_returns_empty_when_no_commitments_dir)
    test("list returns all items", test_list_returns_all_items)
    test("list filters by status", test_list_filters_by_status)
    test("list filters by project", test_list_filters_by_project)
    test("list filters by project case-insensitive", test_list_filters_by_project_case_insensitive)
    test("list filters by priority", test_list_filters_by_priority)
    test("list summary has expected keys", test_list_summary_has_expected_keys)

    test("get returns None when not found", test_get_returns_none_when_not_found)
    test("get returns correct item", test_get_returns_correct_item)

    test("due_soon returns empty when nothing due", test_due_soon_returns_empty_when_nothing_due)
    test("due_soon returns item within window", test_due_soon_returns_item_within_window)
    test("due_soon marks overdue", test_due_soon_marks_overdue)
    test("due_soon excludes done items", test_due_soon_excludes_done_items)
    test("due_soon sorted earliest first", test_due_soon_sorted_earliest_first)

    test("mark_done raises when not found", test_mark_done_raises_when_not_found)
    test("mark_done updates status and moves file", test_mark_done_updates_status_and_moves_file)
    test("mark_done records completed_at", test_mark_done_records_completed_at)
    test("mark_done appends follow-up log entry", test_mark_done_appends_followup_log_entry)
    test("mark_done no service_sync when not configured", test_mark_done_no_service_sync_when_not_configured)

    test("postpone raises when not found", test_postpone_raises_when_not_found)
    test("postpone updates frontmatter", test_postpone_updates_frontmatter)
    test("postpone appends follow-up log entry", test_postpone_appends_followup_log_entry)
    test("postpone no service_sync when not configured", test_postpone_no_service_sync_when_not_configured)

    test("add_reason raises on empty reason", test_add_reason_raises_on_empty_reason)
    test("add_reason raises when not found", test_add_reason_raises_when_not_found)
    test("add_reason appends to user-notes", test_add_reason_appends_to_user_notes)
    test("add_reason preserves existing user notes", test_add_reason_preserves_existing_user_notes)
    test("add_reason result has expected keys", test_add_reason_result_has_expected_keys)

    test("sync returns error when not configured", test_sync_returns_error_when_not_configured)
    test("sync rejects non-http scheme", test_sync_rejects_non_http_scheme)
    test("sync returns error on unreachable service", test_sync_returns_error_on_unreachable_service)
    test("sync writes actions from payload", test_sync_writes_actions_from_payload)
    test("sync partial failure continues", test_sync_partial_failure_does_not_abort)

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    print(f"{'=' * 60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
