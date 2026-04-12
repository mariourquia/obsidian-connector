"""Event-triggered automation runtime for obsidian-connector.

Connects the watcher, scheduler, and tool modules into an autonomous
system.  Tool chains execute sequentially; a failing step logs the
error and continues to the next step.

Usage::

    watcher, bus = start_automation(vault_path)
    watcher.start()          # begins watching vault
    bus.run_schedule("morning")  # manual trigger
    bus.fire_event("after_sync") # event trigger
    watcher.stop()           # cleanup
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Result dataclasses
# ------------------------------------------------------------------

@dataclass
class StepResult:
    """Outcome of a single tool execution."""

    tool_name: str
    ok: bool
    duration_ms: int
    error: str | None = None
    data: Any = None


@dataclass
class ChainResult:
    """Outcome of executing a full tool chain."""

    chain_name: str
    steps: list[StepResult]
    total_duration_ms: int
    all_ok: bool
    trigger: str  # "schedule:morning", "event:after_sync", "manual"


# ------------------------------------------------------------------
# Tool registry -- lazy imports inside each wrapper
# ------------------------------------------------------------------

def _tool_check_in(vault: str, **kw: Any) -> Any:
    from obsidian_connector.workflows import check_in
    return check_in(vault=vault)


def _tool_today(vault: str, **kw: Any) -> Any:
    from obsidian_connector.workflows import today_brief
    return today_brief(vault=vault)


def _tool_close_day(vault: str, **kw: Any) -> Any:
    from obsidian_connector.workflows import close_day_reflection
    return close_day_reflection(vault=vault)


def _tool_open_loops(vault: str, **kw: Any) -> Any:
    from obsidian_connector.workflows import list_open_loops
    return list_open_loops(vault=vault)


def _tool_my_world(vault: str, **kw: Any) -> Any:
    from obsidian_connector.workflows import my_world_snapshot
    return my_world_snapshot(vault=vault)


def _tool_sync_projects(vault: str, **kw: Any) -> Any:
    from obsidian_connector.project_sync import sync_projects
    return sync_projects(vault=vault)


def _tool_report_weekly(vault: str, **kw: Any) -> Any:
    from obsidian_connector.reports import generate_report
    return generate_report(vault, "weekly")


def _tool_report_monthly(vault: str, **kw: Any) -> Any:
    from obsidian_connector.reports import generate_report
    return generate_report(vault, "monthly")


def _tool_report_vault_health(vault: str, **kw: Any) -> Any:
    from obsidian_connector.reports import generate_report
    return generate_report(vault, "vault_health")


def _tool_clean_drafts(vault: str, **kw: Any) -> Any:
    from obsidian_connector.draft_manager import clean_stale_drafts
    return clean_stale_drafts(vault)


def _tool_rebuild_index(vault: str, **kw: Any) -> Any:
    from obsidian_connector.index_store import IndexStore
    from obsidian_connector.config import resolve_vault_path
    vault_path = resolve_vault_path(vault) if isinstance(vault, str) else vault
    store = IndexStore()
    try:
        index = store.build_full(vault_path=vault_path)
        return {"notes_indexed": len(index.notes), "tags": len(index.tags)}
    finally:
        store.close()


def _tool_running_todo(vault: str, **kw: Any) -> Any:
    from obsidian_connector.project_sync import get_running_todo
    return get_running_todo(vault=vault)


def _tool_project_health(vault: str, **kw: Any) -> Any:
    from obsidian_connector.project_intelligence import project_health
    return project_health(vault)


def _tool_project_packet(vault: str, **kw: Any) -> Any:
    from obsidian_connector.project_intelligence import project_packet
    return project_packet(vault)


TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "check_in": _tool_check_in,
    "today": _tool_today,
    "close_day": _tool_close_day,
    "open_loops": _tool_open_loops,
    "my_world": _tool_my_world,
    "sync_projects": _tool_sync_projects,
    "running_todo": _tool_running_todo,
    "report_weekly": _tool_report_weekly,
    "report_monthly": _tool_report_monthly,
    "report_vault_health": _tool_report_vault_health,
    "clean_drafts": _tool_clean_drafts,
    "rebuild_index": _tool_rebuild_index,
    "project_health": _tool_project_health,
    "project_packet": _tool_project_packet,
}


def list_available_tools() -> list[str]:
    """Return sorted list of registered tool names."""
    return sorted(TOOL_REGISTRY.keys())


# ------------------------------------------------------------------
# ToolChainRunner
# ------------------------------------------------------------------

class ToolChainRunner:
    """Executes a sequence of tools against a vault."""

    def __init__(self, vault_path: str | Path, config: dict[str, Any] | None = None):
        self.vault_path = str(vault_path)
        self.config = config or {}

    def run_step(self, tool_name: str) -> StepResult:
        """Execute a single tool by name. Never raises."""
        func = TOOL_REGISTRY.get(tool_name)
        if func is None:
            return StepResult(
                tool_name=tool_name, ok=False, duration_ms=0,
                error=f"Unknown tool: {tool_name}",
            )
        t0 = time.monotonic()
        try:
            data = func(self.vault_path)
            ms = int((time.monotonic() - t0) * 1000)
            log.info("Step %s completed in %dms", tool_name, ms)
            return StepResult(tool_name=tool_name, ok=True, duration_ms=ms, data=data)
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            log.warning("Step %s failed after %dms: %s", tool_name, ms, exc)
            return StepResult(
                tool_name=tool_name, ok=False, duration_ms=ms, error=str(exc),
            )

    def run_chain(self, tool_chain: list[str], trigger: str = "manual") -> ChainResult:
        """Execute tools sequentially. Continues on failure."""
        t0 = time.monotonic()
        steps: list[StepResult] = []
        for tool_name in tool_chain:
            result = self.run_step(tool_name)
            steps.append(result)
        total_ms = int((time.monotonic() - t0) * 1000)
        all_ok = all(s.ok for s in steps)
        chain_name = "+".join(tool_chain)
        if all_ok:
            log.info("Chain [%s] completed in %dms (trigger=%s)", chain_name, total_ms, trigger)
        else:
            failed = [s.tool_name for s in steps if not s.ok]
            log.warning(
                "Chain [%s] completed with %d failures in %dms: %s",
                chain_name, len(failed), total_ms, failed,
            )
        return ChainResult(
            chain_name=chain_name, steps=steps,
            total_duration_ms=total_ms, all_ok=all_ok, trigger=trigger,
        )


# ------------------------------------------------------------------
# EventBus -- connects vault events to tool chains
# ------------------------------------------------------------------

class EventBus:
    """Routes vault events and schedule triggers to tool chain execution."""

    def __init__(self, runner: ToolChainRunner, scheduler: Any | None = None):
        self.runner = runner
        self.scheduler = scheduler
        self._history: list[ChainResult] = []
        self._max_history = 100

    def fire_event(self, event_name: str) -> list[ChainResult]:
        """Look up triggers for *event_name* and execute matching tool chains."""
        results: list[ChainResult] = []
        if self.scheduler is None:
            return results
        triggers = self.scheduler.get_triggers(event_name)
        for trigger in triggers:
            if not trigger.enabled:
                continue
            result = self.runner.run_chain(
                trigger.tool_chain, trigger=f"event:{event_name}",
            )
            results.append(result)
            self._push_history(result)
            if self.scheduler:
                self.scheduler.record_run(
                    f"event:{event_name}", "ok" if result.all_ok else "error",
                )
        return results

    def run_schedule(self, schedule_name: str) -> ChainResult | None:
        """Execute a named schedule's tool chain."""
        if self.scheduler is None:
            return None
        entry = None
        for s in self.scheduler.list_schedules():
            if s.name == schedule_name:
                entry = s
                break
        if entry is None:
            return ChainResult(
                chain_name=schedule_name, steps=[], total_duration_ms=0,
                all_ok=False, trigger=f"schedule:{schedule_name}",
            )
        result = self.runner.run_chain(
            entry.tool_chain, trigger=f"schedule:{schedule_name}",
        )
        self._push_history(result)
        if self.scheduler:
            self.scheduler.record_run(
                schedule_name, "ok" if result.all_ok else "error",
            )
        return result

    def on_vault_change(self, event_type: str, path: str) -> list[ChainResult]:
        """Called by watcher on file changes. Only fires for .md creation."""
        if event_type == "created" and path.endswith(".md"):
            return self.fire_event("after_note_create")
        return []

    def on_sync_complete(self) -> list[ChainResult]:
        """Fire after project sync completes."""
        return self.fire_event("after_sync")

    def on_session_end(self) -> list[ChainResult]:
        """Fire at session end."""
        return self.fire_event("after_session_end")

    def history(self, limit: int = 20) -> list[ChainResult]:
        """Return most recent chain results."""
        return list(reversed(self._history[-limit:]))

    def _push_history(self, result: ChainResult) -> None:
        self._history.append(result)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]


