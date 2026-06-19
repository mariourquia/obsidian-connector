---
title: "Creation Spine v0 Implementation Plan"
status: draft
owner: mariourquia
last_reviewed: "2026-06-18"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/cli.py"
  - "obsidian_connector/write_manager.py"
  - "obsidian_connector/__init__.py"
related_docs:
  - "./2026-06-18-creation-vault-os.md"
  - "../architecture/creation-vault-schema.md"
  - "../architecture/creation-session-state.md"
tags: ["creation-vault-os", "plan", "implementation", "spine"]
---

# Creation Spine v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Creation Vault OS foundation: a freshness/authority spine, an append-only event log, a resumable session lifecycle, and `obsx creation status|sync|freshness-audit`, so stale memory can never silently corrupt current vault state.

**Architecture:** New `creation_*` modules in `obsidian_connector/` over the existing shared core. State changes are appended to an immutable JSONL event log living OUTSIDE iCloud; canonical markdown is a materialized view rebuilt from events. Every canonical note carries a provenance + freshness frontmatter block, and an authority hierarchy resolves conflicts. CLI only this PR (MCP parity is Phase 5).

**Tech Stack:** Python >=3.11 (stdlib only for the spine: `json`, `pathlib`, `dataclasses`, `datetime`, `hashlib`; no new deps), pytest, the existing `write_manager.atomic_write`, `audit.log_action`, and `envelope` helpers.

## Global Constraints

- Python >=3.11; type hints on every new/modified function; `black` + `isort` + `ruff` clean.
- Spine modules are stdlib-only. No new runtime dependencies in `pyproject.toml`.
- The event log + derived index live OUTSIDE iCloud at `~/.obsidian-connector/creation/<vault-id>/` (decision: hybrid vault location). NEVER write the event log inside the vault.
- All VAULT writes go through `write_manager.atomic_write(...)`; raw `write_text` to the vault fails `tests/test_hardening.py`. The event log is NOT in the vault, so it uses a dedicated atomic append helper (write temp + `os.replace`), not `atomic_write`.
- CLI mutating commands take `--dry-run` and call `audit.log_action(...)`; all commands support `--json` returning the canonical envelope `{ok, command, vault, duration_ms, data|error}`.
- Freshness gate is HYBRID: label + warn everywhere; hard-block only `done` / `pr_merged` status transitions that lack `source_commit` or `source_pr` evidence.
- Add-command recipe (from CLAUDE.md): core fn → export in `__init__.py` → argparse subcommand in `cli.py` (human + `--json`) → smoke test in `scripts/` → pytest → update `TOOLS_CONTRACT.md`. MCP `@mcp.tool` wrappers are explicitly deferred to Phase 5.
- Machine IDs are ULID-style with a type prefix (`bkl_`, `ses_`, `chk_`, `ctxp_`, `dec_`). For determinism without `Math.random`, derive the 80-bit random component from `hashlib.sha256(seed)` where `seed` is caller-supplied (timestamp + counter + content); never from a wall clock inside the function.
- Commits: Conventional Commits style, no `Co-Authored-By` trailer, signed.

---

### Task 1: Out-of-iCloud state dir resolution (`creation_paths.py`)

**Files:**
- Create: `obsidian_connector/creation_paths.py`
- Test: `tests/test_creation_paths.py`

