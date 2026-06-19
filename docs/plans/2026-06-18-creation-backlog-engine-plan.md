---
title: "Creation Backlog Engine v0 Implementation Plan"
status: draft
owner: mariourquia
last_reviewed: "2026-06-18"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/creation_backlog.py"
  - "obsidian_connector/creation_events.py"
  - "obsidian_connector/creation_schema.py"
  - "obsidian_connector/creation_freshness.py"
  - "obsidian_connector/cli.py"
  - "obsidian_connector/mcp_server.py"
related_docs:
  - "./2026-06-18-creation-vault-os.md"
  - "./2026-06-18-creation-spine-v0-plan.md"
  - "../architecture/creation-vault-schema.md"
tags: ["creation-vault-os", "backlog", "plan", "phase-2"]
---

# Creation Backlog Engine v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the backlog primitive (Gap #1) to the Creation Vault OS: an event-sourced `backlog-item` engine with `add`/`update`/`list`/`show`/`rebuild`, an event-log source of truth, materialized `Backlog/{project}/{id}.md` notes, a fence-preserving renderer, and the hybrid completion gate — exposed via `obsx creation backlog ...` + `obsx creation rebuild` and mirrored in MCP.

**Architecture:** Mirrors the shipped Creation spine v0. The append-only `creation_events.jsonl` (outside iCloud) is the source of truth; each backlog item is a full-snapshot `backlog.upserted` event keyed by its ULID. `list`/`show` reduce the event log (never parse list fields out of markdown, which the string-only frontmatter reader cannot represent); `rebuild` re-materializes notes idempotently. A `service:backlog-user-notes` fence preserves hand-written notes across regeneration. The hybrid completion gate (`creation_freshness.can_complete`) refuses `status=done` without `source_commit`/`source_pr`.

**Tech Stack:** Python 3 stdlib only (no new deps), `write_manager.atomic_write`, argparse CLI, FastMCP tools. Tests via `pytest` mirroring `tests/test_creation_*.py`.

## Global Constraints

