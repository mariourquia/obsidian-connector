#!/usr/bin/env python3
"""Tests for the scheduler engine (scheduler.py).

Uses tempfile for status file isolation and plain assert statements.
No pytest dependency required.  Run with:

    python3 scripts/scheduler_test.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.scheduler import (
    EventTrigger,
    ScheduleEntry,
    ScheduleStatus,
    Scheduler,
)

PASS = 0
FAIL = 0


def test(label: str, fn):
    """Run a single test function and track pass/fail."""
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    try:
        fn()
        print(f"  OK")
        PASS += 1
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        FAIL += 1


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _tmp_status_path() -> tuple[Path, tempfile.TemporaryDirectory]:
    """Create a temporary directory and return a status file path inside it."""
    td = tempfile.TemporaryDirectory(prefix="obsx_sched_test_")
    return Path(td.name) / "schedule_status.json", td


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_default_schedules_loaded():
    """Scheduler loads default schedules when config has no 'schedules' key."""
    sched = Scheduler(config={})
    entries = sched.list_schedules()
    assert len(entries) == 3, f"expected 3 default schedules, got {len(entries)}"
    names = {e.name for e in entries}
    assert names == {"morning", "evening", "weekly"}, f"wrong default names: {names}"


def test_custom_schedules_from_config():
    """Scheduler loads custom schedules from config."""
    config = {
        "schedules": [
            {
                "name": "nightly",
                "schedule_type": "custom",
                "tool_chain": ["sync_projects"],
                "active_hours": ["23:00", "05:00"],
                "enabled": True,
            },
            {
                "name": "midday",
                "schedule_type": "custom",
                "tool_chain": ["today"],
                "active_hours": ["11:00", "13:00"],
                "enabled": False,
            },
        ]
    }
    sched = Scheduler(config=config)
    entries = sched.list_schedules()
    assert len(entries) == 2, f"expected 2 custom schedules, got {len(entries)}"
    assert entries[0].name == "nightly"
    assert entries[1].name == "midday"
    assert entries[1].enabled is False


def test_list_schedules_returns_all():
    """list_schedules returns all entries."""
    sched = Scheduler(config={})
    entries = sched.list_schedules()
    assert len(entries) == 3
    assert all(isinstance(e, ScheduleEntry) for e in entries)


def test_preview_returns_correct_chain():
    """preview returns correct tool chain."""
    sched = Scheduler(config={})
    chain = sched.preview("morning")
    assert chain == ["check_in", "sync_projects", "today"], f"wrong chain: {chain}"


def test_preview_raises_on_unknown():
    """preview raises KeyError for unknown schedule."""
    sched = Scheduler(config={})
    raised = False
    try:
        sched.preview("nonexistent")
    except KeyError:
        raised = True
    assert raised, "preview should raise KeyError for unknown schedule"


def test_active_hours_inside_window():
    """is_in_active_hours returns True during window."""
    entry = ScheduleEntry(
        name="test",
        schedule_type="custom",
        tool_chain=[],
        active_hours=("08:00", "20:00"),
    )
    noon = datetime(2026, 3, 30, 12, 0)
    sched = Scheduler(config={})
    assert sched.is_in_active_hours(entry, now=noon) is True


def test_active_hours_outside_window():
    """is_in_active_hours returns False outside window."""
    entry = ScheduleEntry(
        name="test",
        schedule_type="custom",
        tool_chain=[],
        active_hours=("08:00", "20:00"),
    )
    late_night = datetime(2026, 3, 30, 23, 30)
    sched = Scheduler(config={})
    assert sched.is_in_active_hours(entry, now=late_night) is False


def test_active_hours_midnight_wrap():
    """is_in_active_hours handles overnight windows (e.g. 22:00 - 06:00)."""
    entry = ScheduleEntry(
        name="overnight",
        schedule_type="custom",
        tool_chain=[],
        active_hours=("22:00", "06:00"),
    )
    sched = Scheduler(config={})
    # 23:00 should be inside.
    assert sched.is_in_active_hours(entry, now=datetime(2026, 3, 30, 23, 0)) is True
    # 12:00 should be outside.
    assert sched.is_in_active_hours(entry, now=datetime(2026, 3, 30, 12, 0)) is False


def test_record_run_writes_status():
    """record_run writes to status file."""
    status_path, td = _tmp_status_path()
    sched = Scheduler(config={}, status_path=status_path)
    sched.record_run("morning", "ok", timestamp="2026-03-30T07:15:00")
    assert status_path.is_file(), "status file should be created"
    data = json.loads(status_path.read_text())
    assert data["morning"]["last_run"] == "2026-03-30T07:15:00"
    assert data["morning"]["last_result"] == "ok"
    td.cleanup()


def test_get_status_returns_correct():
    """get_status returns correct ScheduleStatus."""
    status_path, td = _tmp_status_path()
    sched = Scheduler(config={}, status_path=status_path)
    sched.record_run("morning", "ok", timestamp="2026-03-30T07:15:00")
    status = sched.get_status("morning")
    assert isinstance(status, ScheduleStatus)
    assert status.name == "morning"
    assert status.last_run == "2026-03-30T07:15:00"
    assert status.last_result == "ok"
    td.cleanup()


def test_check_missed_detects_stale():
    """check_missed detects schedules that missed their last window."""
    status_path, td = _tmp_status_path()
    # Write a last_run 48 hours ago.
    old_ts = (datetime.now() - timedelta(hours=48)).isoformat()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps({
        "morning": {"last_run": old_ts, "last_result": "ok"},
    }))
    sched = Scheduler(config={}, status_path=status_path)
    missed = sched.check_missed()
    missed_names = {s.name for s in missed}
    assert "morning" in missed_names, f"morning should be missed, got {missed_names}"
    td.cleanup()


def test_should_catchup_true():
    """should_catchup returns True for missed schedule with catchup enabled."""
    status_path, td = _tmp_status_path()
    config = {
        "schedules": [
            {
                "name": "morning",
                "schedule_type": "morning",
                "tool_chain": ["check_in"],
                "active_hours": ["06:00", "10:00"],
                "enabled": True,
                "catchup": True,
            },
        ]
    }
    # Write stale status.
    old_ts = (datetime.now() - timedelta(hours=48)).isoformat()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps({
        "morning": {"last_run": old_ts, "last_result": "ok"},
    }))
    sched = Scheduler(config=config, status_path=status_path)
    assert sched.should_catchup("morning") is True
    td.cleanup()


def test_should_catchup_false_no_catchup():
    """should_catchup returns False when catchup is not enabled."""
    status_path, td = _tmp_status_path()
    sched = Scheduler(config={}, status_path=status_path)
    # Default schedules have catchup=False.
    # Even if missed (never run), catchup is off.
    assert sched.should_catchup("morning") is False
    td.cleanup()


def test_event_triggers_loaded():
    """Event triggers load from config."""
    config = {
        "event_triggers": [
            {"event": "after_sync", "tool_chain": ["today"], "enabled": True},
            {"event": "after_note_create", "tool_chain": ["sync_projects"], "enabled": True},
        ]
    }
    sched = Scheduler(config=config)
    triggers = sched.get_triggers("after_sync")
    assert len(triggers) == 1
    assert isinstance(triggers[0], EventTrigger)
    assert triggers[0].event == "after_sync"
    assert triggers[0].tool_chain == ["today"]


def test_get_triggers_matching():
    """get_triggers returns matching triggers."""
    config = {
        "event_triggers": [
            {"event": "after_sync", "tool_chain": ["today"], "enabled": True},
            {"event": "after_sync", "tool_chain": ["open_loops"], "enabled": True},
            {"event": "after_session_end", "tool_chain": ["close_day"], "enabled": True},
        ]
    }
    sched = Scheduler(config=config)
    triggers = sched.get_triggers("after_sync")
    assert len(triggers) == 2, f"expected 2 after_sync triggers, got {len(triggers)}"


def test_get_triggers_unknown_event():
    """get_triggers returns empty for unknown event."""
    config = {
        "event_triggers": [
            {"event": "after_sync", "tool_chain": ["today"], "enabled": True},
        ]
    }
    sched = Scheduler(config=config)
    triggers = sched.get_triggers("nonexistent_event")
    assert triggers == [], f"expected empty list, got {triggers}"


def test_get_triggers_disabled_excluded():
    """get_triggers excludes disabled triggers."""
    config = {
        "event_triggers": [
            {"event": "after_sync", "tool_chain": ["today"], "enabled": False},
        ]
    }
    sched = Scheduler(config=config)
    triggers = sched.get_triggers("after_sync")
    assert triggers == [], "disabled trigger should be excluded"


def test_all_statuses_returns_all():
    """all_statuses returns status for all schedules."""
    status_path, td = _tmp_status_path()
    sched = Scheduler(config={}, status_path=status_path)
    sched.record_run("morning", "ok", timestamp="2026-03-30T07:00:00")
    statuses = sched.all_statuses()
    assert len(statuses) == 3, f"expected 3 statuses, got {len(statuses)}"
    names = {s.name for s in statuses}
    assert names == {"morning", "evening", "weekly"}
    morning = [s for s in statuses if s.name == "morning"][0]
    assert morning.last_run == "2026-03-30T07:00:00"
    td.cleanup()


def test_status_file_created_on_first_write():
    """Status file created on first write."""
    status_path, td = _tmp_status_path()
    assert not status_path.exists(), "status file should not exist before first write"
    sched = Scheduler(config={}, status_path=status_path)
    sched.record_run("evening", "error", timestamp="2026-03-30T19:00:00")
    assert status_path.is_file(), "status file should exist after first record_run"
    data = json.loads(status_path.read_text())
    assert data["evening"]["last_result"] == "error"
    td.cleanup()


def test_multiple_records_accumulate():
    """Multiple record_run calls accumulate in status file."""
    status_path, td = _tmp_status_path()
    sched = Scheduler(config={}, status_path=status_path)
    sched.record_run("morning", "ok", timestamp="2026-03-30T07:00:00")
    sched.record_run("evening", "ok", timestamp="2026-03-30T19:00:00")
    data = json.loads(status_path.read_text())
    assert "morning" in data
    assert "evening" in data
    td.cleanup()


def test_no_triggers_by_default():
    """No triggers loaded when config has no event_triggers key."""
    sched = Scheduler(config={})
    triggers = sched.get_triggers("after_sync")
    assert triggers == []


def test_entry_vault_name_override():
    """Per-vault schedule override via vault_name field."""
    config = {
        "schedules": [
            {
                "name": "morning",
                "schedule_type": "morning",
                "tool_chain": ["check_in"],
                "vault_name": "work",
                "active_hours": ["06:00", "10:00"],
            },
        ]
    }
    sched = Scheduler(config=config)
    entries = sched.list_schedules()
    assert entries[0].vault_name == "work"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    test("default schedules loaded when config empty", test_default_schedules_loaded)
    test("custom schedules from config", test_custom_schedules_from_config)
    test("list_schedules returns all entries", test_list_schedules_returns_all)
    test("preview returns correct tool chain", test_preview_returns_correct_chain)
    test("preview raises on unknown schedule", test_preview_raises_on_unknown)
    test("is_in_active_hours inside window", test_active_hours_inside_window)
    test("is_in_active_hours outside window", test_active_hours_outside_window)
    test("is_in_active_hours handles midnight wrap", test_active_hours_midnight_wrap)
    test("record_run writes to status file", test_record_run_writes_status)
    test("get_status returns correct ScheduleStatus", test_get_status_returns_correct)
    test("check_missed detects stale schedules", test_check_missed_detects_stale)
    test("should_catchup true for missed + catchup", test_should_catchup_true)
    test("should_catchup false when catchup disabled", test_should_catchup_false_no_catchup)
    test("event triggers loaded from config", test_event_triggers_loaded)
    test("get_triggers returns matching triggers", test_get_triggers_matching)
    test("get_triggers returns empty for unknown event", test_get_triggers_unknown_event)
    test("get_triggers excludes disabled triggers", test_get_triggers_disabled_excluded)
    test("all_statuses returns status for all schedules", test_all_statuses_returns_all)
    test("status file created on first write", test_status_file_created_on_first_write)
    test("multiple records accumulate", test_multiple_records_accumulate)
    test("no triggers by default", test_no_triggers_by_default)
    test("per-vault schedule override", test_entry_vault_name_override)

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