**Interfaces:**
- Consumes: `config.resolve_vault_path` (existing).
- Produces: `creation_state_dir(vault_path: Path) -> Path` (returns `~/.obsidian-connector/creation/<vault-id>/`, created if absent; `<vault-id>` = first 16 hex of sha256 of the resolved vault path); `events_path(vault_path: Path) -> Path` (`<state>/events/creation_events.jsonl`); `index_dir(vault_path: Path) -> Path` (`<state>/index/`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_creation_paths.py
import hashlib
from pathlib import Path
from obsidian_connector import creation_paths


def test_state_dir_is_outside_vault_and_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "icloud" / "creation"
    vault.mkdir(parents=True)
    d1 = creation_paths.creation_state_dir(vault)
    d2 = creation_paths.creation_state_dir(vault)
    assert d1 == d2                                   # stable
    assert str(tmp_path / "icloud") not in str(d1)    # NOT inside the vault
    assert d1.is_dir()                                # created
    vid = hashlib.sha256(str(vault.resolve()).encode()).hexdigest()[:16]
    assert d1.name == vid


def test_events_path_under_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; vault.mkdir()
    ev = creation_paths.events_path(vault)
    assert ev.name == "creation_events.jsonl"
    assert ev.parent.name == "events"
    assert ev.parent.parent == creation_paths.creation_state_dir(vault)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_creation_paths.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError: module ... has no attribute 'creation_state_dir'`.

- [ ] **Step 3: Write minimal implementation**

```python
# obsidian_connector/creation_paths.py
"""Filesystem paths for Creation Vault OS state that must live OUTSIDE iCloud.

The canonical markdown notes live in the iCloud vault; the hot, append-only event
log and derived indexes live here, beside the existing audit log, so a hot-append
file never races iCloud sync. See docs/plans/2026-06-18-creation-vault-os.md.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _root() -> Path:
    return Path(os.path.expanduser("~/.obsidian-connector/creation"))


def _vault_id(vault_path: Path) -> str:
    return hashlib.sha256(str(Path(vault_path).resolve()).encode()).hexdigest()[:16]


def creation_state_dir(vault_path: Path) -> Path:
    d = _root() / _vault_id(vault_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def events_path(vault_path: Path) -> Path:
    d = creation_state_dir(vault_path) / "events"
    d.mkdir(parents=True, exist_ok=True)
    return d / "creation_events.jsonl"


def index_dir(vault_path: Path) -> Path:
    d = creation_state_dir(vault_path) / "index"
    d.mkdir(parents=True, exist_ok=True)
    return d
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_creation_paths.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add obsidian_connector/creation_paths.py tests/test_creation_paths.py
git commit -m "feat(creation): out-of-iCloud state dir resolution"
```

---

### Task 2: Freshness block + machine IDs (`creation_schema.py`)

**Files:**
- Create: `obsidian_connector/creation_schema.py`
- Test: `tests/test_creation_schema.py`

**Interfaces:**
- Produces:
  - `STATUS_LABELS: tuple[str, ...]` = `("verified_current", "fresh_user_instruction", "repo_grounded", "agent_reported_unverified", "stale_needs_review", "deprecated", "conflicting")`.
  - `@dataclass(frozen=True) Freshness` with fields: `id: str`, `authority_level: str`, `confidence: float = 0.5`, `last_verified_at: str | None = None`, `last_verified_by: str | None = None`, `verification_source: str | None = None`, `source_repo: str | None = None`, `source_branch: str | None = None`, `source_commit: str | None = None`, `source_pr: str | None = None`, `source_session: str | None = None`, `staleness_policy: str = "manual"`, `valid_until: str | None = None`, `supersedes: tuple[str, ...] = ()`, `superseded_by: str | None = None`.
  - `new_id(prefix: str, seed: str) -> str` (deterministic ULID-style id; prefix in `bkl|ses|chk|ctxp|dec`).
  - `freshness_to_dict(f: Freshness) -> dict` and `freshness_from_dict(d: dict) -> Freshness` (round-trip; unknown keys ignored, missing keys defaulted).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_creation_schema.py
import pytest
from obsidian_connector import creation_schema as cs


def test_status_labels_exact():
    assert cs.STATUS_LABELS == (
        "verified_current", "fresh_user_instruction", "repo_grounded",
        "agent_reported_unverified", "stale_needs_review", "deprecated", "conflicting",
    )


def test_new_id_deterministic_and_prefixed():
    a = cs.new_id("bkl", "2026-06-18T00:00:00Z|0|hello")
    b = cs.new_id("bkl", "2026-06-18T00:00:00Z|0|hello")
    c = cs.new_id("bkl", "2026-06-18T00:00:00Z|1|hello")
    assert a == b and a != c
    assert a.startswith("bkl_")


def test_freshness_round_trip_defaults_and_unknown_keys():
    f = cs.Freshness(id="bkl_x", authority_level="repo_grounded", source_commit="abc1234")
    d = cs.freshness_to_dict(f)
    d["totally_unknown"] = "ignore me"          # tolerate forward-compat keys
    back = cs.freshness_from_dict(d)
    assert back.id == "bkl_x"
    assert back.authority_level == "repo_grounded"
    assert back.source_commit == "abc1234"
    assert back.staleness_policy == "manual"     # defaulted
    assert back.supersedes == ()


def test_freshness_rejects_unknown_authority_level():
    with pytest.raises(ValueError, match="authority_level"):
        cs.Freshness(id="x", authority_level="totally-made-up")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_creation_schema.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# obsidian_connector/creation_schema.py
"""Freshness/authority frontmatter schema + machine IDs for the Creation Vault OS.

See docs/architecture/creation-vault-schema.md.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, fields

STATUS_LABELS: tuple[str, ...] = (
    "verified_current",
    "fresh_user_instruction",
    "repo_grounded",
    "agent_reported_unverified",
    "stale_needs_review",
    "deprecated",
    "conflicting",
)
_ID_PREFIXES = {"bkl", "ses", "chk", "ctxp", "dec"}
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str, seed: str) -> str:
    """Deterministic ULID-style id. The random component is derived from a
    caller-supplied seed (timestamp + counter + content) so callers stay
    testable and resume-safe; this function never reads a clock."""
    if prefix not in _ID_PREFIXES:
        raise ValueError(f"unknown id prefix: {prefix!r}")
    digest = hashlib.sha256(seed.encode()).digest()
    n = int.from_bytes(digest[:13], "big")          # 104 bits -> 21 base32 chars
    chars = []
    for _ in range(21):
        n, rem = divmod(n, 32)
        chars.append(_CROCKFORD[rem])
    return f"{prefix}_" + "".join(reversed(chars))