- **Stdlib only.** No new third-party dependencies. Match the spine's import style (`from . import creation_events as ce`; `from obsidian_connector.write_manager import atomic_write` as an absolute import so `tests/test_hardening.py`'s AST audit recognizes it).
- **Event log is the source of truth.** Markdown notes are materialized views. `list`/`show`/`rebuild` read the event log, never re-parse list frontmatter. Each mutation appends one `backlog.upserted` event carrying the FULL item snapshot under `payload["item"]`; reduction keeps the latest event per `id`.
- **All vault writes go through `write_manager.atomic_write`** with `vault_root=Path(vault_path)` and a `tool_name`. No raw `write_text` to the vault. `creation_backlog.py` MUST be added to `tests/test_hardening.py::_AUDITED_MODULES`.
- **Mutations are dry-run-by-default at the CLI/MCP boundary.** Module functions take `dry_run: bool`. CLI: `dry = args.dry_run or not args.allow_write`. MCP: `dry_run: bool = True`. `log_action(...)` fires only on real (non-dry) CLI mutations.
- **Clock boundary stays at the CLI/MCP edge.** Module functions take `now_iso: str`; they never read a clock. The CLI/MCP layer passes `datetime.now(timezone.utc).isoformat()`. `creation_schema.new_id(prefix, seed)` is deterministic from its seed.
- **Canonical envelope.** CLI sets `data` (dict/list) + `human` (str); the surrounding dispatcher wraps `{ok, command, vault, duration_ms, data}`. MCP tools return `json.dumps(result, indent=2)` and a `{"ok": False, "error": {...}}` envelope on exception.
- **CLI ↔ MCP parity.** Every new CLI verb has exactly one MCP tool: `creation backlog add|update|list|show` + `creation rebuild` ↔ `obsidian_creation_backlog_add|update|list|show` + `obsidian_creation_rebuild` (5 each). `mcpb.json` `tools_count` goes 118 → 123. `scripts/integrity_check.py` and `scripts/manifest_check.py` must pass.
- **Folder layout:** `Backlog/{project}/{id}.md` (matches `freshness_audit`'s `Backlog/**/*.md` rglob and `creation-vault-schema.md`).
- **Enums** (reject anything else): `priority ∈ {P0,P1,P2,P3}`; `status ∈ {idea,ready,in_progress,blocked,in_review,done,archived}`; `work_type ∈ {feature-dev,bugfix,refactor,research,ops,docs,testing,review,planning,release,architecture}`; `authority_level ∈ creation_schema.STATUS_LABELS`.
- **`project` is immutable after creation** (its value is in the note path). `update` does not accept a project change.
- **No model/provider co-author attribution trailer** on any commit (strip any auto-generated authorship/attribution line). Branch is `feat/creation-backlog-engine`.

## Out of scope (later phases, do NOT build here)

Migration backfill of existing scattered work items (`running-todo`/`open-loops`/commitments) into backlog items; the Project entity + dashboards (Phase 4); the explainable `next` scoring engine (Phase 4); `reprioritize`/`handoff` verbs; voice-to-backlog (Phase 3); a persistent `index/backlog.json` (reduce-on-read is sufficient at v0 scale). `list_backlog`'s sort is a simple deterministic ordering, NOT the Phase-4 weighted score.

## File Structure

- **Create** `obsidian_connector/creation_backlog.py` — the engine (reduce, build, render, fence-extract, add, update + completion gate, list, show, rebuild).
- **Create** `tests/test_creation_backlog.py` — unit tests (engine + materialization + gate + idempotency + fence preservation).
- **Create** `tests/test_creation_backlog_cli.py` — CLI tests (envelope, `--json`, dry-run default, `--allow-write`, `log_action`).
- **Modify** `obsidian_connector/__init__.py` — export the public backlog functions.
- **Modify** `tests/test_hardening.py` — add `creation_backlog.py` to `_AUDITED_MODULES`.
- **Modify** `obsidian_connector/cli.py` — `backlog` (add/update/list/show) + `rebuild` subparsers and dispatch.
- **Modify** `obsidian_connector/mcp_server.py` — 5 MCP tools.
- **Modify** `mcpb.json` — `tools_count` 118 → 123.
- **Modify** `TOOLS_CONTRACT.md` — document the new verbs.

---

## Task 1: `creation_backlog.py` engine + unit tests + hardening allowlist + exports

**Files:**
- Create: `obsidian_connector/creation_backlog.py`
- Create: `tests/test_creation_backlog.py`
- Modify: `obsidian_connector/__init__.py`
- Modify: `tests/test_hardening.py`

**Interfaces:**
- Consumes: `creation_events.append_event(vault_path, event_type, payload, *, event_id, ts_iso, session_id=None)`, `creation_events.read_events(vault_path)`, `creation_schema.new_id(prefix, seed)`, `creation_schema.STATUS_LABELS`, `creation_schema.freshness_from_dict(d)`, `creation_freshness.can_complete(f) -> (bool, str)`, `write_manager.atomic_write(path, content, *, vault_root, tool_name)`. The event type `"backlog.upserted"` is already in `creation_events.EVENT_TYPES`.
- Produces (relied on by Tasks 2-3):
  - `add_backlog_item(vault_path, *, title, project, now_iso, repos=(), priority="P2", status="idea", work_type="feature-dev", owner="mario", ready_for_agent=False, needs_decision=False, acceptance_criteria=(), blockers=(), dependencies=(), source_notes=(), next_action=None, urgency=5, impact=5, confidence=0.5, authority_level="agent_reported_unverified", verification_source=None, source_repo=None, source_branch=None, source_commit=None, source_pr=None, source_session=None, staleness_policy="manual", valid_until=None, last_verified_at=None, last_verified_by=None, dry_run=False) -> dict` returning `{"id", "path", "dry_run"}`.
  - `update_backlog_item(vault_path, *, item_id, now_iso, dry_run=False, **changes) -> dict` returning `{"id", "path", "status", "dry_run"}`; raises `KeyError` if the id is unknown, `ValueError` on a bad enum or a blocked completion.
  - `list_backlog(vault_path, *, project=None, status=None, priority=None) -> list[dict]`.
  - `show_backlog_item(vault_path, *, item_id) -> dict | None`.
  - `rebuild_backlog(vault_path, *, dry_run=False) -> dict` returning `{"count", "ids", "dry_run"}`.

- [ ] **Step 1: Write the module.** Create `obsidian_connector/creation_backlog.py` with exactly this content:

```python
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
```

- [ ] **Step 2: Write the failing unit tests.** Create `tests/test_creation_backlog.py` with exactly this content:

```python
# tests/test_creation_backlog.py
import pytest

from obsidian_connector import creation_backlog as cb
from obsidian_connector import creation_events as ce

T0 = "2026-06-18T00:00:00Z"
T1 = "2026-06-18T01:00:00Z"


def _vault(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    v = tmp_path / "v"
    (v / ".obsidian").mkdir(parents=True)
    return v


def test_add_creates_event_and_note(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="JWKS rotation", project="mcmc-erp",
                              repos=["mcmc-erp", "mcmc-erp-web"], priority="P1",
                              now_iso=T0)
    assert res["id"].startswith("bkl_")
    assert res["path"] == f"Backlog/mcmc-erp/{res['id']}.md"
    assert (v / res["path"]).exists()
    evs = ce.read_events(v)
    assert [e["event_type"] for e in evs] == ["backlog.upserted"]
    assert evs[0]["payload"]["item"]["title"] == "JWKS rotation"


def test_note_frontmatter_is_parser_safe_and_repos_inline(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="t", project="p", repos=["a", "b"],
                              now_iso=T0)
    text = (v / res["path"]).read_text(encoding="utf-8")
    assert 'repos: ["a", "b"]' in text          # inline array, not multiline YAML
    assert "type: backlog-item" in text
    assert "source_commit:" not in text          # None freshness fields omitted
    assert cb._FENCE_BEGIN in text and cb._FENCE_END in text


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="t", project="p", now_iso=T0, dry_run=True)
    assert res["dry_run"] is True
    assert ce.read_events(v) == []
    assert not (v / "Backlog").exists()


def test_list_reduces_latest_per_id_and_filters(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", priority="P0", now_iso=T0)["id"]
    cb.add_backlog_item(v, title="b", project="y", priority="P2", now_iso=T0)
    cb.update_backlog_item(v, item_id=a, now_iso=T1, status="ready")
    rows = cb.list_backlog(v)
    assert len(rows) == 2                         # update did not create a 3rd item
    assert next(r for r in rows if r["id"] == a)["status"] == "ready"
    assert [r["project"] for r in cb.list_backlog(v, project="x")] == ["x"]
    assert cb.list_backlog(v, status="ready")[0]["id"] == a


def test_show_returns_item_or_none(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    assert cb.show_backlog_item(v, item_id=a)["title"] == "a"
    assert cb.show_backlog_item(v, item_id="bkl_nope") is None


def test_update_unknown_id_raises(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    with pytest.raises(KeyError):
        cb.update_backlog_item(v, item_id="bkl_nope", now_iso=T0, status="ready")


def test_update_rejects_bad_enum(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    with pytest.raises(ValueError):
        cb.update_backlog_item(v, item_id=a, now_iso=T1, priority="P9")


def test_completion_gate_blocks_done_without_evidence(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    with pytest.raises(ValueError, match="repo evidence"):
        cb.update_backlog_item(v, item_id=a, now_iso=T1, status="done")


def test_completion_gate_allows_done_with_commit(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    a = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)["id"]
    res = cb.update_backlog_item(v, item_id=a, now_iso=T1, status="done",
                                 source_commit="abc1234")
    assert res["status"] == "done"
    assert cb.show_backlog_item(v, item_id=a)["source_commit"] == "abc1234"


def test_rebuild_is_idempotent(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="a", project="x",
                              acceptance_criteria=["c1"], now_iso=T0)
    note = v / res["path"]
    first = note.read_text(encoding="utf-8")
    out = cb.rebuild_backlog(v)
    assert out["count"] == 1 and out["dry_run"] is False
    after_one = note.read_text(encoding="utf-8")
    cb.rebuild_backlog(v)
    after_two = note.read_text(encoding="utf-8")
    assert first == after_one == after_two          # byte-identical across rebuilds


def test_rebuild_preserves_user_notes_fence(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    res = cb.add_backlog_item(v, title="a", project="x", now_iso=T0)
    note = v / res["path"]
    text = note.read_text(encoding="utf-8")
    text = text.replace(cb._FENCE_BEGIN + "\n\n" + cb._FENCE_END,
                        cb._FENCE_BEGIN + "\nMARIO HAND NOTE\n" + cb._FENCE_END)
    note.write_text(text, encoding="utf-8")
    cb.update_backlog_item(v, item_id=res["id"], now_iso=T1, status="in_progress")
    assert "MARIO HAND NOTE" in note.read_text(encoding="utf-8")
    cb.rebuild_backlog(v)
    assert "MARIO HAND NOTE" in note.read_text(encoding="utf-8")
```

- [ ] **Step 3: Run the unit tests, expect PASS.** Run: `python3 -m pytest tests/test_creation_backlog.py -v`. Expected: all 11 tests PASS. If `test_rebuild_preserves_user_notes_fence`'s string `.replace` does not match (because the empty-fence rendering differs), adjust the test's seed replacement to match the actual empty-fence bytes produced by `_render_backlog_md` — do NOT change the module to fit the test.

- [ ] **Step 4: Add the module to the hardening allowlist.** In `tests/test_hardening.py`, find `_AUDITED_MODULES` (it already contains `creation_session.py`) and add `"creation_backlog.py"` to it, preserving the existing ordering/format.

- [ ] **Step 5: Run the hardening test, expect PASS.** Run: `python3 -m pytest tests/test_hardening.py -v`. Expected: PASS (the module writes only through `atomic_write`).

- [ ] **Step 6: Export the public functions.** In `obsidian_connector/__init__.py`, near the existing creation imports (the `from obsidian_connector.creation_session import (...)` / `creation_status import (...)` block around line 99-106), add:

```python
from obsidian_connector.creation_backlog import (
    add_backlog_item,
    update_backlog_item,
    list_backlog,
    show_backlog_item,
    rebuild_backlog,
)
```

If `__init__.py` maintains an `__all__`, append these five names to it. Match the file's existing import style.

- [ ] **Step 7: Verify exports import cleanly.** Run: `python3 -c "import obsidian_connector as o; print(o.add_backlog_item, o.rebuild_backlog)"`. Expected: prints two function objects, no ImportError.

- [ ] **Step 8: Commit.**

```bash
git add obsidian_connector/creation_backlog.py tests/test_creation_backlog.py tests/test_hardening.py obsidian_connector/__init__.py
git commit -m "feat(creation): backlog engine (events-as-truth, materialized notes, completion gate)"
```

---

## Task 2: CLI verbs — `creation backlog add|update|list|show` + `creation rebuild`

**Files:**
- Modify: `obsidian_connector/cli.py` (subparsers near line 3564, after the `sync end` parser, before `return parser`; dispatch near line 5398, inside `elif args.command == "creation"`, after the `sync` branch and before the `else:` usage fallback)
- Create: `tests/test_creation_backlog_cli.py`

**Interfaces:**
- Consumes the Task 1 functions via `from obsidian_connector import creation_backlog as _cbl`.
- Reuses the existing dispatch locals: `vault` (already resolved), `now = datetime.now(timezone.utc).isoformat()` (already computed at the top of the `creation` branch), `log_action`, and the `data`/`human` envelope convention.

- [ ] **Step 1: Add the subparsers.** In `cli.py`, immediately after the `sync end` parser block (the last `creation_sync_sub.add_parser("end", ...)` group, ending at line ~3564) and before `return parser`, insert:

```python
    # backlog (Creation Vault OS backlog engine)
    creation_bl_p = creation_sub.add_parser("backlog", help="Backlog item CRUD.")
    creation_bl_sub = creation_bl_p.add_subparsers(dest="backlog_cmd")

    p = creation_bl_sub.add_parser("add", help="Add a backlog item.")
    p.add_argument("--title", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--repos", default="", help="Comma-separated repo slugs.")
    p.add_argument("--priority", default="P2")
    p.add_argument("--status", default="idea")
    p.add_argument("--work-type", dest="work_type", default="feature-dev")
    p.add_argument("--owner", default="mario")
    p.add_argument("--next-action", dest="next_action", default=None)
    p.add_argument("--acceptance", action="append", default=[],
                   help="Acceptance criterion (repeatable).")
    p.add_argument("--blocker", action="append", default=[],
                   help="Blocker (repeatable).")
    p.add_argument("--depends-on", dest="depends_on", action="append", default=[],
                   help="Dependency backlog id (repeatable).")
    p.add_argument("--urgency", type=int, default=5)
    p.add_argument("--impact", type=int, default=5)
    p.add_argument("--confidence", type=float, default=0.5)
    p.add_argument("--authority-level", dest="authority_level",
                   default="agent_reported_unverified")
    p.add_argument("--source-repo", dest="source_repo", default=None)
    p.add_argument("--source-commit", dest="source_commit", default=None)
    p.add_argument("--source-pr", dest="source_pr", default=None)
    p.add_argument("--ready-for-agent", dest="ready_for_agent", action="store_true")
    p.add_argument("--needs-decision", dest="needs_decision", action="store_true")
    p.add_argument("--allow-write", dest="allow_write", action="store_true")
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    p.add_argument("--json", dest="sub_json", action="store_true")

    p = creation_bl_sub.add_parser("update", help="Update a backlog item.")
    p.add_argument("--id", dest="item_id", required=True)
    p.add_argument("--title", default=None)
    p.add_argument("--priority", default=None)
    p.add_argument("--status", default=None)
    p.add_argument("--work-type", dest="work_type", default=None)
    p.add_argument("--owner", default=None)
    p.add_argument("--next-action", dest="next_action", default=None)
    p.add_argument("--repos", default=None, help="Comma-separated; replaces the list.")
    p.add_argument("--acceptance", action="append", default=None,
                   help="Replace acceptance criteria (repeatable).")
    p.add_argument("--blocker", action="append", default=None,
                   help="Replace blockers (repeatable).")
    p.add_argument("--depends-on", dest="depends_on", action="append", default=None,
                   help="Replace dependencies (repeatable).")
    p.add_argument("--urgency", type=int, default=None)
    p.add_argument("--impact", type=int, default=None)
    p.add_argument("--confidence", type=float, default=None)
    p.add_argument("--authority-level", dest="authority_level", default=None)
    p.add_argument("--source-repo", dest="source_repo", default=None)
    p.add_argument("--source-commit", dest="source_commit", default=None)
    p.add_argument("--source-pr", dest="source_pr", default=None)
    p.add_argument("--allow-write", dest="allow_write", action="store_true")
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    p.add_argument("--json", dest="sub_json", action="store_true")

    p = creation_bl_sub.add_parser("list", help="List backlog items.")
    p.add_argument("--project", default=None)
    p.add_argument("--status", default=None)
    p.add_argument("--priority", default=None)
    p.add_argument("--json", dest="sub_json", action="store_true")

    p = creation_bl_sub.add_parser("show", help="Show one backlog item.")
    p.add_argument("--id", dest="item_id", required=True)
    p.add_argument("--json", dest="sub_json", action="store_true")

    p = creation_sub.add_parser("rebuild", help="Re-materialize all backlog notes from events.")
    p.add_argument("--allow-write", dest="allow_write", action="store_true")
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    p.add_argument("--json", dest="sub_json", action="store_true")
```

- [ ] **Step 2: Add the dispatch.** In `cli.py`, inside `elif args.command == "creation":`, the `creation_cmd` if/elif chain currently ends with `elif creation_cmd == "sync":` then `else:`. Add an import of the engine at the top of the `creation` branch (next to the existing `from obsidian_connector import creation_session as _csess` import):

```python
            from obsidian_connector import creation_backlog as _cbl
```

Then insert these two branches BEFORE the final `else:` (the `print("Usage: obsx creation status|sync|freshness-audit", ...)`):

```python
            elif creation_cmd == "backlog":
                backlog_cmd = getattr(args, "backlog_cmd", None)
                if backlog_cmd == "add":
                    dry = args.dry_run or not args.allow_write
                    data = _cbl.add_backlog_item(
                        vault, title=args.title, project=args.project, now_iso=now,
                        repos=[r for r in args.repos.split(",") if r],
                        priority=args.priority, status=args.status,
                        work_type=args.work_type, owner=args.owner,
                        next_action=args.next_action,
                        acceptance_criteria=args.acceptance, blockers=args.blocker,
                        dependencies=args.depends_on, urgency=args.urgency,
                        impact=args.impact, confidence=args.confidence,
                        authority_level=args.authority_level,
                        source_repo=args.source_repo, source_commit=args.source_commit,
                        source_pr=args.source_pr,
                        ready_for_agent=args.ready_for_agent,
                        needs_decision=args.needs_decision, dry_run=dry)
                    human = (f"[dry-run] " if dry else "") + \
                        f"Backlog item {data['id']} added ({args.project})."
                    log_action("creation-backlog-add", vars(args), vault, dry_run=dry)

                elif backlog_cmd == "update":
                    dry = args.dry_run or not args.allow_write
                    changes = {k: getattr(args, k) for k in (
                        "title", "priority", "status", "work_type", "owner",
                        "next_action", "urgency", "impact", "confidence",
                        "authority_level", "source_repo", "source_commit",
                        "source_pr")}
                    if args.repos is not None:
                        changes["repos"] = [r for r in args.repos.split(",") if r]
                    if args.acceptance is not None:
                        changes["acceptance_criteria"] = args.acceptance
                    if args.blocker is not None:
                        changes["blockers"] = args.blocker
                    if args.depends_on is not None:
                        changes["dependencies"] = args.depends_on
                    data = _cbl.update_backlog_item(
                        vault, item_id=args.item_id, now_iso=now, dry_run=dry,
                        **changes)
                    human = (f"[dry-run] " if dry else "") + \
                        f"Backlog item {data['id']} updated (status={data['status']})."
                    log_action("creation-backlog-update", vars(args), vault, dry_run=dry)

                elif backlog_cmd == "list":
                    rows = _cbl.list_backlog(vault, project=args.project,
                                             status=args.status, priority=args.priority)
                    data = {"items": rows, "count": len(rows)}
                    human = "\n".join(
                        f"{r['priority']} {r['status']:<11} {r['id']}  {r['title']}"
                        for r in rows) or "No backlog items."

                elif backlog_cmd == "show":
                    item = _cbl.show_backlog_item(vault, item_id=args.item_id)
                    if item is None:
                        print(f"Unknown backlog item: {args.item_id}", file=sys.stderr)
                        return 1
                    data = item
                    human = (f"{item['id']}  {item['title']}\n"
                             f"  {item['priority']} {item['status']} "
                             f"({item['project']})\n"
                             f"  next: {item.get('next_action') or '-'}")

                else:
                    print("Usage: obsx creation backlog add|update|list|show",
                          file=sys.stderr)
                    return 1

            elif creation_cmd == "rebuild":
                dry = args.dry_run or not args.allow_write
                data = _cbl.rebuild_backlog(vault, dry_run=dry)
                human = (f"[dry-run] " if dry else "") + \
                    f"Rebuilt {data['count']} backlog note(s)."
                log_action("creation-rebuild", vars(args), vault, dry_run=dry)
```

Update the final `else:` usage string to: `"Usage: obsx creation status|sync|backlog|rebuild|freshness-audit"`.

- [ ] **Step 3: Write the failing CLI tests.** Create `tests/test_creation_backlog_cli.py`:

```python
# tests/test_creation_backlog_cli.py
import json

from obsidian_connector import cli
from obsidian_connector import creation_backlog as cb
from obsidian_connector import creation_events as ce


def _run(monkeypatch, tmp_path, argv):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "v"))
    (tmp_path / "v" / ".obsidian").mkdir(parents=True, exist_ok=True)
    return cli.main(argv)


def test_add_is_dry_run_by_default(tmp_path, monkeypatch, capsys):
    rc = _run(monkeypatch, tmp_path,
              ["creation", "backlog", "add", "--title", "t", "--project", "p"])
    assert rc == 0
    assert "[dry-run]" in capsys.readouterr().out
    assert ce.read_events(tmp_path / "v") == []           # nothing written


def test_add_allow_write_persists_and_logs(tmp_path, monkeypatch, capsys):
    logged = []
    monkeypatch.setattr(cli, "log_action",
                        lambda *a, **k: logged.append((a, k)))
    rc = _run(monkeypatch, tmp_path,
              ["creation", "backlog", "add", "--title", "t", "--project", "p",
               "--repos", "a,b", "--allow-write", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    item_id = out["data"]["id"]
    assert cb.show_backlog_item(tmp_path / "v", item_id=item_id) is not None
    assert logged and logged[-1][1].get("dry_run") is False


def test_list_and_show_roundtrip(tmp_path, monkeypatch, capsys):
    _run(monkeypatch, tmp_path,
         ["creation", "backlog", "add", "--title", "t", "--project", "p",
          "--allow-write"])
    rc = _run(monkeypatch, tmp_path, ["creation", "backlog", "list", "--json"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)["data"]["items"]
    assert len(rows) == 1
    rc = _run(monkeypatch, tmp_path,
              ["creation", "backlog", "show", "--id", rows[0]["id"], "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["data"]["title"] == "t"
```

(If `cli.main`'s signature or the envelope key names differ from `out["ok"]` / `out["data"]`, adjust the test assertions to the real envelope shape observed from `creation status --json` — the envelope is produced by existing code, not this task.)

- [ ] **Step 4: Run CLI tests, expect PASS.** Run: `python3 -m pytest tests/test_creation_backlog_cli.py -v`. Expected: 3 PASS.

- [ ] **Step 5: Manual smoke.** Run:
```bash
python3 -m obsidian_connector.cli creation backlog --help
python3 -m obsidian_connector.cli creation rebuild --help
```
Expected: both print usage with the new options, exit 0.

- [ ] **Step 6: Commit.**

```bash
git add obsidian_connector/cli.py tests/test_creation_backlog_cli.py
git commit -m "feat(creation): obsx creation backlog add|update|list|show + rebuild CLI"
```

---

## Task 3: MCP parity + contract + integrity

**Files:**
- Modify: `obsidian_connector/mcp_server.py` (after `obsidian_creation_sync_end`, ending ~line 5018)
- Modify: `mcpb.json` (`tools_count` 118 → 123)
- Modify: `TOOLS_CONTRACT.md` (document the new verbs)

**Interfaces:** Consumes the Task 1 functions. Mirrors the existing `obsidian_creation_sync_*` tool pattern exactly (lazy imports, `load_config`/`resolve_vault_path`, `now = datetime.now(timezone.utc).isoformat()` for mutators, `json.dumps(result, indent=2)`, `{"ok": False, "error": {...}}` on exception).

- [ ] **Step 1: Add the five MCP tools.** In `mcp_server.py`, after the `obsidian_creation_sync_end` function (~line 5018), add five tools. Reads (`list`, `show`) use `readOnlyHint=True, idempotentHint=True`; writes (`add`, `update`, `rebuild`) use `readOnlyHint=False, idempotentHint=False`, `dry_run: bool = True`. Use this shape (shown for `add`; replicate for the others with the matching parameters from Task 1's signatures):

```python
@mcp.tool(
    title="Creation Backlog Add",
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False,
        idempotentHint=False, openWorldHint=False,
    ),
)
def obsidian_creation_backlog_add(
    title: str,
    project: str,
    repos: list[str] | None = None,
    priority: str = "P2",
    status: str = "idea",
    work_type: str = "feature-dev",
    owner: str = "mario",
    next_action: str | None = None,
    acceptance_criteria: list[str] | None = None,
    blockers: list[str] | None = None,
    dependencies: list[str] | None = None,
    urgency: int = 5,
    impact: int = 5,
    confidence: float = 0.5,
    authority_level: str = "agent_reported_unverified",
    source_repo: str | None = None,
    source_commit: str | None = None,
    source_pr: str | None = None,
    ready_for_agent: bool = False,
    needs_decision: bool = False,
    dry_run: bool = True,
    vault: str | None = None,
) -> str:
    """Add a Creation Vault backlog item (event + materialized note). Dry-run by default."""
    from datetime import datetime, timezone

    from obsidian_connector.config import load_config, resolve_vault_path
    from obsidian_connector.creation_backlog import add_backlog_item

    try:
        cfg = load_config()
        vault_path = resolve_vault_path(vault or cfg.default_vault)
        now = datetime.now(timezone.utc).isoformat()
        result = add_backlog_item(
            vault_path, title=title, project=project, now_iso=now,
            repos=repos or [], priority=priority, status=status,
            work_type=work_type, owner=owner, next_action=next_action,
            acceptance_criteria=acceptance_criteria or [],
            blockers=blockers or [], dependencies=dependencies or [],
            urgency=urgency, impact=impact, confidence=confidence,
            authority_level=authority_level, source_repo=source_repo,
            source_commit=source_commit, source_pr=source_pr,
            ready_for_agent=ready_for_agent, needs_decision=needs_decision,
            dry_run=dry_run)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})
```

Then add:
- `obsidian_creation_backlog_update(item_id: str, title=None, priority=None, status=None, work_type=None, owner=None, next_action=None, repos=None, acceptance_criteria=None, blockers=None, dependencies=None, urgency=None, impact=None, confidence=None, authority_level=None, source_repo=None, source_commit=None, source_pr=None, dry_run=True, vault=None)` — builds a `changes` dict of the non-None params (only keys in `creation_backlog.UPDATABLE_FIELDS`) and calls `update_backlog_item(vault_path, item_id=item_id, now_iso=now, dry_run=dry_run, **changes)`.
- `obsidian_creation_backlog_list(project=None, status=None, priority=None, vault=None)` — `readOnlyHint=True, idempotentHint=True`; returns `json.dumps({"items": list_backlog(...)}, indent=2)`.
- `obsidian_creation_backlog_show(item_id: str, vault=None)` — `readOnlyHint=True, idempotentHint=True`; returns `json.dumps(show_backlog_item(...) or {"ok": False, "error": {"type": "NotFound", "message": item_id}}, indent=2)`.
- `obsidian_creation_rebuild(dry_run: bool = True, vault=None)` — `readOnlyHint=False, idempotentHint=True`; calls `rebuild_backlog(vault_path, dry_run=dry_run)`.

Each follows the same try/except envelope + lazy-import pattern.

- [ ] **Step 2: Bump the tool count.** In `mcpb.json`, change `"tools_count": 118,` to `"tools_count": 123,`.

- [ ] **Step 3: Run the integrity check, expect 8/8 PASS.** Run: `python3 scripts/integrity_check.py`. Expected: all checks PASS, including the CLI↔MCP parity check and the `tools_count` match. If parity fails, reconcile the CLI verb names and MCP tool names until the check is green (do not silence the check).

- [ ] **Step 4: Run the manifest check, expect PASS.** Run: `python3 scripts/manifest_check.py`. Expected: PASS. If it reports a documented count that must move, update the doc it names.

- [ ] **Step 5: Document the verbs in `TOOLS_CONTRACT.md`.** Add the five `creation backlog`/`rebuild` CLI verbs and their `obsidian_creation_backlog_*`/`obsidian_creation_rebuild` MCP mirrors to the relevant section, matching the format used for the spine's `creation status|sync|freshness-audit` entries.

- [ ] **Step 6: Run the full creation + hardening + build suites.** Run:
```bash
python3 -m pytest tests/test_creation_backlog.py tests/test_creation_backlog_cli.py tests/test_hardening.py tests/test_build_system.py -v
```
Expected: all PASS. `test_build_system.py` skill count is unchanged (no new skill) and must stay green.

- [ ] **Step 7: Commit.**

```bash
git add obsidian_connector/mcp_server.py mcpb.json TOOLS_CONTRACT.md
git commit -m "feat(creation): MCP parity for backlog + rebuild; tools_count 123; contract"
```

---

## Self-Review (controller, before dispatch)

- **Spec coverage:** backlog primitive (add/update/list/show) ✓ Task 1-2; event-sourced source of truth ✓ Task 1; materialized fence-preserving notes ✓ Task 1; idempotent `rebuild` ✓ Task 1; hybrid completion gate ✓ Task 1; CLI ✓ Task 2; MCP parity + contract + counts ✓ Task 3; folder layout `Backlog/{project}/{id}.md` ✓.
- **Type consistency:** `_reduce` returns `dict[str, dict]`; `list_backlog -> list[dict]`; `show_backlog_item -> dict | None`; event payload shape `{"item": {...}}` is identical in `add`, `update`, and `_reduce`. CLI imports `creation_backlog as _cbl`; MCP imports the functions lazily. `UPDATABLE_FIELDS` gates both the module `update` and the CLI/MCP change dicts.
- **Placeholders:** none — complete code for the module, all unit tests, all CLI code+tests; MCP `add` shown in full with the remaining four specified by exact signature + behavior against the identical, already-shown pattern.
- **Acceptance flow D** (stale note never overwrites higher-authority state): satisfied structurally — markdown is a view; `update`/`rebuild` always re-derive from events; the completion gate refuses unevidenced `done`.
