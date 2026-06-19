# obsidian_connector/creation_events.py
"""Append-only, immutable event log for the Creation Vault OS (outside iCloud).

One JSON object per line. The canonical markdown notes are materialized views of
this log. Concurrent appends never conflict; conflict detection happens at
materialization time.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import creation_paths

EVENT_TYPES: frozenset[str] = frozenset({
    "session.start", "checkpoint.created", "checkpoint.emergency",
    "session.end", "session.blocked",
    "backlog.upserted", "decision.pending", "decision.resolved",
})


def append_event(vault_path: Path, event_type: str, payload: dict, *,
                 event_id: str, ts_iso: str, session_id: str | None = None) -> dict:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type: {event_type!r}")
    record = {"event_id": event_id, "ts": ts_iso, "event_type": event_type,
              "session_id": session_id, "payload": payload}
    path = creation_paths.events_path(vault_path)
    line = json.dumps(record, sort_keys=True) + "\n"
    # Append by writing existing + new to a temp file then atomically replacing,
    # so a crash never leaves a half-written line in the log.
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(existing + line, encoding="utf-8")
    os.replace(tmp, path)
    return record


def read_events(vault_path: Path) -> list[dict]:
    path = creation_paths.events_path(vault_path)
    if not path.exists():
        return []
    out: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue          # tolerate/skip malformed lines (corruption-resilient)
    return out
