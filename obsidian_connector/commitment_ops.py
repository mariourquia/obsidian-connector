"""High-level commitment state operations.

Provides list, inspect, mutate, and sync operations for commitment notes.
Sits above ``commitment_notes.py`` (rendering/writing) and below the MCP
tools and CLI (presentation layer).

Service integration
-------------------
When ``OBSIDIAN_CAPTURE_SERVICE_URL`` (and optionally
``OBSIDIAN_CAPTURE_SERVICE_TOKEN``) are set, mutating commands
(``mark_commitment_done``, ``postpone_commitment``) also PATCH the remote
action via the service API.  Service errors are non-fatal: the local vault
write always completes first, and the result dict includes a ``service_sync``
key that reports what happened.

``sync_commitments_from_service`` fetches all open actions from the service
and writes them into the vault.  When the service is unavailable it returns
``{"ok": False, "error": "..."}`` without touching the vault.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from obsidian_connector.commitment_notes import (
    ActionInput,
    COMMITMENTS_ROOT,
    USER_NOTES_BEGIN,
    find_commitment_note,
    parse_frontmatter,
    write_commitment_note,
)
from obsidian_connector.write_manager import atomic_write


# ---------------------------------------------------------------------------
# URL safety guard
# ---------------------------------------------------------------------------

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})


# ---------------------------------------------------------------------------
# Read-only summary
# ---------------------------------------------------------------------------

@dataclass
class CommitmentSummary:
    """Lightweight view of a commitment note parsed from frontmatter + body.

    Task 26 adds ``created_at``, ``updated_at``, ``lifecycle_stage``,
    ``urgency``, ``source_app``, ``source_entrypoint``, ``people``, and
    ``areas`` in backward-compatible slots.  Pre-Task-26 scanners keep
    working because the new fields carry safe defaults.
    """

    action_id: str
    title: str
    status: str
    priority: str
    project: str | None
    due_at: str | None
    postponed_until: str | None
    requires_ack: bool
    path: str  # vault-relative POSIX path
    # Task 26 additions (all optional, safe defaults for legacy notes).
    created_at: str | None = None  # body-line "- Created: ..."
    updated_at: str | None = None  # frontmatter "service_last_synced_at"
    lifecycle_stage: str = "inbox"
    urgency: str = "normal"
    source_app: str | None = None
    source_entrypoint: str | None = None
    people: tuple[str, ...] = ()
    areas: tuple[str, ...] = ()


def _bool_from_fm(value: str) -> bool:
    return value.lower() in {"true", "yes", "1"}


def _null_or(value: str) -> str | None:
    """Return None when value is the YAML null sentinel, else the string."""
    return None if (not value or value.lower() == "null") else value


_FM_CREATED_AT_RE = re.compile(r"^-\s+Created:\s*(.+)$", re.MULTILINE)
_FM_FLOW_LIST_RE = re.compile(r"\[([^\]]*)\]")


def _parse_fm_flow_list(raw: str) -> tuple[str, ...]:
    """Parse a YAML flow list like ``[alice, bob]`` into a tuple of strings.

    Empty input, ``[]`` or a malformed value yields ``()``.  Values are
    trimmed and unquoted.  Tuples are used so :class:`CommitmentSummary`
    stays hashable for dedup checks in tests and heuristics.
    """
    if not raw:
        return ()
    m = _FM_FLOW_LIST_RE.match(raw.strip())
    if not m:
        return ()
    inner = m.group(1).strip()
    if not inner:
        return ()
    items: list[str] = []
    for piece in inner.split(","):
        v = piece.strip().strip('"').strip("'")
        if v:
            items.append(v)
    return tuple(items)


def _parse_commitment_file(path: Path, vault_root: Path) -> CommitmentSummary | None:
    """Parse frontmatter of *path* into a CommitmentSummary.

    Returns ``None`` when the file is unreadable, has no frontmatter, or is
    not a commitment note.

    Reads up to 8 KiB so the ``- Created:`` body line (Task 26) lands in
    the parsed slice even for notes with long frontmatter flow lists.
    """
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:8192]
    except OSError:
        return None
    fm = parse_frontmatter(head)
    if fm.get("type") != "commitment":
        return None
    action_id = fm.get("action_id", "")
    if not action_id:
        return None
    rel = path.relative_to(vault_root).as_posix()
    # Body-side Created: line -- authoritative for Task 26 review windows.
    cm = _FM_CREATED_AT_RE.search(head)
    created_at = cm.group(1).strip() if cm else None
    return CommitmentSummary(
        action_id=action_id,
        title=fm.get("title", ""),
        status=fm.get("status", "open"),
        priority=fm.get("priority", "normal"),
        project=_null_or(fm.get("project", "")),
        due_at=_null_or(fm.get("due_at", "")),
        postponed_until=_null_or(fm.get("postponed_until", "")),
        requires_ack=_bool_from_fm(fm.get("requires_ack", "false")),
        path=rel,
        created_at=created_at,
        updated_at=_null_or(fm.get("service_last_synced_at", "")),
        lifecycle_stage=fm.get("lifecycle_stage", "inbox") or "inbox",
        urgency=fm.get("urgency", "normal") or "normal",
        source_app=_null_or(fm.get("source_app", "")),
        source_entrypoint=_null_or(fm.get("source_entrypoint", "")),
        people=_parse_fm_flow_list(fm.get("people", "")),
        areas=_parse_fm_flow_list(fm.get("areas", "")),
    )


def _scan_commitments(vault_root: Path) -> list[CommitmentSummary]:
    """Walk ``Commitments/`` and return all parseable commitment notes."""
    root = vault_root / COMMITMENTS_ROOT
    if not root.exists():
        return []
    results: list[CommitmentSummary] = []
    for md_path in sorted(root.rglob("*.md")):
        s = _parse_commitment_file(md_path, vault_root)
        if s is not None:
            results.append(s)
    return results


def _summary_to_dict(s: CommitmentSummary) -> dict:
    return {
        "action_id": s.action_id,
        "title": s.title,
        "status": s.status,
        "priority": s.priority,
        "project": s.project,
        "due_at": s.due_at,
        "postponed_until": s.postponed_until,
        "requires_ack": s.requires_ack,
        "path": s.path,
    }


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def list_commitments(
    vault_root: Path,
    status: str | None = None,
    project: str | None = None,
    priority: str | None = None,
) -> list[dict]:
    """Return all commitment notes, optionally filtered.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    status:
        Filter by ``"open"`` or ``"done"``.  Omit for all.
    project:
        Case-insensitive project name filter.
    priority:
        Filter by ``"low"``, ``"normal"``, or ``"high"``.
    """
    vault_root = Path(vault_root)
    items = _scan_commitments(vault_root)
    if status:
        items = [i for i in items if i.status == status]
    if project:
        items = [i for i in items if (i.project or "").lower() == project.lower()]
    if priority:
        items = [i for i in items if i.priority == priority]
    return [_summary_to_dict(s) for s in items]


def get_commitment(vault_root: Path, action_id: str) -> dict | None:
    """Return a single commitment summary, or ``None`` if not found."""
    vault_root = Path(vault_root)
    path = find_commitment_note(vault_root, action_id)
    if path is None:
        return None
    s = _parse_commitment_file(path, vault_root)
    return _summary_to_dict(s) if s is not None else None


def list_due_soon(vault_root: Path, within_days: int = 3) -> list[dict]:
    """Return open commitments with ``due_at`` within *within_days* from now.

    Results are sorted earliest-due first.  Each dict includes an
    ``overdue`` boolean when the due date is already past.
    """
    vault_root = Path(vault_root)
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=within_days)
    results: list[dict] = []
    for s in _scan_commitments(vault_root):
        if s.status != "open" or not s.due_at:
            continue
        try:
            due = datetime.fromisoformat(s.due_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if due <= cutoff:
            d = _summary_to_dict(s)
            d["overdue"] = due < now
            results.append(d)
    results.sort(key=lambda x: x["due_at"] or "")
    return results


# ---------------------------------------------------------------------------
# Reconstruction helper
# ---------------------------------------------------------------------------

_CHANNELS_FLOW_RE = re.compile(r"\[([^\]]*)\]")
_CREATED_AT_RE = re.compile(r"^- Created:\s+(.+)$", re.MULTILINE)


def _action_from_content(content: str, fm: dict) -> ActionInput:
    """Reconstruct an :class:`ActionInput` from on-disk note content and parsed
    frontmatter.

    This is intentionally tolerant: missing or malformed fields fall back to
    safe defaults so callers can always write the updated note back.

    Task 27 adds ``urgency``, ``lifecycle_stage``, ``source_app``,
    ``source_entrypoint``, ``people``, and ``areas``. Missing fields on
    pre-Task 27 notes hydrate as ``'normal'`` / ``'inbox'`` / ``None`` /
    ``[]`` so existing commitment notes roundtrip cleanly.
    """
    # created_at lives in the body (not frontmatter) to keep FM stable.
    m = _CREATED_AT_RE.search(content)
    created_at = m.group(1).strip() if m else datetime.now(timezone.utc).isoformat()

    # Parse YAML flow list: [push, sms] or []
    def _parse_flow_list(raw: str) -> list[str]:
        cm = _CHANNELS_FLOW_RE.match((raw or "").strip())
        if not cm:
            return []
        inner = cm.group(1).strip()
        if not inner:
            return []
        return [
            v.strip().strip('"').strip("'")
            for v in inner.split(",")
            if v.strip()
        ]

    channels = _parse_flow_list(fm.get("channels", "[]"))
    people = _parse_flow_list(fm.get("people", "[]"))
    areas = _parse_flow_list(fm.get("areas", "[]"))

    def _unquote(s: str) -> str | None:
        s = s.strip()
        if not s or s in ("null", "~"):
            return None
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
            return s[1:-1]
        return s

    return ActionInput(
        action_id=fm.get("action_id", ""),
        capture_id=fm.get("capture_id", ""),
        title=fm.get("title", ""),
        created_at=created_at,
        project=_unquote(fm.get("project", "null") or "null"),
        status=fm.get("status", "open"),
        priority=fm.get("priority", "normal"),
        due_at=_unquote(fm.get("due_at", "null") or "null"),
        postponed_until=_unquote(fm.get("postponed_until", "null") or "null"),
        requires_ack=fm.get("requires_ack", "false").lower() in {"true", "yes"},
        escalation_policy=_unquote(fm.get("escalation_policy", "null") or "null"),
        channels=channels,
        source_note=_unquote(fm.get("source_note", "null") or "null"),
        # Task 27
        urgency=fm.get("urgency", "normal") or "normal",
        lifecycle_stage=fm.get("lifecycle_stage", "inbox") or "inbox",
        source_app=_unquote(fm.get("source_app", "null") or "null"),
        source_entrypoint=_unquote(fm.get("source_entrypoint", "null") or "null"),
        people=people,
        areas=areas,
    )


# ---------------------------------------------------------------------------
# Mutating operations
# ---------------------------------------------------------------------------

def mark_commitment_done(
    vault_root: Path,
    action_id: str,
    completed_at: str | None = None,
    now_iso: str | None = None,
) -> dict:
    """Mark a commitment as done.

    Writes an updated note with ``status=done`` and moves the file from
    ``Open/`` to ``Done/``.  The follow-up log records the transition.

    When ``OBSIDIAN_CAPTURE_SERVICE_URL`` is set, also PATCHes the service.
    The PATCH is best-effort; a failure does not roll back the local write.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    action_id:
        ID of the commitment to mark done.
    completed_at:
        ISO 8601 completion timestamp.  Defaults to ``now_iso`` or UTC now.
    now_iso:
        Sync timestamp injected into the follow-up log.  Defaults to UTC now.

    Raises
    ------
    ValueError
        When *action_id* is not found in the vault.
    """
    vault_root = Path(vault_root)
    path = find_commitment_note(vault_root, action_id)
    if path is None:
        raise ValueError(f"commitment not found: {action_id!r}")

    content = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    prev_status = fm.get("status", "open")

    action = _action_from_content(content, fm)
    ts = completed_at or now_iso or datetime.now(timezone.utc).isoformat()

    done_action = ActionInput(
        action_id=action.action_id,
        capture_id=action.capture_id,
        title=action.title,
        created_at=action.created_at,
        project=action.project,
        status="done",
        priority=action.priority,
        due_at=action.due_at,
        postponed_until=action.postponed_until,
        requires_ack=action.requires_ack,
        escalation_policy=action.escalation_policy,
        channels=action.channels,
        source_note=action.source_note,
        completed_at=ts,
        # Task 27: preserve rich metadata; lifecycle_stage shifts to 'done'
        # on this transition because the service-side verb also does so.
        urgency=action.urgency,
        lifecycle_stage="done",
        source_app=action.source_app,
        source_entrypoint=action.source_entrypoint,
        people=action.people,
        areas=action.areas,
    )
    result = write_commitment_note(vault_root, done_action, now_iso=now_iso)

    out: dict = {
        "action_id": action_id,
        "previous_status": prev_status,
        "status": "done",
        "completed_at": ts,
        "path": result.path.relative_to(vault_root).as_posix(),
        "moved_from": (
            result.moved_from.relative_to(vault_root).as_posix()
            if result.moved_from else None
        ),
    }
    service = _try_service_patch(action_id, {"status": "done", "completed_at": ts})
    if service is not None:
        out["service_sync"] = service
    return out


def postpone_commitment(
    vault_root: Path,
    action_id: str,
    postponed_until: str,
    now_iso: str | None = None,
) -> dict:
    """Set or update ``postponed_until`` on an open commitment.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    action_id:
        ID of the commitment to postpone.
    postponed_until:
        ISO 8601 timestamp indicating when the commitment should resurface.
    now_iso:
        Sync timestamp injected into the follow-up log.

    Raises
    ------
    ValueError
        When *action_id* is not found.
    """
    vault_root = Path(vault_root)
    path = find_commitment_note(vault_root, action_id)
    if path is None:
        raise ValueError(f"commitment not found: {action_id!r}")

    content = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    action = _action_from_content(content, fm)

    updated = ActionInput(
        action_id=action.action_id,
        capture_id=action.capture_id,
        title=action.title,
        created_at=action.created_at,
        project=action.project,
        status=action.status,
        priority=action.priority,
        due_at=action.due_at,
        postponed_until=postponed_until,
        requires_ack=action.requires_ack,
        escalation_policy=action.escalation_policy,
        channels=action.channels,
        source_note=action.source_note,
        # Task 27: preserve rich metadata; lifecycle_stage shifts to 'waiting'
        # on postpone to mirror the service-side verb.
        urgency=action.urgency,
        lifecycle_stage="waiting",
        source_app=action.source_app,
        source_entrypoint=action.source_entrypoint,
        people=action.people,
        areas=action.areas,
    )
    result = write_commitment_note(vault_root, updated, now_iso=now_iso)

    out: dict = {
        "action_id": action_id,
        "status": action.status,
        "postponed_until": postponed_until,
        "path": result.path.relative_to(vault_root).as_posix(),
    }
    service = _try_service_patch(action_id, {"postponed_until": postponed_until})
    if service is not None:
        out["service_sync"] = service
    return out


def add_commitment_reason(
    vault_root: Path,
    action_id: str,
    reason: str,
    now_iso: str | None = None,
) -> dict:
    """Append a timestamped reason line to a commitment's user-notes block.

    The note is modified in-place via an atomic write; the renderer is not
    re-invoked so existing content (frontmatter, follow-up log) is preserved
    exactly.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    action_id:
        ID of the target commitment.
    reason:
        Non-empty reason text.
    now_iso:
        Timestamp for the reason line.  Defaults to UTC now.

    Raises
    ------
    ValueError
        When *action_id* is not found, *reason* is empty, or the user-notes
        block is missing from the note (indicates a corrupt/non-standard file).
    """
    if not reason or not reason.strip():
        raise ValueError("reason must be non-empty")

    vault_root = Path(vault_root)
    path = find_commitment_note(vault_root, action_id)
    if path is None:
        raise ValueError(f"commitment not found: {action_id!r}")

    content = path.read_text(encoding="utf-8")
    begin_idx = content.find(USER_NOTES_BEGIN)
    if begin_idx == -1:
        raise ValueError(
            f"user-notes block missing from note for {action_id!r}; "
            "the note may have been manually edited"
        )

    ts = now_iso or datetime.now(timezone.utc).isoformat()
    insert_after = begin_idx + len(USER_NOTES_BEGIN)
    reason_line = f"\n- {ts}: {reason.strip()}"
    new_content = content[:insert_after] + reason_line + content[insert_after:]

    atomic_write(
        path,
        new_content,
        vault_root=vault_root,
        metadata={"action_id": action_id},
        tool_name="obsidian-connector/commitment-ops",
        inject_generated_by=False,
    )

    fm = parse_frontmatter(content)
    return {
        "action_id": action_id,
        "reason_added": reason.strip(),
        "timestamp": ts,
        "path": path.relative_to(vault_root).as_posix(),
        "status": fm.get("status", "open"),
    }


# ---------------------------------------------------------------------------
# Service sync
# ---------------------------------------------------------------------------

def sync_commitments_from_service(
    vault_root: Path,
    service_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Fetch open actions from obsidian-capture-service and write them as notes.

    When the service is unavailable or not configured, returns an error dict
    without touching the vault.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    service_url:
        Base URL of the capture service.  Falls back to
        ``OBSIDIAN_CAPTURE_SERVICE_URL`` env var.
    api_key:
        Bearer token.  Falls back to ``OBSIDIAN_CAPTURE_SERVICE_TOKEN``.

    Returns
    -------
    dict
        ``{"ok": True, "synced": N, "errors": [...], "source_url": "..."}``
        on success, or ``{"ok": False, "error": "..."}`` on failure.
    """
    import http.client

    vault_root = Path(vault_root)
    url = service_url or os.getenv("OBSIDIAN_CAPTURE_SERVICE_URL")
    key = api_key or os.getenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN")

    if not url:
        return {
            "ok": False,
            "error": "service not configured (set OBSIDIAN_CAPTURE_SERVICE_URL)",
        }

    parsed = urllib.parse.urlparse(url.rstrip("/"))
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return {
            "ok": False,
            "error": f"service URL must use http or https, got: {parsed.scheme!r}",
        }

    base_path = (parsed.path or "").rstrip("/")
    get_path = base_path + "/actions?status=open&limit=200"
    actions_url = f"{parsed.scheme}://{parsed.netloc}{get_path}"
    req_headers: dict[str, str] = {"Accept": "application/json"}
    if key:
        req_headers["Authorization"] = f"Bearer {key}"

    conn: http.client.HTTPConnection | None = None
    sync_timeout = _service_timeout()
    try:
        if parsed.scheme == "https":
            import ssl
            conn = http.client.HTTPSConnection(  # nosemgrep
                parsed.netloc, timeout=sync_timeout, context=ssl.create_default_context()
            )
        else:
            conn = http.client.HTTPConnection(parsed.netloc, timeout=sync_timeout)
        conn.request("GET", get_path, headers=req_headers)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        payload = json.loads(body)
    except http.client.HTTPException as exc:
        return {"ok": False, "error": f"HTTP error: {exc}"}
    except OSError as exc:
        return {"ok": False, "error": f"service unreachable: {exc}"}
    except (json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "error": f"service response malformed: {exc}"}
    finally:
        if conn is not None:
            conn.close()

    actions_raw = (
        payload
        if isinstance(payload, list)
        else payload.get("actions", payload.get("data", []))
    )
    if not isinstance(actions_raw, list):
        return {"ok": False, "error": "unexpected response shape from service"}

    synced = 0
    errors: list[str] = []
    for raw in actions_raw:
        try:
            action = _dict_to_action_input(raw)
            write_commitment_note(vault_root, action)
            synced += 1
        except Exception as exc:
            errors.append(f"{raw.get('action_id', '?')}: {exc}")

    return {
        "ok": True,
        "synced": synced,
        "errors": errors,
        "source_url": actions_url,
    }


