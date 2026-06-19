# obsidian_connector/creation_session.py
"""Resumable agent-session lifecycle for the Creation Vault OS.

See docs/architecture/creation-session-state.md. Events are the source of truth;
the session note + active marker are materialized views.
"""
from __future__ import annotations

from pathlib import Path

from . import creation_events as ce
from . import creation_schema as cs
from .write_manager import atomic_write

_ACTIVE = "sessions/_active.md"


def _session_md(session_id: str, repo: str, branch: str, backlog_id: str | None, started_at: str) -> str:
    return (
        f"---\nid: {session_id}\ntype: agent-session\nstatus: active\n"
        f"backlog_item: {backlog_id or 'null'}\nrepos: [{repo}]\nbranch: {branch}\n"
        f"started_at: {started_at}\n---\n\n# Session {session_id}\n\n"
        "## Plan\n\n## Completed\n\n## Next action\n\n## Blockers\n"
    )


def start_session(vault_path: Path, *, repo: str, branch: str, backlog_id: str | None = None,
                  now_iso: str, dry_run: bool = False) -> dict:
    session_id = cs.new_id("ses", f"{now_iso}|{repo}|{branch}")
    rel = f"sessions/{session_id}.md"
    if dry_run:
        return {"session_id": session_id, "path": rel, "dry_run": True}
    ce.append_event(vault_path, "session.start",
                    {"repo": repo, "branch": branch, "backlog_id": backlog_id},
                    event_id=session_id, ts_iso=now_iso, session_id=session_id)
    atomic_write(Path(vault_path) / rel,
                 _session_md(session_id, repo, branch, backlog_id, now_iso),
                 vault_root=Path(vault_path), tool_name="creation_sync_start")
    atomic_write(Path(vault_path) / _ACTIVE, f"{session_id}\n",
                 vault_root=Path(vault_path), tool_name="creation_sync_start")
    return {"session_id": session_id, "path": rel, "dry_run": False}


def checkpoint_session(vault_path: Path, *, session_id: str, summary: str, next_steps: str,
                       blockers: str, confidence: float, now_iso: str,
                       emergency: bool = False, dry_run: bool = False) -> dict:
    chk_id = cs.new_id("chk", f"{now_iso}|{session_id}")
    if dry_run:
        return {"checkpoint_id": chk_id, "session_id": session_id, "dry_run": True}
    ce.append_event(vault_path, "checkpoint.emergency" if emergency else "checkpoint.created",
                    {"summary": summary, "next_steps": next_steps, "blockers": blockers,
                     "confidence": confidence},
                    event_id=chk_id, ts_iso=now_iso, session_id=session_id)
    rel = f"sessions/{session_id}/checkpoints/{now_iso.replace(':', '-')}.md"
    atomic_write(Path(vault_path) / rel,
                 f"---\nid: {chk_id}\ntype: checkpoint\nsession: {session_id}\n"
                 f"created_at: {now_iso}\nemergency: {str(emergency).lower()}\n---\n\n"
                 f"## Completed\n{summary}\n\n## Next steps\n{next_steps}\n\n"
                 f"## Blockers\n{blockers}\n",
                 vault_root=Path(vault_path), tool_name="creation_sync_checkpoint")
    return {"checkpoint_id": chk_id, "session_id": session_id, "dry_run": False}


def end_session(vault_path: Path, *, session_id: str, report: str, next_action: str,
                now_iso: str, status: str = "closed", dry_run: bool = False) -> dict:
    if dry_run:
        return {"session_id": session_id, "status": status, "dry_run": True}
    ce.append_event(vault_path, "session.end",
                    {"report": report, "next_action": next_action, "status": status},
                    event_id=cs.new_id("ses", f"{now_iso}|end|{session_id}"),
                    ts_iso=now_iso, session_id=session_id)
    active = Path(vault_path) / _ACTIVE
    if active.exists() and active.read_text(encoding="utf-8").strip() == session_id:
        active.unlink()
    return {"session_id": session_id, "status": status, "dry_run": False}


def active_session(vault_path: Path) -> str | None:
    active = Path(vault_path) / _ACTIVE
    if not active.exists():
        return None
    val = active.read_text(encoding="utf-8").strip()
    return val or None
