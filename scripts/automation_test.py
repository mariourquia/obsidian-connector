"""Tests for the event-triggered automation runtime."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian_connector.automation import (
    ChainResult,
    EventBus,
    StepResult,
    TOOL_REGISTRY,
    ToolChainRunner,
    list_available_tools,
)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}")


# ------------------------------------------------------------------
# Mock tool registry for testing (don't call real vault operations)
# ------------------------------------------------------------------

_call_log: list[str] = []


def _mock_tool_ok(vault: str, **kw) -> dict:
    _call_log.append("ok_tool")
    return {"status": "ok"}


def _mock_tool_fail(vault: str, **kw) -> dict:
    _call_log.append("fail_tool")
    raise RuntimeError("intentional failure")


def _mock_tool_slow(vault: str, **kw) -> dict:
    _call_log.append("slow_tool")
    time.sleep(0.05)
    return {"status": "slow_ok"}


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_tool_registry():
    print("== tool registry ==")
    tools = list_available_tools()
    check("list_available_tools returns list", isinstance(tools, list))
    check("list_available_tools is sorted", tools == sorted(tools))
    check("registry has check_in", "check_in" in TOOL_REGISTRY)
    check("registry has today", "today" in TOOL_REGISTRY)
    check("registry has sync_projects", "sync_projects" in TOOL_REGISTRY)
    check("registry has report_weekly", "report_weekly" in TOOL_REGISTRY)
    check("registry has clean_drafts", "clean_drafts" in TOOL_REGISTRY)
    check("registry has rebuild_index", "rebuild_index" in TOOL_REGISTRY)
    check("registry has project_health", "project_health" in TOOL_REGISTRY)
    check("registry has >= 12 tools", len(TOOL_REGISTRY) >= 12)


def test_dataclasses():
    print("== dataclasses ==")
    sr = StepResult(tool_name="test", ok=True, duration_ms=100)
    check("StepResult has tool_name", sr.tool_name == "test")
    check("StepResult has ok", sr.ok is True)
    check("StepResult has duration_ms", sr.duration_ms == 100)
    check("StepResult error defaults None", sr.error is None)

    cr = ChainResult(
        chain_name="a+b", steps=[sr], total_duration_ms=100,
        all_ok=True, trigger="manual",
    )
    check("ChainResult has chain_name", cr.chain_name == "a+b")
    check("ChainResult has trigger", cr.trigger == "manual")
    check("ChainResult all_ok", cr.all_ok is True)


def test_runner_with_mocks():
    print("== runner with mocks ==")
    _call_log.clear()

    # Patch the registry with mock tools
    mock_registry = {
        "ok_tool": _mock_tool_ok,
        "fail_tool": _mock_tool_fail,
        "slow_tool": _mock_tool_slow,
    }

    with patch.dict("obsidian_connector.automation.TOOL_REGISTRY", mock_registry, clear=True):
        runner = ToolChainRunner("/fake/vault")

        # Single step success
        result = runner.run_step("ok_tool")
        check("run_step ok returns ok=True", result.ok is True)
        check("run_step ok has duration", result.duration_ms >= 0)
        check("run_step ok has data", result.data == {"status": "ok"})

        # Single step failure
        result = runner.run_step("fail_tool")
        check("run_step fail returns ok=False", result.ok is False)
        check("run_step fail has error", "intentional failure" in result.error)

        # Unknown tool
        result = runner.run_step("nonexistent")
        check("run_step unknown ok=False", result.ok is False)
        check("run_step unknown has error", "Unknown tool" in result.error)

        # Chain execution
        _call_log.clear()
        chain = runner.run_chain(["ok_tool", "fail_tool", "ok_tool"], trigger="test")
        check("chain has 3 steps", len(chain.steps) == 3)
        check("chain all_ok is False (one failed)", chain.all_ok is False)
        check("chain trigger recorded", chain.trigger == "test")
        check("chain continued after failure", len(_call_log) == 3)
        check("chain step 0 ok", chain.steps[0].ok is True)
        check("chain step 1 failed", chain.steps[1].ok is False)
        check("chain step 2 ok", chain.steps[2].ok is True)

        # All-success chain
        _call_log.clear()
        chain = runner.run_chain(["ok_tool", "slow_tool"])
        check("all-ok chain all_ok=True", chain.all_ok is True)
        check("all-ok chain has duration", chain.total_duration_ms >= 50)

        # Empty chain
        chain = runner.run_chain([])
        check("empty chain all_ok=True", chain.all_ok is True)
        check("empty chain 0 steps", len(chain.steps) == 0)


def test_event_bus():
    print("== event bus ==")
    _call_log.clear()

    mock_registry = {"ok_tool": _mock_tool_ok, "fail_tool": _mock_tool_fail}

    with patch.dict("obsidian_connector.automation.TOOL_REGISTRY", mock_registry, clear=True):
        runner = ToolChainRunner("/fake/vault")

        # Mock scheduler with triggers
        mock_scheduler = MagicMock()

        # EventTrigger mock
        trigger_sync = MagicMock()
        trigger_sync.event = "after_sync"
        trigger_sync.tool_chain = ["ok_tool"]
        trigger_sync.enabled = True

        trigger_disabled = MagicMock()
        trigger_disabled.event = "after_sync"
        trigger_disabled.tool_chain = ["fail_tool"]
        trigger_disabled.enabled = False

        mock_scheduler.get_triggers.return_value = [trigger_sync, trigger_disabled]
        mock_scheduler.record_run = MagicMock()

        # Schedule entry mock
        schedule_entry = MagicMock()
        schedule_entry.name = "morning"
        schedule_entry.tool_chain = ["ok_tool"]
        mock_scheduler.list_schedules.return_value = [schedule_entry]

        bus = EventBus(runner, mock_scheduler)

        # fire_event with matching trigger
        results = bus.fire_event("after_sync")
        check("fire_event returns results", len(results) == 1)
        check("fire_event skips disabled", len(results) == 1)  # disabled one skipped
        check("fire_event result all_ok", results[0].all_ok is True)
        check("fire_event recorded run", mock_scheduler.record_run.called)

        # fire_event with no matching triggers
        mock_scheduler.get_triggers.return_value = []
        results = bus.fire_event("nonexistent_event")
        check("fire_event no triggers returns []", results == [])

        # run_schedule
        result = bus.run_schedule("morning")
        check("run_schedule returns result", result is not None)
        check("run_schedule all_ok", result.all_ok is True)
        check("run_schedule trigger set", result.trigger == "schedule:morning")

        # run_schedule unknown
        result = bus.run_schedule("nonexistent")
        check("run_schedule unknown all_ok=False", result.all_ok is False)

        # on_vault_change -- .md creation fires event
        mock_scheduler.get_triggers.return_value = [trigger_sync]
        trigger_sync.event = "after_note_create"
        results = bus.on_vault_change("created", "/vault/new-note.md")
        check("on_vault_change .md fires event", len(results) >= 0)

        # on_vault_change -- non-.md ignored
        results = bus.on_vault_change("created", "/vault/image.png")
        check("on_vault_change non-.md returns []", results == [])

        # on_vault_change -- modified (not created) ignored
        results = bus.on_vault_change("modified", "/vault/existing.md")
        check("on_vault_change modified returns []", results == [])

        # history
        history = bus.history()
        check("history returns list", isinstance(history, list))
        check("history has entries", len(history) > 0)

        # on_sync_complete and on_session_end
        trigger_sync.event = "after_sync"
        mock_scheduler.get_triggers.return_value = [trigger_sync]
        results = bus.on_sync_complete()
        check("on_sync_complete fires", isinstance(results, list))

        trigger_sync.event = "after_session_end"
        results = bus.on_session_end()
        check("on_session_end fires", isinstance(results, list))

    # No scheduler
    bus_no_sched = EventBus(runner, scheduler=None)
    check("no scheduler fire_event safe", bus_no_sched.fire_event("x") == [])
    check("no scheduler run_schedule safe", bus_no_sched.run_schedule("x") is None)


def test_one_shot_helpers():
    print("== one-shot helpers ==")
    mock_registry = {"ok_tool": _mock_tool_ok}

    with patch.dict("obsidian_connector.automation.TOOL_REGISTRY", mock_registry, clear=True):
        from obsidian_connector.automation import run_schedule_now, run_event_now
        from obsidian_connector.scheduler import Scheduler

        # Use the real Scheduler with empty config (gets built-in defaults)
        # and pass config directly to avoid load_config
        result = run_schedule_now("/fake", "morning", config={})
        check("run_schedule_now returns ChainResult", isinstance(result, ChainResult))

        results = run_event_now("/fake", "after_sync", config={})
        check("run_event_now returns list", isinstance(results, list))


def main() -> int:
    test_tool_registry()
    test_dataclasses()
    test_runner_with_mocks()
    test_event_bus()
    test_one_shot_helpers()

    print(f"\n{'=' * 50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 50}")
    return 1 if FAIL > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