def _dict_to_action_input(raw: dict) -> ActionInput:
    """Map a service action payload dict to an :class:`ActionInput`.

    Tolerates the Task 27 rich-metadata keys (``urgency``,
    ``lifecycle_stage``, ``source_app``, ``source_entrypoint``,
    ``projects``, ``people``, ``areas``) when the service includes them;
    falls back to sensible defaults when the payload is from a pre-Task
    27 service build.
    """

    def _s(k: str) -> str | None:
        v = raw.get(k)
        return str(v) if v is not None else None

    def _list(k: str) -> list[str]:
        v = raw.get(k) or []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v]

    channels = raw.get("channels") or []
    if isinstance(channels, str):
        channels = [channels]

    return ActionInput(
        action_id=raw["action_id"],
        capture_id=raw.get("capture_id") or "",
        title=raw.get("title") or "Untitled",
        created_at=raw.get("created_at") or datetime.now(timezone.utc).isoformat(),
        project=_s("project"),
        status=raw.get("status") or "open",
        priority=raw.get("priority") or "normal",
        due_at=_s("due_at"),
        postponed_until=_s("postponed_until"),
        requires_ack=bool(raw.get("requires_ack", False)),
        escalation_policy=_s("escalation_policy"),
        channels=list(channels),
        source_note=_s("source_note"),
        description=_s("description"),
        completed_at=_s("completed_at"),
        # Task 27 rich metadata (all optional / defaulted).
        urgency=raw.get("urgency") or "normal",
        lifecycle_stage=raw.get("lifecycle_stage") or "inbox",
        source_app=_s("source_app"),
        source_entrypoint=_s("source_entrypoint"),
        projects=_list("projects"),
        people=_list("people"),
        areas=_list("areas"),
    )