@dataclass(frozen=True)
class Freshness:
    id: str
    authority_level: str
    confidence: float = 0.5
    last_verified_at: str | None = None
    last_verified_by: str | None = None
    verification_source: str | None = None
    source_repo: str | None = None
    source_branch: str | None = None
    source_commit: str | None = None
    source_pr: str | None = None
    source_session: str | None = None
    staleness_policy: str = "manual"     # manual | ttl | repo-commit
    valid_until: str | None = None
    supersedes: tuple[str, ...] = ()
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        if self.authority_level not in STATUS_LABELS:
            raise ValueError(f"authority_level must be one of {STATUS_LABELS}")


def freshness_to_dict(f: Freshness) -> dict:
    out: dict = {}
    for fld in fields(Freshness):
        val = getattr(f, fld.name)
        if isinstance(val, tuple):
            val = list(val)
        out[fld.name] = val
    return out


def freshness_from_dict(d: dict) -> Freshness:
    known = {fld.name for fld in fields(Freshness)}
    kwargs = {k: v for k, v in d.items() if k in known}
    if "supersedes" in kwargs and kwargs["supersedes"] is not None:
        kwargs["supersedes"] = tuple(kwargs["supersedes"])
    return Freshness(**kwargs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_creation_schema.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add obsidian_connector/creation_schema.py tests/test_creation_schema.py
git commit -m "feat(creation): freshness/authority block + deterministic machine IDs"
```

---

### Task 3: Authority + staleness resolution (`creation_freshness.py`)

**Files:**
- Create: `obsidian_connector/creation_freshness.py`
- Test: `tests/test_creation_freshness.py`

**Interfaces:**
- Consumes: `creation_schema.Freshness`, `STATUS_LABELS`.
- Produces:
  - `is_stale(f: Freshness, *, repo_head: str | None = None, now_iso: str | None = None) -> bool` (policy `repo-commit`: stale when `source_commit != repo_head`; `ttl`: stale when `valid_until < now_iso`; `manual`: never).
  - `resolve_label(f: Freshness, *, repo_head: str | None = None, now_iso: str | None = None) -> str` (downgrades to `stale_needs_review` when `is_stale`; otherwise returns `f.authority_level`).
  - `can_complete(f: Freshness) -> tuple[bool, str]` (the hybrid hard-gate: `done`/`pr_merged` claims require `source_commit` or `source_pr`; returns `(ok, reason)`).
  - `AUTHORITY_ORDER: tuple[str, ...]` highest-to-lowest for conflict resolution.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_creation_freshness.py
from obsidian_connector import creation_schema as cs
from obsidian_connector import creation_freshness as cf


def _f(**kw):
    base = dict(id="bkl_x", authority_level="repo_grounded")
    base.update(kw)
    return cs.Freshness(**base)


def test_repo_commit_staleness():
    f = _f(staleness_policy="repo-commit", source_commit="abc")
    assert cf.is_stale(f, repo_head="abc") is False
    assert cf.is_stale(f, repo_head="def") is True            # HEAD moved -> stale


def test_ttl_staleness():
    f = _f(staleness_policy="ttl", valid_until="2026-06-20")
    assert cf.is_stale(f, now_iso="2026-06-19") is False
    assert cf.is_stale(f, now_iso="2026-06-25") is True


def test_resolve_label_downgrades_stale():
    f = _f(staleness_policy="repo-commit", source_commit="abc")
    assert cf.resolve_label(f, repo_head="def") == "stale_needs_review"
    assert cf.resolve_label(f, repo_head="abc") == "repo_grounded"


def test_can_complete_requires_evidence():
    ok, _ = cf.can_complete(_f(source_commit="abc"))
    assert ok is True
    ok, reason = cf.can_complete(_f())                         # no commit, no PR
    assert ok is False and "evidence" in reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_creation_freshness.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# obsidian_connector/creation_freshness.py
"""Authority hierarchy + staleness for the Creation Vault OS freshness spine."""
from __future__ import annotations

from .creation_schema import Freshness

AUTHORITY_ORDER: tuple[str, ...] = (
    "fresh_user_instruction",
    "repo_grounded",
    "verified_current",
    "agent_reported_unverified",
    "stale_needs_review",
    "conflicting",
    "deprecated",
)


def is_stale(f: Freshness, *, repo_head: str | None = None, now_iso: str | None = None) -> bool:
    if f.staleness_policy == "repo-commit":
        return bool(f.source_commit) and repo_head is not None and f.source_commit != repo_head
    if f.staleness_policy == "ttl":
        return bool(f.valid_until) and now_iso is not None and now_iso > f.valid_until
    return False


def resolve_label(f: Freshness, *, repo_head: str | None = None, now_iso: str | None = None) -> str:
    if is_stale(f, repo_head=repo_head, now_iso=now_iso):
        return "stale_needs_review"
    return f.authority_level


def can_complete(f: Freshness) -> tuple[bool, str]:
    if f.source_commit or f.source_pr:
        return True, "has repo evidence"
    return False, "completion requires repo evidence (source_commit or source_pr)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_creation_freshness.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add obsidian_connector/creation_freshness.py tests/test_creation_freshness.py
git commit -m "feat(creation): authority hierarchy + staleness + completion gate"
```

---

### Task 4: Append-only event log (`creation_events.py`)

**Files:**
- Create: `obsidian_connector/creation_events.py`
- Test: `tests/test_creation_events.py`

**Interfaces:**
- Consumes: `creation_paths.events_path`.
- Produces:
  - `append_event(vault_path: Path, event_type: str, payload: dict, *, event_id: str, ts_iso: str, session_id: str | None = None) -> dict` (writes one JSON object per line atomically via temp-file + `os.replace` of an appended copy; returns the written record). Records: `{event_id, ts, event_type, session_id, payload}`.
  - `read_events(vault_path: Path) -> list[dict]` (parses the JSONL; tolerates and skips malformed lines, counting them).
  - `EVENT_TYPES: frozenset[str]` covering the spine: `session.start`, `checkpoint.created`, `checkpoint.emergency`, `session.end`, `session.blocked`, `backlog.upserted`, `decision.pending`, `decision.resolved`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_creation_events.py
from pathlib import Path
from obsidian_connector import creation_events as ce


def test_append_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; vault.mkdir()
    ce.append_event(vault, "session.start", {"repo": "x"},
                    event_id="ses_a", ts_iso="2026-06-18T00:00:00Z", session_id="ses_a")
    ce.append_event(vault, "checkpoint.created", {"n": 1},
                    event_id="chk_b", ts_iso="2026-06-18T00:01:00Z", session_id="ses_a")
    events = ce.read_events(vault)
    assert [e["event_type"] for e in events] == ["session.start", "checkpoint.created"]
    assert events[0]["payload"]["repo"] == "x"
    assert events[1]["session_id"] == "ses_a"


def test_read_tolerates_malformed_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; vault.mkdir()
    ce.append_event(vault, "session.start", {},
                    event_id="ses_a", ts_iso="2026-06-18T00:00:00Z")
    from obsidian_connector import creation_paths
    with creation_paths.events_path(vault).open("a") as fh:
        fh.write("this is not json\n")
    events = ce.read_events(vault)
    assert len(events) == 1                       # malformed line skipped, valid kept


def test_unknown_event_type_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; vault.mkdir()
    import pytest
    with pytest.raises(ValueError, match="event_type"):
        ce.append_event(vault, "totally.bogus", {}, event_id="x", ts_iso="t")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_creation_events.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_creation_events.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add obsidian_connector/creation_events.py tests/test_creation_events.py
git commit -m "feat(creation): append-only JSONL event log"
```

---

### Task 5: Session lifecycle (`creation_session.py`)

**Files:**
- Create: `obsidian_connector/creation_session.py`
- Modify: `obsidian_connector/__init__.py` (export the public session API)
- Test: `tests/test_creation_session.py`

**Interfaces:**
- Consumes: `creation_events.append_event`, `creation_schema.new_id`, `write_manager.atomic_write`, `config.resolve_vault_path`.
- Produces:
  - `start_session(vault_path, *, repo, branch, backlog_id=None, now_iso, dry_run=False) -> dict` (emits `session.start`, materializes `sessions/{id}.md` + `sessions/_active.md`; returns `{session_id, path, dry_run}`).
  - `checkpoint_session(vault_path, *, session_id, summary, next_steps, blockers, confidence, now_iso, emergency=False, dry_run=False) -> dict`.
  - `end_session(vault_path, *, session_id, report, next_action, now_iso, status="closed", dry_run=False) -> dict` (clears `_active.md`).
  - `active_session(vault_path) -> str | None` (reads `_active.md`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_creation_session.py
from obsidian_connector import creation_session as csess
from obsidian_connector import creation_events as ce


def test_start_creates_active_marker_and_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    res = csess.start_session(vault, repo="mcmc-erp", branch="main",
                              now_iso="2026-06-18T00:00:00Z")
    sid = res["session_id"]
    assert sid.startswith("ses_")
    assert csess.active_session(vault) == sid
    assert (vault / "sessions" / f"{sid}.md").exists()
    assert ce.read_events(vault)[0]["event_type"] == "session.start"


def test_end_clears_active_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    sid = csess.start_session(vault, repo="x", branch="main",
                              now_iso="2026-06-18T00:00:00Z")["session_id"]
    csess.end_session(vault, session_id=sid, report="done", next_action="ship",
                      now_iso="2026-06-18T01:00:00Z")
    assert csess.active_session(vault) is None
    types = [e["event_type"] for e in ce.read_events(vault)]
    assert types == ["session.start", "session.end"]


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    res = csess.start_session(vault, repo="x", branch="main",
                              now_iso="2026-06-18T00:00:00Z", dry_run=True)
    assert res["dry_run"] is True
    assert csess.active_session(vault) is None
    assert ce.read_events(vault) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_creation_session.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
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


def _session_md(session_id: str, repo: str, branch: str, backlog_id, started_at: str) -> str:
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
```

- [ ] **Step 4: Add exports to `__init__.py`**

In `obsidian_connector/__init__.py`, add to the public re-exports:

```python
from .creation_session import start_session, checkpoint_session, end_session, active_session
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_creation_session.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add obsidian_connector/creation_session.py obsidian_connector/__init__.py tests/test_creation_session.py
git commit -m "feat(creation): resumable session lifecycle (start/checkpoint/end)"
```

---

### Task 6: Status + freshness audit (`creation_status.py`)

**Files:**
- Create: `obsidian_connector/creation_status.py`
- Test: `tests/test_creation_status.py`

**Interfaces:**
- Consumes: `creation_events.read_events`, `creation_session.active_session`, `creation_freshness`.
- Produces:
  - `creation_status(vault_path) -> dict` (`{active_session, recent_events, event_count, stale_warnings}`; pure read, no writes).
  - `freshness_audit(vault_path, *, repo_heads: dict[str, str] | None = None, now_iso: str | None = None) -> dict` (scans materialized backlog/session notes, returns `{stale: [...], conflicting: [...], checked: N}`). For v0, scans `Backlog/**/*.md` frontmatter only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_creation_status.py
from obsidian_connector import creation_status as cstat
from obsidian_connector import creation_session as csess


def test_status_reports_active_session_and_event_count(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    sid = csess.start_session(vault, repo="x", branch="main",
                              now_iso="2026-06-18T00:00:00Z")["session_id"]
    st = cstat.creation_status(vault)
    assert st["active_session"] == sid
    assert st["event_count"] == 1


def test_freshness_audit_flags_stale_backlog(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; (vault / "Backlog" / "mcmc").mkdir(parents=True)
    (vault / "Backlog" / "mcmc" / "bkl_x.md").write_text(
        "---\nid: bkl_x\ntype: backlog-item\nauthority_level: repo_grounded\n"
        "staleness_policy: repo-commit\nsource_repo: mcmc-erp\nsource_commit: abc\n---\n",
        encoding="utf-8")
    audit = cstat.freshness_audit(vault, repo_heads={"mcmc-erp": "def"})
    assert "bkl_x" in [i["id"] for i in audit["stale"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_creation_status.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# obsidian_connector/creation_status.py
"""Read-only `creation status` + `freshness-audit` (the dashboard read-view seed)."""
from __future__ import annotations

from pathlib import Path

from . import creation_events as ce
from . import creation_freshness as cf
from . import creation_schema as cs
from . import creation_session as csess
from .draft_manager import _parse_frontmatter  # existing simple key:value YAML reader


def creation_status(vault_path: Path) -> dict:
    events = ce.read_events(vault_path)
    return {
        "active_session": csess.active_session(vault_path),
        "event_count": len(events),
        "recent_events": events[-10:],
        "stale_warnings": freshness_audit(vault_path).get("stale", []),
    }


def _load_freshness(md_path: Path) -> cs.Freshness | None:
    fm = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
    if not fm or "authority_level" not in fm:
        return None
    try:
        return cs.freshness_from_dict(fm)
    except (ValueError, TypeError):
        return None


def freshness_audit(vault_path: Path, *, repo_heads: dict | None = None,
                    now_iso: str | None = None) -> dict:
    repo_heads = repo_heads or {}
    stale, conflicting, checked = [], [], 0
    for md in sorted((Path(vault_path) / "Backlog").rglob("*.md")):
        f = _load_freshness(md)
        if f is None:
            continue
        checked += 1
        head = repo_heads.get(f.source_repo or "")
        if f.authority_level == "conflicting":
            conflicting.append({"id": f.id, "path": str(md)})
        elif cf.is_stale(f, repo_head=head, now_iso=now_iso):
            stale.append({"id": f.id, "path": str(md), "source_repo": f.source_repo})
    return {"stale": stale, "conflicting": conflicting, "checked": checked}
```

Note: `_parse_frontmatter` is the existing regex frontmatter reader in `draft_manager.py`. If its name/signature differs, add a 3-line local YAML-lite reader instead of importing a private helper.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_creation_status.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add obsidian_connector/creation_status.py tests/test_creation_status.py
git commit -m "feat(creation): status + freshness-audit read views"
```

---

### Task 7: CLI surface (`creation` subcommands)

**Files:**
- Modify: `obsidian_connector/cli.py` (register `creation` parent + subcommands; human + `--json`)
- Modify: `obsidian_connector/__init__.py` (export `creation_status`, `freshness_audit`)
- Test: `tests/test_creation_cli.py`

**Interfaces:**
- Consumes: all the above. Produces the canonical envelope through the existing `envelope` helper.
- Subcommands: `creation status`, `creation sync start|checkpoint|end`, `creation freshness-audit`. Each accepts `--json`; the `sync` writes accept `--dry-run` and `--allow-write` (default dry-run unless `--allow-write`), and call `audit.log_action`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_creation_cli.py
import json
import subprocess
import sys


def _run(args, env_home, vault):
    return subprocess.run(
        [sys.executable, "-m", "obsidian_connector.cli", "--json", "--vault", str(vault), *args],
        capture_output=True, text=True,
        env={"HOME": str(env_home), "PATH": __import__("os").environ["PATH"]},
    )


def test_creation_status_json_envelope(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    p = _run(["creation", "status"], home, vault)
    assert p.returncode == 0, p.stderr
    env = json.loads(p.stdout)
    assert env["ok"] is True
    assert env["command"].startswith("creation")
    assert "active_session" in env["data"]


def test_creation_sync_start_dry_run_default(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    vault = tmp_path / "v"; (vault / ".obsidian").mkdir(parents=True)
    p = _run(["creation", "sync", "start", "--repo", "x", "--branch", "main"], home, vault)
    env = json.loads(p.stdout)
    assert env["ok"] is True
    assert env["data"]["dry_run"] is True            # default is dry-run
    assert not (vault / "sessions" / "_active.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_creation_cli.py -v`
Expected: FAIL (unknown subcommand `creation`).

- [ ] **Step 3: Register the subcommands in `cli.py`**

Add a `creation` subparser group near the other `add_subparsers` registrations, then dispatch. Use `now_iso = datetime.now(timezone.utc).isoformat()` at the CLI boundary (clock lives here, not in the pure modules):

```python
# in build_parser(): after the existing subparsers are defined
creation = sub.add_parser("creation", help="Creation Vault OS")
csub = creation.add_subparsers(dest="creation_cmd")
csub.add_parser("status", help="global status + stale warnings")
fa = csub.add_parser("freshness-audit", help="stale/conflicting report")
sync = csub.add_parser("sync", help="session lifecycle sync").add_subparsers(dest="sync_cmd")
s_start = sync.add_parser("start"); s_start.add_argument("--repo", required=True); s_start.add_argument("--branch", required=True); s_start.add_argument("--backlog-id"); s_start.add_argument("--allow-write", action="store_true"); s_start.add_argument("--dry-run", action="store_true")
s_ckpt = sync.add_parser("checkpoint"); s_ckpt.add_argument("--session-id", required=True); s_ckpt.add_argument("--summary", default=""); s_ckpt.add_argument("--next-steps", default=""); s_ckpt.add_argument("--blockers", default=""); s_ckpt.add_argument("--confidence", type=float, default=0.5); s_ckpt.add_argument("--emergency", action="store_true"); s_ckpt.add_argument("--allow-write", action="store_true"); s_ckpt.add_argument("--dry-run", action="store_true")
s_end = sync.add_parser("end"); s_end.add_argument("--session-id", required=True); s_end.add_argument("--report", default=""); s_end.add_argument("--next-action", default=""); s_end.add_argument("--status", default="closed"); s_end.add_argument("--allow-write", action="store_true"); s_end.add_argument("--dry-run", action="store_true")
```

Dispatch block (mirrors the existing `elif args.command == ...` chain). `_creation_now()` returns the UTC ISO timestamp; writes are dry-run unless `--allow-write` is passed:

```python
elif args.command == "creation":
    from . import creation_status as _cstat, creation_session as _csess
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    if args.creation_cmd == "status":
        data = _cstat.creation_status(vault)
    elif args.creation_cmd == "freshness-audit":
        data = _cstat.freshness_audit(vault)
    elif args.creation_cmd == "sync":
        dry = args.dry_run or not args.allow_write
        if args.sync_cmd == "start":
            data = _csess.start_session(vault, repo=args.repo, branch=args.branch,
                                        backlog_id=args.backlog_id, now_iso=now, dry_run=dry)
        elif args.sync_cmd == "checkpoint":
            data = _csess.checkpoint_session(vault, session_id=args.session_id,
                                             summary=args.summary, next_steps=args.next_steps,
                                             blockers=args.blockers, confidence=args.confidence,
                                             now_iso=now, emergency=args.emergency, dry_run=dry)
        elif args.sync_cmd == "end":
            data = _csess.end_session(vault, session_id=args.session_id, report=args.report,
                                      next_action=args.next_action, now_iso=now,
                                      status=args.status, dry_run=dry)
        log_action(f"creation-sync-{args.sync_cmd}", vars(args), vault, dry_run=dry)
    # wrap `data` in the canonical envelope exactly like the other commands
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_creation_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full suite + linters**

Run: `python3 -m pytest tests/ -q && ruff check obsidian_connector/creation_*.py && black --check obsidian_connector/creation_*.py`
Expected: all PASS / clean.

- [ ] **Step 6: Commit**

```bash
git add obsidian_connector/cli.py obsidian_connector/__init__.py tests/test_creation_cli.py
git commit -m "feat(creation): obsx creation status|sync|freshness-audit CLI"
```

---

### Task 8: Freshness-guard skill (guarded mode)

**Files:**
- Create: `src/skills/creation-vault-freshness-guard/SKILL.md`
- Test: `tests/test_creation_freshness_guard_skill.py` (asserts the skill file exists with valid frontmatter `name`/`description`, mirroring how other skills are validated)

**Interfaces:** none (a skill doc). Guarded mode = warn + label only; never blocks.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_creation_freshness_guard_skill.py
from pathlib import Path

SKILL = Path("src/skills/creation-vault-freshness-guard/SKILL.md")


def test_skill_exists_with_frontmatter():
    assert SKILL.exists()
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: creation-vault-freshness-guard" in text
    assert "description:" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_creation_freshness_guard_skill.py -v`
Expected: FAIL (file missing).

- [ ] **Step 3: Write the skill**

```markdown
---
name: creation-vault-freshness-guard
description: Use whenever loading vault context, writing to the vault, ingesting captures, or starting a work session. Detects stale/conflicting notes, downgrades unverified old information, and annotates context with freshness labels. Guarded mode: warns and labels, never blocks (except completion claims lacking repo evidence).
---

# Creation Vault Freshness Guard

Run `obsx creation freshness-audit --json` and `obsx creation status --json` before
relying on any vault fact. For each fact, attach its `authority_level`. Treat memory or
notes older than 7 days, or any item whose `source_commit` no longer matches repo HEAD, as
`stale_needs_review` and verify against git before acting. Refuse to mark a backlog item
`done` without `source_commit` or `source_pr` evidence. Emit a "Stale context warnings"
section in every startup context pack. Guarded mode: warn and label; do not block work
(the only hard block is unverified completion).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_creation_freshness_guard_skill.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/creation-vault-freshness-guard/SKILL.md tests/test_creation_freshness_guard_skill.py
git commit -m "feat(creation): freshness-guard skill (guarded mode)"
```

---

### Task 9: TOOLS_CONTRACT update + full-suite gate

**Files:**
- Modify: `TOOLS_CONTRACT.md` (document the 4 new CLI commands; note MCP parity is Phase 5)

- [ ] **Step 1: Add a "Creation Vault OS (spine v0)" section to `TOOLS_CONTRACT.md`** listing `creation status`, `creation sync start|checkpoint|end`, `creation freshness-audit` with their flags, the canonical envelope, and a note that MCP `obsidian_creation_*` parity lands in Phase 5.

- [ ] **Step 2: Run the integrity + full test gate**

Run: `python3 scripts/integrity_check.py && python3 -m pytest tests/ -q`
Expected: integrity PASS; full suite PASS (existing + new creation tests).

- [ ] **Step 3: Commit**

```bash
git add TOOLS_CONTRACT.md
git commit -m "docs(creation): document spine v0 CLI in TOOLS_CONTRACT"
```

---

## Deferred to later PRs (NOT in spine v0)

Backlog-item materialization + `backlog add|update`, migration backfill of existing
`running-todo`/commitments/open-loops into `stale_needs_review` backlog items, the Project
entity + dashboards (Phase 4), the interactive console + TUI (Phase 6), `next` / `handoff`
/ `reprioritize`, voice-to-backlog (Phase 3), MCP parity (Phase 5), and the agentops
`creation sync plan|spec|files|tests|commit|pr` wiring (Phase 9). The agentops
SessionStart/SessionEnd/git-mutation auto-sync hooks already shipped in mario-agentops PR
#17. `obsx creation status` here is the seed of the dashboard read-view.

## Self-Review

- **Spec coverage:** spine v0 first-PR scope from the master plan (schema, event log,
  freshness guard, `creation status`, `creation sync start|checkpoint|end`,
  `freshness-audit`) is covered by Tasks 1-9. Backlog materialization is explicitly
  deferred above with a pointer.
- **Placeholder scan:** every code step has concrete code; commands have expected output.
  The one soft reference (`_parse_frontmatter`) carries an explicit fallback instruction.
- **Type consistency:** `Freshness`, `new_id(prefix, seed)`, `append_event(... event_id,
  ts_iso ...)`, and the session API signatures are used identically across Tasks 2-7.