# ------------------------------------------------------------------
# High-level entry points
# ------------------------------------------------------------------

def start_automation(
    vault_path: str | Path,
    config: dict[str, Any] | None = None,
) -> tuple[Any, EventBus]:
    """Initialize watcher + event bus + scheduler.

    Returns ``(watcher, event_bus)``.  Caller must call
    ``watcher.start()`` to begin and ``watcher.stop()`` to clean up.
    """
    from obsidian_connector.config import load_config
    from obsidian_connector.scheduler import Scheduler
    from obsidian_connector.watcher import VaultWatcher

    cfg = config if config is not None else load_config().__dict__
    scheduler = Scheduler(cfg)
    runner = ToolChainRunner(vault_path, cfg)
    bus = EventBus(runner, scheduler)

    # Create a mock index_store since watcher needs one
    # In real usage, the watcher updates the index; here we just need
    # the event routing.
    class _NoOpIndex:
        def update_incremental(self, *a: Any, **kw: Any) -> None:
            pass

    watcher = VaultWatcher(
        vault_path=str(vault_path),
        index_store=_NoOpIndex(),
    )

    # Wire watcher events to the event bus
    _original_on_change = watcher.on_change

    def _wired_on_change(event_type: str, path: str) -> None:
        _original_on_change(event_type, path)
        bus.on_vault_change(event_type, path)

    watcher.on_change = _wired_on_change  # type: ignore[assignment]

    return watcher, bus


def run_schedule_now(
    vault_path: str | Path,
    schedule_name: str,
    config: dict[str, Any] | None = None,
) -> ChainResult:
    """One-shot: execute a named schedule immediately."""
    from obsidian_connector.config import load_config
    from obsidian_connector.scheduler import Scheduler

    cfg = config if config is not None else load_config().__dict__
    scheduler = Scheduler(cfg)
    runner = ToolChainRunner(vault_path, cfg)
    bus = EventBus(runner, scheduler)
    result = bus.run_schedule(schedule_name)
    if result is None:
        return ChainResult(
            chain_name=schedule_name, steps=[], total_duration_ms=0,
            all_ok=False, trigger=f"schedule:{schedule_name}",
        )
    return result


def run_event_now(
    vault_path: str | Path,
    event_name: str,
    config: dict[str, Any] | None = None,
) -> list[ChainResult]:
    """One-shot: fire an event and execute matching triggers."""
    from obsidian_connector.config import load_config
    from obsidian_connector.scheduler import Scheduler

    cfg = config if config is not None else load_config().__dict__
    scheduler = Scheduler(cfg)
    runner = ToolChainRunner(vault_path, cfg)
    bus = EventBus(runner, scheduler)
    return bus.fire_event(event_name)
