"""Local-only session telemetry for obsidian-connector.

Tracks per-session metrics (notes read/written, tools called, errors) and
persists them as JSONL files in the user's config directory.

**CRITICAL**: This module makes ZERO network calls.  All data stays local.
No ``urllib``, ``socket``, ``requests``, or ``http.client`` imports.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Default storage location
# ---------------------------------------------------------------------------

_DEFAULT_STORAGE_DIR = (
    Path.home() / ".config" / "obsidian-connector" / "telemetry"
)


# ---------------------------------------------------------------------------
# Session dataclass
# ---------------------------------------------------------------------------

@dataclass
class SessionTelemetry:
    """Metrics for a single connector session."""

    session_start: str = ""  # ISO datetime
    notes_read: int = 0
    notes_written: int = 0
    tools_called: dict[str, int] = field(default_factory=dict)
    retrieval_misses: int = 0
    write_risk_events: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON output."""
        return {
            "session_start": self.session_start,
            "notes_read": self.notes_read,
            "notes_written": self.notes_written,
            "tools_called": dict(self.tools_called),
            "retrieval_misses": self.retrieval_misses,
            "write_risk_events": self.write_risk_events,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class TelemetryCollector:
    """Local-only session telemetry collector.

    Stores one JSONL file per calendar day.  Each line is one session.
    Auto-rotates files older than ``max_age_days`` on explicit
    :meth:`rotate` calls.
    """

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        if storage_dir is not None:
            self._dir = Path(storage_dir)
        else:
            self._dir = _DEFAULT_STORAGE_DIR
        self._session: SessionTelemetry | None = None

    # -- Session lifecycle ---------------------------------------------------

    def start_session(self) -> None:
        """Initialize a new session with zeroed counters."""
        self._session = SessionTelemetry(
            session_start=datetime.now(timezone.utc).isoformat(),
        )

    def end_session(self) -> Path | None:
        """Write the current session to today's JSONL file.

        Returns the path to the JSONL file, or ``None`` if no session was
        active.
        """
        if self._session is None:
            return None

        self._dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = self._dir / f"{today}.jsonl"

        record = self._session.to_dict()
        record["session_end"] = datetime.now(timezone.utc).isoformat()

        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")

        result_path = log_file
        self._session = None
        return result_path

    # -- Recording methods ---------------------------------------------------

    def record_read(self) -> None:
        """Increment notes_read counter."""
        if self._session is not None:
            self._session.notes_read += 1

    def record_write(self) -> None:
        """Increment notes_written counter."""
        if self._session is not None:
            self._session.notes_written += 1

    def record_tool(self, tool_name: str) -> None:
        """Increment the call count for *tool_name*."""
        if self._session is not None:
            self._session.tools_called[tool_name] = (
                self._session.tools_called.get(tool_name, 0) + 1
            )

    def record_retrieval_miss(self) -> None:
        """Increment retrieval_misses counter."""
        if self._session is not None:
            self._session.retrieval_misses += 1

    def record_write_risk(self) -> None:
        """Increment write_risk_events counter."""
        if self._session is not None:
            self._session.write_risk_events += 1

    def record_error(self) -> None:
        """Increment errors counter."""
        if self._session is not None:
            self._session.errors += 1

    # -- Query methods -------------------------------------------------------

    def session_summary(self) -> dict[str, Any]:
        """Return the current session telemetry as a dict.

        Returns an empty dict if no session is active.
        """
        if self._session is None:
            return {}
        return self._session.to_dict()

    def weekly_summary(self) -> dict[str, Any]:
        """Aggregate the last 7 days of telemetry files.

        Returns a dict with summed counters and per-tool totals.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return self._aggregate(cutoff)

    # -- Maintenance ---------------------------------------------------------

    def rotate(self, max_age_days: int = 30) -> int:
        """Delete telemetry files older than *max_age_days*.

        Returns the number of files deleted.
        """
        if not self._dir.is_dir():
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        deleted = 0

        for f in self._dir.iterdir():
            if not f.name.endswith(".jsonl"):
                continue
            # Parse date from filename (YYYY-MM-DD.jsonl).
            date_str = f.stem
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc,
                )
            except ValueError:
                continue
            if file_date < cutoff:
                f.unlink(missing_ok=True)
                deleted += 1

        return deleted

    # -- Internal helpers ----------------------------------------------------

    def _aggregate(self, since: datetime) -> dict[str, Any]:
        """Sum session records from files dated on or after *since*."""
        totals: dict[str, Any] = {
            "sessions": 0,
            "notes_read": 0,
            "notes_written": 0,
            "tools_called": {},
            "retrieval_misses": 0,
            "write_risk_events": 0,
            "errors": 0,
        }

        if not self._dir.is_dir():
            return totals

        for f in sorted(self._dir.iterdir()):
            if not f.name.endswith(".jsonl"):
                continue
            date_str = f.stem
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc,
                )
            except ValueError:
                continue
            if file_date < since:
                continue

            try:
                lines = f.read_text(encoding="utf-8").strip().split("\n")
            except OSError:
                continue

            for line in lines:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                totals["sessions"] += 1
                totals["notes_read"] += record.get("notes_read", 0)
                totals["notes_written"] += record.get("notes_written", 0)
                totals["retrieval_misses"] += record.get("retrieval_misses", 0)
                totals["write_risk_events"] += record.get("write_risk_events", 0)
                totals["errors"] += record.get("errors", 0)

                for tool, count in record.get("tools_called", {}).items():
                    totals["tools_called"][tool] = (
                        totals["tools_called"].get(tool, 0) + count
                    )

        return totals
