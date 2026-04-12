"""First-class scheduler config and execution engine for obsidian-connector.

Provides schedule definitions, status tracking, event triggers,
active-hours enforcement, and missed-run detection. Reads config
from config.json ``schedules`` and ``event_triggers`` keys; falls
back to sensible built-in defaults when config is absent.

Status is persisted to ``~/.config/obsidian-connector/schedule_status.json``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


# ------------------------------------------------------------------
# Status file location
# ------------------------------------------------------------------

_STATUS_DIR = Path.home() / ".config" / "obsidian-connector"
_STATUS_FILE = _STATUS_DIR / "schedule_status.json"


# ------------------------------------------------------------------
# Dataclasses
# ------------------------------------------------------------------

@dataclass
class ScheduleEntry:
    """A single schedule definition."""

    name: str
    schedule_type: str  # morning | evening | weekly | custom
    tool_chain: list[str]
    vault_name: Optional[str] = None
    enabled: bool = True
    active_hours: tuple[str, str] = ("07:00", "22:00")
    catchup: bool = False


@dataclass
class ScheduleStatus:
    """Runtime status for a schedule."""

    name: str
    last_run: Optional[str] = None   # ISO datetime
    next_run: Optional[str] = None   # ISO datetime
    missed: bool = False
    last_result: Optional[str] = None  # ok | error | None


@dataclass
class EventTrigger:
    """An event-driven trigger definition."""

    event: str  # after_sync | after_note_create | after_session_end
    tool_chain: list[str]
    enabled: bool = True


# ------------------------------------------------------------------
# Built-in defaults
# ------------------------------------------------------------------

_DEFAULT_SCHEDULES: list[dict[str, Any]] = [
    {
        "name": "morning",
        "schedule_type": "morning",
        "tool_chain": ["check_in", "sync_projects", "today"],
        "active_hours": ["06:00", "10:00"],
        "enabled": True,
        "catchup": False,
    },
    {
        "name": "evening",
        "schedule_type": "evening",
        "tool_chain": ["close_day", "running_todo"],
        "active_hours": ["18:00", "22:00"],
        "enabled": True,
        "catchup": False,
    },
    {
        "name": "weekly",
        "schedule_type": "weekly",
        "tool_chain": ["sync_projects", "open_loops", "my_world"],
        "active_hours": ["09:00", "12:00"],
        "enabled": True,
        "catchup": False,
    },
]


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _parse_time(t: str) -> tuple[int, int]:
    """Parse a ``HH:MM`` string into (hour, minute)."""
    parts = t.strip().split(":")
    return int(parts[0]), int(parts[1])


def _dict_to_entry(d: dict[str, Any]) -> ScheduleEntry:
    """Convert a dict (from config or defaults) to a ScheduleEntry."""
    ah = d.get("active_hours", ["07:00", "22:00"])
    if isinstance(ah, list) and len(ah) == 2:
        active = (str(ah[0]), str(ah[1]))
    elif isinstance(ah, tuple) and len(ah) == 2:
        active = (str(ah[0]), str(ah[1]))
    else:
        active = ("07:00", "22:00")

    return ScheduleEntry(
        name=d["name"],
        schedule_type=d.get("schedule_type", "custom"),
        tool_chain=list(d.get("tool_chain", [])),
        vault_name=d.get("vault_name"),
        enabled=d.get("enabled", True),
        active_hours=active,
        catchup=d.get("catchup", False),
    )


def _dict_to_trigger(d: dict[str, Any]) -> EventTrigger:
    """Convert a dict from config to an EventTrigger."""
    return EventTrigger(
        event=d["event"],
        tool_chain=list(d.get("tool_chain", [])),
        enabled=d.get("enabled", True),
    )


def _read_status_file(path: Path | None = None) -> dict[str, Any]:
    """Read the schedule status JSON file. Returns ``{}`` on missing/corrupt."""
    status_path = path or _STATUS_FILE
    if not status_path.is_file():
        return {}
    try:
        with open(status_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_status_file(data: dict[str, Any], path: Path | None = None) -> None:
    """Persist schedule status to disk."""
    status_path = path or _STATUS_FILE
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = status_path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(status_path)


def _estimate_next_run(entry: ScheduleEntry) -> Optional[str]:
    """Estimate the next run time based on schedule type and active hours.

    Returns an ISO datetime string for the next active-hours window
    start, or ``None`` if the schedule is disabled.
    """
    if not entry.enabled:
        return None
    now = datetime.now()
    start_h, start_m = _parse_time(entry.active_hours[0])
    candidate = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.isoformat()


# ------------------------------------------------------------------
# Scheduler class
# ------------------------------------------------------------------

class Scheduler:
    """First-class scheduler config and execution engine.

    Parameters
    ----------
    config:
        Full config dict (typically from ``config.json``). The scheduler
        reads from ``config["schedules"]`` and ``config["event_triggers"]``.
    status_path:
        Override for the status file location (useful in tests).
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        status_path: Path | None = None,
    ) -> None:
        config = config or {}
        self._status_path = status_path
        self._entries: list[ScheduleEntry] = []
        self._triggers: list[EventTrigger] = []

        # Load schedule entries.
        raw_schedules = config.get("schedules")
        if raw_schedules and isinstance(raw_schedules, list):
            for item in raw_schedules:
                if isinstance(item, dict) and "name" in item:
                    self._entries.append(_dict_to_entry(item))
        else:
            # Fall back to built-in defaults.
            for item in _DEFAULT_SCHEDULES:
                self._entries.append(_dict_to_entry(item))

        # Load event triggers.
        raw_triggers = config.get("event_triggers")
        if raw_triggers and isinstance(raw_triggers, list):
            for item in raw_triggers:
                if isinstance(item, dict) and "event" in item:
                    self._triggers.append(_dict_to_trigger(item))

    # -- Schedule queries --------------------------------------------------

    def list_schedules(self) -> list[ScheduleEntry]:
        """Return all configured schedule entries."""
        return list(self._entries)

    def preview(self, name: str) -> list[str]:
        """Return the tool chain for a named schedule without executing.

        Parameters
        ----------
        name:
            Schedule name (e.g. ``"morning"``).

        Returns
        -------
        list[str]
            Ordered list of tool names that would run.

        Raises
        ------
        KeyError
            If the schedule name is not found.
        """
        for entry in self._entries:
            if entry.name == name:
                return list(entry.tool_chain)
        raise KeyError(f"schedule not found: {name!r}")

    def _find_entry(self, name: str) -> ScheduleEntry | None:
        """Look up a schedule entry by name."""
        for entry in self._entries:
            if entry.name == name:
                return entry
        return None

    # -- Active hours ------------------------------------------------------

    def is_in_active_hours(
        self,
        entry: ScheduleEntry | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Check if the current time falls within an entry's active window.

        If *entry* is ``None``, checks the global default window
        ``("07:00", "22:00")``.
        """
        now = now or datetime.now()
        if entry is not None:
            start_str, end_str = entry.active_hours
        else:
            start_str, end_str = "07:00", "22:00"

        start_h, start_m = _parse_time(start_str)
        end_h, end_m = _parse_time(end_str)

        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        now_minutes = now.hour * 60 + now.minute

        if start_minutes <= end_minutes:
            return start_minutes <= now_minutes < end_minutes
        else:
            # Wraps midnight (e.g. 22:00 - 06:00).
            return now_minutes >= start_minutes or now_minutes < end_minutes

    # -- Status tracking ---------------------------------------------------

    def get_status(self, name: str) -> ScheduleStatus:
        """Return the current status for a named schedule.

        Reads persisted status from disk and merges with schedule metadata.
        """
        data = _read_status_file(self._status_path)
        entry = self._find_entry(name)
        sdata = data.get(name, {})

        last_run = sdata.get("last_run")
        last_result = sdata.get("last_result")

        # Determine if the schedule was missed.
        missed = False
        if entry and entry.enabled and last_run:
            try:
                lr = datetime.fromisoformat(last_run)
                # If the last run was more than 24 hours ago, flag as missed.
                if (datetime.now() - lr) > timedelta(hours=24):
                    missed = True
            except ValueError:
                pass
        elif entry and entry.enabled and last_run is None:
            # Never run -- treat as missed.
            missed = True

        next_run = None
        if entry:
            next_run = _estimate_next_run(entry)

        return ScheduleStatus(
            name=name,
            last_run=last_run,
            next_run=next_run,
            missed=missed,
            last_result=last_result,
        )

    def all_statuses(self) -> list[ScheduleStatus]:
        """Return status for every configured schedule."""
        return [self.get_status(e.name) for e in self._entries]

    def record_run(
        self,
        name: str,
        result: str,
        timestamp: str | None = None,
    ) -> None:
        """Record a schedule run result to the status file.

        Parameters
        ----------
        name:
            Schedule name.
        result:
            ``"ok"`` or ``"error"``.
        timestamp:
            ISO datetime string. Defaults to ``datetime.now().isoformat()``.
        """
        ts = timestamp or datetime.now().isoformat()
        data = _read_status_file(self._status_path)
        data[name] = {
            "last_run": ts,
            "last_result": result,
        }
        _write_status_file(data, self._status_path)

    # -- Missed-run detection ----------------------------------------------

    def check_missed(self) -> list[ScheduleStatus]:
        """Return statuses for all schedules that missed their last window."""
        return [s for s in self.all_statuses() if s.missed]

    def should_catchup(self, name: str) -> bool:
        """Return ``True`` if the schedule was missed and catchup is enabled."""
        entry = self._find_entry(name)
        if entry is None:
            return False
        status = self.get_status(name)
        return status.missed and entry.catchup

    # -- Event triggers ----------------------------------------------------

    def get_triggers(self, event: str) -> list[EventTrigger]:
        """Return all enabled triggers matching the given event name.

        Parameters
        ----------
        event:
            One of ``"after_sync"``, ``"after_note_create"``,
            ``"after_session_end"``.

        Returns
        -------
        list[EventTrigger]
            Matching triggers (may be empty).
        """
        return [
            t for t in self._triggers
            if t.event == event and t.enabled
        ]