# ---------------------------------------------------------------------------
# Service PATCH helper
# ---------------------------------------------------------------------------

def _try_service_patch(action_id: str, updates: dict) -> dict | None:
    """Fire a PATCH to the service if configured.

    Returns a result dict on success or failure, or ``None`` when the service
    is not configured.  Never raises.
    """
    import http.client
    import ssl

    url = os.getenv("OBSIDIAN_CAPTURE_SERVICE_URL")
    key = os.getenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN")
    if not url:
        return None

    parsed = urllib.parse.urlparse(url.rstrip("/"))
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return {"ok": False, "error": f"service URL must use http or https, got: {parsed.scheme!r}"}

    patch_path = (parsed.path or "").rstrip("/") + f"/actions/{action_id}"
    body_bytes = json.dumps(updates).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    conn: http.client.HTTPConnection | None = None
    try:
        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(  # nosemgrep
                parsed.netloc, timeout=5, context=ssl.create_default_context()
            )
        else:
            conn = http.client.HTTPConnection(parsed.netloc, timeout=5)
        conn.request("PATCH", patch_path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        return {"ok": True, "status_code": resp.status}
    except http.client.HTTPException as exc:
        return {"ok": False, "error": f"HTTP error: {exc}"}
    except OSError as exc:
        return {"ok": False, "error": f"unreachable: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Task 28: thin wrappers over the service retrieval endpoints
# ---------------------------------------------------------------------------


def _service_timeout(default: float = 10.0) -> float:
    """Resolve the HTTP client timeout (Task 35).

    ``SERVICE_REQUEST_TIMEOUT_SECONDS`` env overrides the per-call
    default. Values <= 0 or unparseable fall back to ``default`` so a
    typo never disables the ceiling silently. Kept as a tiny helper so
    every wrapper uses the same knob.
    """
    raw = os.environ.get("SERVICE_REQUEST_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value <= 0:
        return default
    return value


def _service_get_json(
    path_with_query: str,
    *,
    service_url: str | None = None,
    token: str | None = None,
    timeout: float | None = None,
) -> dict:
    """Issue a GET to the capture service and return the parsed JSON.

    Returns a result dict:

    - ``{"ok": True, "status_code": 200, "data": {...}}`` on 2xx.
    - ``{"ok": False, "error": "..."}`` on any failure (network, auth,
      malformed JSON, bad scheme, missing URL).

    ``path_with_query`` is a path + query-string pair starting at ``/``
    that is appended to the service base URL (minus trailing slash).
    No string interpolation of untrusted input into the path should
    happen here; callers encode query params via ``urllib.parse.urlencode``.
    """
    import http.client
    import ssl

    url = service_url or os.getenv("OBSIDIAN_CAPTURE_SERVICE_URL")
    key = token or os.getenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN")
    if timeout is None:
        timeout = _service_timeout()
    if not url:
        return {
            "ok": False,
            "error": "service not configured (set OBSIDIAN_CAPTURE_SERVICE_URL)",
        }

    parsed = urllib.parse.urlparse(url.rstrip("/"))
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return {
            "ok": False,
            "error": (
                f"service URL must use http or https, got: {parsed.scheme!r}"
            ),
        }

    base_path = (parsed.path or "").rstrip("/")
    full_path = base_path + path_with_query
    headers: dict[str, str] = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    conn: http.client.HTTPConnection | None = None
    try:
        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(  # nosemgrep
                parsed.netloc,
                timeout=timeout,
                context=ssl.create_default_context(),
            )
        else:
            conn = http.client.HTTPConnection(parsed.netloc, timeout=timeout)
        conn.request("GET", full_path, headers=headers)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status >= 400:
            return {
                "ok": False,
                "status_code": resp.status,
                "error": body or f"HTTP {resp.status}",
            }
        data = json.loads(body) if body else {}
    except http.client.HTTPException as exc:
        return {"ok": False, "error": f"HTTP error: {exc}"}
    except OSError as exc:
        return {"ok": False, "error": f"service unreachable: {exc}"}
    except (json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "error": f"service response malformed: {exc}"}
    finally:
        if conn is not None:
            conn.close()

    return {"ok": True, "status_code": 200, "data": data}


def list_service_actions(
    *,
    status: str | None = None,
    lifecycle_stage: str | None = None,
    project: str | None = None,
    person: str | None = None,
    area: str | None = None,
    urgency: str | None = None,
    priority: str | None = None,
    source_app: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/actions`` on the capture service.

    All filters are optional. ``project``/``person``/``area`` resolve
    on the service side through its alias table (case-insensitive).
    ``limit`` defaults to 50; the server enforces a cap of 200.
    ``cursor`` is the opaque value returned in a prior response under
    ``next_cursor``.

    Returns the wrapper envelope from :func:`_service_get_json`. On
    success the service response lives under ``data`` with the shape:

    ``{"ok": True, "items": [...], "next_cursor": "..." | null}``

    Never raises; always returns a dict.
    """
    params: list[tuple[str, str]] = []
    if status is not None:
        params.append(("status", status))
    if lifecycle_stage is not None:
        params.append(("lifecycle_stage", lifecycle_stage))
    if project is not None:
        params.append(("project", project))
    if person is not None:
        params.append(("person", person))
    if area is not None:
        params.append(("area", area))
    if urgency is not None:
        params.append(("urgency", urgency))
    if priority is not None:
        params.append(("priority", priority))
    if source_app is not None:
        params.append(("source_app", source_app))
    if due_before is not None:
        params.append(("due_before", due_before))
    if due_after is not None:
        params.append(("due_after", due_after))
    if limit is not None:
        params.append(("limit", str(int(limit))))
    if cursor is not None:
        params.append(("cursor", cursor))

    query = urllib.parse.urlencode(params)
    path = "/api/v1/actions" + (f"?{query}" if query else "")
    return _service_get_json(path, service_url=service_url, token=token)


def get_service_action(
    action_id: str,
    *,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/actions/{action_id}`` on the capture service.

    Returns the :func:`_service_get_json` envelope. A 404 from the
    service surfaces as ``{"ok": False, "status_code": 404, "error":
    "..."}``. Never raises.
    """
    if not action_id or not isinstance(action_id, str):
        return {"ok": False, "error": "action_id must be a non-empty string"}
    # Quote defensively — action IDs are ULID-style but we never trust
    # the caller not to pass something funky.
    quoted = urllib.parse.quote(action_id, safe="")
    path = f"/api/v1/actions/{quoted}"
    return _service_get_json(path, service_url=service_url, token=token)


def get_service_action_stats(
    *,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/actions/stats`` on the capture service.

    Returns the :func:`_service_get_json` envelope. On success the
    service payload contains ``total``, ``by_status``,
    ``by_lifecycle_stage``, ``by_priority``, ``by_source_app``. Never
    raises.
    """
    return _service_get_json(
        "/api/v1/actions/stats",
        service_url=service_url,
        token=token,
    )


# ---------------------------------------------------------------------------
# Task 21.B: cross-input dedup wrappers
# ---------------------------------------------------------------------------


def _service_post_json(
    path: str,
    *,
    body: dict | None = None,
    service_url: str | None = None,
    token: str | None = None,
    timeout: float | None = None,
) -> dict:
    """POST JSON to the capture service and return the parsed response.

    Return shape matches :func:`_service_get_json`:

    - ``{"ok": True, "status_code": 2xx, "data": {...}}`` on success.
    - ``{"ok": False, "status_code": n?, "error": "..."}`` on any
      failure (network, auth, malformed JSON, bad scheme, missing URL).

    Never raises.
    """
    import http.client
    import ssl

    url = service_url or os.getenv("OBSIDIAN_CAPTURE_SERVICE_URL")
    key = token or os.getenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN")
    if timeout is None:
        timeout = _service_timeout()
    if not url:
        return {
            "ok": False,
            "error": "service not configured (set OBSIDIAN_CAPTURE_SERVICE_URL)",
        }

    parsed = urllib.parse.urlparse(url.rstrip("/"))
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return {
            "ok": False,
            "error": (
                f"service URL must use http or https, got: {parsed.scheme!r}"
            ),
        }

    base_path = (parsed.path or "").rstrip("/")
    full_path = base_path + path
    body_bytes = json.dumps(body or {}).encode("utf-8")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"

    conn: http.client.HTTPConnection | None = None
    try:
        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(  # nosemgrep
                parsed.netloc,
                timeout=timeout,
                context=ssl.create_default_context(),
            )
        else:
            conn = http.client.HTTPConnection(parsed.netloc, timeout=timeout)
        conn.request("POST", full_path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        if resp.status >= 400:
            return {
                "ok": False,
                "status_code": resp.status,
                "error": raw or f"HTTP {resp.status}",
            }
        data = json.loads(raw) if raw else {}
    except http.client.HTTPException as exc:
        return {"ok": False, "error": f"HTTP error: {exc}"}
    except OSError as exc:
        return {"ok": False, "error": f"service unreachable: {exc}"}
    except (json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "error": f"service response malformed: {exc}"}
    finally:
        if conn is not None:
            conn.close()

    return {"ok": True, "status_code": resp.status, "data": data}


def list_duplicate_candidates(
    action_id: str,
    *,
    limit: int = 10,
    within_days: int = 30,
    min_score: float | None = None,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/actions/{action_id}/duplicate-candidates``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload has ``{ok, action_id, candidates: [...], thresholds:
    {candidate, strong}}``.  404 is surfaced as ``{ok: False,
    status_code: 404, error: "..."}``.

    ``min_score`` defaults to the server-side candidate threshold
    (``0.55``) when omitted — passing an explicit value overrides the
    env-configured default.
    """
    if not action_id or not isinstance(action_id, str):
        return {"ok": False, "error": "action_id must be a non-empty string"}

    params: list[tuple[str, str]] = [
        ("limit", str(int(limit))),
        ("within_days", str(int(within_days))),
    ]
    if min_score is not None:
        params.append(("min_score", str(float(min_score))))

    quoted = urllib.parse.quote(action_id, safe="")
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/actions/{quoted}/duplicate-candidates"
    if query:
        path = f"{path}?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


def merge_commitments(
    loser_id: str,
    winner_id: str,
    *,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``POST /api/v1/actions/{loser_id}/merge`` with ``{winner_id}``.

    Returns the :func:`_service_post_json` envelope. Server responses:

    - 200 + ``{ok, loser_id, winner_id, edge_id, already_merged}`` on
      success (idempotent on re-merge).
    - 400 for self-merge or blank ``winner_id``.
    - 404 when either action is missing.
    - 409 when the loser or winner is in a terminal status.

    All of those return a dict with ``ok: False`` and ``status_code``
    populated so the caller can disambiguate.
    """
    if not loser_id or not isinstance(loser_id, str):
        return {"ok": False, "error": "loser_id must be a non-empty string"}
    if not winner_id or not isinstance(winner_id, str):
        return {"ok": False, "error": "winner_id must be a non-empty string"}

    quoted = urllib.parse.quote(loser_id, safe="")
    path = f"/api/v1/actions/{quoted}/merge"
    return _service_post_json(
        path,
        body={"winner_id": winner_id},
        service_url=service_url,
        token=token,
    )


# ---------------------------------------------------------------------------
# Task 31: pattern intelligence wrappers
# ---------------------------------------------------------------------------


def list_repeated_postponements(
    *,
    since_days: int = 30,
    limit: int = 50,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/patterns/repeated-postponements``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{ok, since_days, items: [...]}`` where each item
    carries ``action_id``, ``title``, ``count``, ``first_postponed_at``,
    ``last_postponed_at``, ``cumulative_days_slipped``, ``last_reason``.
    Never raises.
    """
    params: list[tuple[str, str]] = [
        ("since_days", str(int(since_days))),
        ("limit", str(int(limit))),
    ]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/patterns/repeated-postponements?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


def list_blocker_clusters(
    *,
    since_days: int = 60,
    limit: int = 50,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/patterns/blocker-clusters``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{ok, since_days, items: [...]}`` where each item
    carries ``blocker_action_id``, ``title``, ``blocks_count``,
    ``downstream_action_ids`` (sorted list of action IDs),
    ``oldest_edge_at``. Never raises.
    """
    params: list[tuple[str, str]] = [
        ("since_days", str(int(since_days))),
        ("limit", str(int(limit))),
    ]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/patterns/blocker-clusters?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


def explain_commitment(
    action_id: str,
    *,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/actions/{action_id}/why-still-open`` (Task 32).

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{ok, action_id, status, lifecycle_stage, urgency,
    reasons: [{code, label, data}, ...], inputs: {...}}``. 404 surfaces
    as ``{ok: False, status_code: 404}``; 409 (terminal action) as
    ``{ok: False, status_code: 409}``. Never raises.
    """
    if not action_id or not isinstance(action_id, str):
        return {"ok": False, "error": "action_id must be a non-empty string"}
    quoted = urllib.parse.quote(action_id, safe="")
    path = f"/api/v1/actions/{quoted}/why-still-open"
    return _service_get_json(path, service_url=service_url, token=token)


def list_recurring_unfinished(
    *,
    by: str = "project",
    since_days: int = 90,
    limit: int = 50,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/patterns/recurring-unfinished?by=...``.

    ``by`` must be one of ``{"project", "person", "area"}``. Returns
    the :func:`_service_get_json` envelope. On success the payload is
    ``{ok, by, since_days, items: [...]}`` where each item carries
    ``entity_id``, ``canonical_name``, ``slug``, ``kind``,
    ``open_count``, ``median_age_days``, ``action_ids``. Never raises.
    """
    if by not in {"project", "person", "area"}:
        return {
            "ok": False,
            "error": "by must be one of {'project', 'person', 'area'}",
        }
    params: list[tuple[str, str]] = [
        ("by", by),
        ("since_days", str(int(since_days))),
        ("limit", str(int(limit))),
    ]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/patterns/recurring-unfinished?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


# ---------------------------------------------------------------------------
# Task 38: delegation wrappers
# ---------------------------------------------------------------------------


def delegate_commitment(
    action_id: str,
    *,
    to_person: str,
    note: str | None = None,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``POST /api/v1/actions/{action_id}/delegate`` (Task 38).

    Returns the :func:`_service_post_json` envelope. On success
    ``data`` is the standard ``ActionLifecycleResponse`` shape extended
    with ``delegated_to``, ``delegated_to_entity_id``, ``delegated_at``,
    ``delegation_note``. The service creates a person entity on miss
    when ``to_person`` does not resolve via alias lookup. 404 / 409 /
    422 surface via ``status_code``. Never raises.
    """
    if not action_id or not isinstance(action_id, str):
        return {"ok": False, "error": "action_id must be a non-empty string"}
    if not to_person or not isinstance(to_person, str) or not to_person.strip():
        return {"ok": False, "error": "to_person must be a non-empty string"}

    body: dict[str, str | None] = {"to_person": to_person.strip()}
    if note is not None:
        body["note"] = note

    quoted = urllib.parse.quote(action_id, safe="")
    path = f"/api/v1/actions/{quoted}/delegate"
    return _service_post_json(
        path, body=body, service_url=service_url, token=token,
    )


def reclaim_commitment(
    action_id: str,
    *,
    note: str | None = None,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``POST /api/v1/actions/{action_id}/reclaim`` (Task 38).

    Clears the action's delegation columns and (when applicable) flips
    ``lifecycle_stage`` from ``waiting`` back to ``active``. Idempotent
    on a non-delegated row. Returns the :func:`_service_post_json`
    envelope; on success ``data`` is the lifecycle response with
    ``delegated_to == None``.
    """
    if not action_id or not isinstance(action_id, str):
        return {"ok": False, "error": "action_id must be a non-empty string"}

    body: dict[str, str | None] = {}
    if note is not None:
        body["note"] = note

    quoted = urllib.parse.quote(action_id, safe="")
    path = f"/api/v1/actions/{quoted}/reclaim"
    return _service_post_json(
        path, body=body, service_url=service_url, token=token,
    )


def list_delegated_to(
    person: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
    include_terminal: bool = False,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/actions/delegated-to/{person}`` (Task 38).

    ``person`` is the canonical name or any alias of the delegate.
    Returns the :func:`_service_get_json` envelope. On success
    ``data`` is ``{ok, items: [...], next_cursor: "..." | null}``.
    Unknown person yields an empty list.
    """
    if not person or not isinstance(person, str) or not person.strip():
        return {"ok": False, "error": "person must be a non-empty string"}

    params: list[tuple[str, str]] = [("limit", str(int(limit)))]
    if cursor is not None:
        params.append(("cursor", cursor))
    if include_terminal:
        params.append(("include_terminal", "true"))

    quoted = urllib.parse.quote(person.strip(), safe="")
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/actions/delegated-to/{quoted}"
    if query:
        path = f"{path}?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


def list_stale_delegations(
    *,
    threshold_days: int = 14,
    limit: int = 50,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/patterns/stale-delegations`` (Task 38).

    Returns the :func:`_service_get_json` envelope. On success ``data``
    is ``{ok, threshold_days, items: [...]}`` where each item is a
    per-person bucket with ``entity_id``, ``canonical_name``, ``count``,
    ``oldest_delegated_at``, ``newest_delegated_at``, and up to 10
    ``items: [{action_id, title, delegated_at, delegation_note}, ...]``.
    Never raises.
    """
    params: list[tuple[str, str]] = [
        ("threshold_days", str(int(threshold_days))),
        ("limit", str(int(limit))),
    ]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/patterns/stale-delegations?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


__all__ = [
    "CommitmentSummary",
    "list_commitments",
    "get_commitment",
    "list_due_soon",
    "mark_commitment_done",
    "postpone_commitment",
    "add_commitment_reason",
    "sync_commitments_from_service",
    "list_service_actions",
    "get_service_action",
    "get_service_action_stats",
    "list_duplicate_candidates",
    "merge_commitments",
    "list_repeated_postponements",
    "list_blocker_clusters",
    "list_recurring_unfinished",
    "explain_commitment",
    "delegate_commitment",
    "reclaim_commitment",
    "list_delegated_to",
    "list_stale_delegations",
]
