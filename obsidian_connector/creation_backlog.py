# obsidian_connector/creation_backlog.py
"""Backlog primitive for the Creation Vault OS (Gap #1).

The append-only event log (``creation_events``) is the source of truth. Each
backlog item is stored as a full-snapshot ``backlog.upserted`` event keyed by
its ULID id under ``payload["item"]``; reduction keeps the latest event per id.
The canonical ``Backlog/{project}/{id}.md`` note is a materialized view, rebuilt
idempotently from events. ``list``/``show`` reduce the event log and never parse
list fields back out of markdown (the string-only frontmatter reader cannot
represent lists). A ``service:backlog-user-notes`` fence holds free-form user
notes preserved across regeneration.

See docs/architecture/creation-vault-schema.md and
docs/plans/2026-06-18-creation-backlog-engine-plan.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import creation_events as ce
from . import creation_freshness as cf
from . import creation_schema as cs
from obsidian_connector.write_manager import atomic_write

PRIORITIES = ("P0", "P1", "P2", "P3")
STATUSES = ("idea", "ready", "in_progress", "blocked", "in_review", "done", "archived")
WORK_TYPES = (
    "feature-dev", "bugfix", "refactor", "research", "ops", "docs",
    "testing", "review", "planning", "release", "architecture",
)

_FENCE_BEGIN = "<!-- service:backlog-user-notes:begin -->"
_FENCE_END = "<!-- service:backlog-user-notes:end -->"

# List-valued item fields (stored as real lists in events; rendered as inline
# arrays or body lists in the note, never parsed back from markdown).
_LIST_FIELDS = ("repos", "acceptance_criteria", "blockers", "dependencies",
                "source_notes", "supersedes")

# Freshness scalar fields that also live on a backlog item (flat).
_FRESHNESS_SCALARS = (
    "authority_level", "confidence", "last_verified_at", "last_verified_by",
    "verification_source", "source_repo", "source_branch", "source_commit",
    "source_pr", "source_session", "staleness_policy", "valid_until",
    "superseded_by",
)

# Item fields the CLI/MCP `update` verb may change (project is immutable; id and
# last_touched are managed internally).
UPDATABLE_FIELDS = (
    "title", "repos", "priority", "status", "work_type", "owner",
    "ready_for_agent", "needs_decision", "acceptance_criteria", "blockers",
    "dependencies", "source_notes", "next_action", "urgency", "impact",
    "confidence", "authority_level", "verification_source", "source_repo",
    "source_branch", "source_commit", "source_pr", "source_session",
    "staleness_policy", "valid_until", "last_verified_at", "last_verified_by",
)


def _validate(item: dict) -> None:
    if item["priority"] not in PRIORITIES:
        raise ValueError(f"priority must be one of {PRIORITIES}")
    if item["status"] not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if item["work_type"] not in WORK_TYPES:
        raise ValueError(f"work_type must be one of {WORK_TYPES}")
    if item["authority_level"] not in cs.STATUS_LABELS:
        raise ValueError(f"authority_level must be one of {cs.STATUS_LABELS}")


def _freshness(item: dict) -> cs.Freshness:
    sub = {k: item.get(k) for k in (("id", "supersedes") + _FRESHNESS_SCALARS)}
    return cs.freshness_from_dict(sub)


def _check_completion(item: dict) -> None:
    if item["status"] == "done":
        ok, reason = cf.can_complete(_freshness(item))
        if not ok:
            raise ValueError(f"cannot mark done: {reason}")


def _reduce(events: list[dict]) -> dict[str, dict]:
    items: dict[str, dict] = {}
    for ev in events:
        if ev.get("event_type") != "backlog.upserted":
            continue
        item = (ev.get("payload") or {}).get("item")
        if isinstance(item, dict) and item.get("id"):
            items[item["id"]] = item
    return items


def _inline_array(items) -> str:
    return "[" + ", ".join(json.dumps(str(i)) for i in (items or [])) + "]"


def _extract_user_notes(existing: str | None) -> str:
    if not existing:
        return ""
    b = existing.find(_FENCE_BEGIN)
    e = existing.find(_FENCE_END)
    if b == -1 or e == -1 or e < b:
        return ""
    return existing[b + len(_FENCE_BEGIN):e].strip("\n")


def _render_backlog_md(item: dict, user_notes: str) -> str:
    L = ["---", f"id: {item['id']}", "type: backlog-item",
         f"title: {item['title']}", f"project: {item['project']}",
         f"repos: {_inline_array(item.get('repos'))}",
         f"priority: {item['priority']}", f"status: {item['status']}",
         f"work_type: {item['work_type']}", f"owner: {item['owner']}",
         f"ready_for_agent: {str(item['ready_for_agent']).lower()}",
         f"needs_decision: {str(item['needs_decision']).lower()}",
         f"urgency: {item['urgency']}", f"impact: {item['impact']}",
         f"dependencies: {_inline_array(item.get('dependencies'))}",
         f"last_touched: {item['last_touched']}",
         f"authority_level: {item['authority_level']}",
         f"confidence: {item['confidence']}"]
    if item.get("next_action") is not None:
        L.append(f"next_action: {item['next_action']}")
    for k in ("last_verified_at", "last_verified_by", "verification_source",
              "source_repo", "source_branch", "source_commit", "source_pr",
              "source_session", "valid_until", "superseded_by"):
        v = item.get(k)
        if v is not None:
            L.append(f"{k}: {v}")
    L.append(f"staleness_policy: {item.get('staleness_policy', 'manual')}")
    L.append(f"supersedes: {_inline_array(item.get('supersedes'))}")
    L += ["---", "", f"# {item['title']}", "",
          f"**Next action:** {item.get('next_action') or '_none_'}", "",
          "## Acceptance criteria"]
    L += [f"- [ ] {c}" for c in (item.get("acceptance_criteria") or [])] or ["_none_"]
    L += ["", "## Blockers"]
    L += [f"- {b}" for b in (item.get("blockers") or [])] or ["_none_"]
    L += ["", "## Dependencies"]
    L += [f"- [[{d}]]" for d in (item.get("dependencies") or [])] or ["_none_"]
    L += ["", "## Sources"]
    L += [f"- {s}" for s in (item.get("source_notes") or [])] or ["_none_"]
    L += ["", _FENCE_BEGIN, user_notes, _FENCE_END, ""]
    return "\n".join(L)


def _materialize(vault_path: Path, item: dict) -> str:
    rel = f"Backlog/{item['project']}/{item['id']}.md"
    path = Path(vault_path) / rel
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    atomic_write(path, _render_backlog_md(item, _extract_user_notes(existing)),
                 vault_root=Path(vault_path), tool_name="creation_backlog")
    return rel


def add_backlog_item(vault_path: Path, *, title: str, project: str, now_iso: str,
                     repos=(), priority: str = "P2", status: str = "idea",
                     work_type: str = "feature-dev", owner: str = "mario",
                     ready_for_agent: bool = False, needs_decision: bool = False,
                     acceptance_criteria=(), blockers=(), dependencies=(),
                     source_notes=(), next_action: str | None = None,
                     urgency: int = 5, impact: int = 5, confidence: float = 0.5,
                     authority_level: str = "agent_reported_unverified",
                     verification_source: str | None = None,
                     source_repo: str | None = None, source_branch: str | None = None,
                     source_commit: str | None = None, source_pr: str | None = None,
                     source_session: str | None = None,
                     staleness_policy: str = "manual", valid_until: str | None = None,
                     last_verified_at: str | None = None,
                     last_verified_by: str | None = None,
                     dry_run: bool = False) -> dict:
    item_id = cs.new_id("bkl", f"{now_iso}|{project}|{title}")
    item = {
        "id": item_id, "title": title, "project": project,
        "repos": list(repos), "priority": priority, "status": status,
        "work_type": work_type, "owner": owner,
        "ready_for_agent": bool(ready_for_agent),
        "needs_decision": bool(needs_decision),
        "acceptance_criteria": list(acceptance_criteria),
        "blockers": list(blockers), "dependencies": list(dependencies),
        "source_notes": list(source_notes), "next_action": next_action,
        "urgency": urgency, "impact": impact, "confidence": confidence,
        "last_touched": now_iso, "authority_level": authority_level,
        "verification_source": verification_source, "source_repo": source_repo,
        "source_branch": source_branch, "source_commit": source_commit,
        "source_pr": source_pr, "source_session": source_session,
        "staleness_policy": staleness_policy, "valid_until": valid_until,
        "last_verified_at": last_verified_at, "last_verified_by": last_verified_by,
        "supersedes": [], "superseded_by": None,
    }
    _validate(item)
    _check_completion(item)
    rel = f"Backlog/{project}/{item_id}.md"
    if dry_run:
        return {"id": item_id, "path": rel, "dry_run": True}
    ce.append_event(vault_path, "backlog.upserted", {"item": item},
                    event_id=item_id, ts_iso=now_iso, session_id=source_session)
    _materialize(vault_path, item)
    return {"id": item_id, "path": rel, "dry_run": False}


def update_backlog_item(vault_path: Path, *, item_id: str, now_iso: str,
                        dry_run: bool = False, **changes) -> dict:
    current = _reduce(ce.read_events(vault_path)).get(item_id)
    if current is None:
        raise KeyError(f"unknown backlog item: {item_id}")
    item = dict(current)
    for key, val in changes.items():
        if val is None or key not in UPDATABLE_FIELDS:
            continue
        item[key] = list(val) if key in _LIST_FIELDS else val
    item["last_touched"] = now_iso
    _validate(item)
    _check_completion(item)
    rel = f"Backlog/{item['project']}/{item_id}.md"
    if dry_run:
        return {"id": item_id, "path": rel, "status": item["status"], "dry_run": True}
    ce.append_event(vault_path, "backlog.upserted", {"item": item},
                    event_id=cs.new_id("bkl", f"{now_iso}|update|{item_id}"),
                    ts_iso=now_iso, session_id=item.get("source_session"))
    _materialize(vault_path, item)
    return {"id": item_id, "path": rel, "status": item["status"], "dry_run": False}


def list_backlog(vault_path: Path, *, project: str | None = None,
                 status: str | None = None, priority: str | None = None) -> list[dict]:
    items = list(_reduce(ce.read_events(vault_path)).values())
    if project:
        items = [i for i in items if i.get("project") == project]
    if status:
        items = [i for i in items if i.get("status") == status]
    if priority:
        items = [i for i in items if i.get("priority") == priority]
    items.sort(key=lambda i: (i.get("priority", "P3"), -int(i.get("urgency", 0)),
                              -int(i.get("impact", 0)), i["id"]))
    return items


def show_backlog_item(vault_path: Path, *, item_id: str) -> dict | None:
    return _reduce(ce.read_events(vault_path)).get(item_id)


def rebuild_backlog(vault_path: Path, *, dry_run: bool = False) -> dict:
    items = _reduce(ce.read_events(vault_path))
    ids = sorted(items)
    if not dry_run:
        for item_id in ids:
            _materialize(vault_path, items[item_id])
    return {"count": len(ids), "ids": ids, "dry_run": dry_run}
