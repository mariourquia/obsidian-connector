"""Commitment note renderer and writer.

Represents action objects emitted by ``obsidian-capture-service`` as
vault-native notes. Each action is stored at a deterministic path under
``Commitments/Open/`` or ``Commitments/Done/`` so the service remains the
system of record while the vault becomes a human-navigable surface.

This module is deliberately scoped to one responsibility: take a
structured :class:`ActionInput` and write (or update) a single commitment
note idempotently. It does not:

- expose any MCP tools
- build dashboards
- subscribe to events
- talk to SQLite or HTTP

Those concerns belong to later tasks. This module is their foundation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obsidian_connector.write_manager import atomic_write

# ---------------------------------------------------------------------------
# Public constants: fence markers used to delimit service-managed regions
# inside the note body. These are plain HTML comments so they stay out of
# rendered preview but remain greppable and stable across edits.
# ---------------------------------------------------------------------------

FOLLOWUP_BEGIN = "<!-- service:follow-up-log:begin -->"
FOLLOWUP_END = "<!-- service:follow-up-log:end -->"
USER_NOTES_BEGIN = "<!-- service:user-notes:begin -->"
USER_NOTES_END = "<!-- service:user-notes:end -->"

NOTE_TYPE = "commitment"
COMMITMENTS_ROOT = "Commitments"
OPEN_DIR = "Open"
DONE_DIR = "Done"

_VALID_STATUSES = frozenset({"open", "done"})

_TOOL_NAME = "obsidian-connector/commitment-notes"


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ActionInput:
    """Structured action input from ``obsidian-capture-service``.

    Field names mirror the capture-service ``Action`` row model where
    possible, plus a handful of presentation-layer additions
    (``channels``, ``escalation_policy`` as a human-readable label,
    ``source_note``).
    """

    action_id: str
    capture_id: str
    title: str
    created_at: str
    project: str | None = None
    status: str = "open"
    priority: str = "normal"
    due_at: str | None = None
    postponed_until: str | None = None
    requires_ack: bool = False
    escalation_policy: str | None = None
    channels: list[str] = field(default_factory=list)
    source_note: str | None = None
    description: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class WriteResult:
    """Outcome of :func:`write_commitment_note`."""

    path: Path
    created: bool
    moved_from: Path | None = None


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert *text* to a vault-safe filename stem.

    Lowercase, collapse non-alphanumeric runs to single hyphens, strip
    trailing hyphens, and clamp to 60 characters. Empty input falls back
    to ``"untitled"``.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        slug = "untitled"
    return slug[:60]


def _action_suffix(action_id: str) -> str:
    """Return a short, stable suffix derived from the action id.

    Uses the last 7 characters so titles with identical slugs produce
    distinct filenames. Length 7 gives enough entropy for any realistic
    workload while keeping filenames readable.
    """
    tail = action_id[-7:] if len(action_id) >= 7 else action_id
    return tail.lower()


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _parse_iso_date(iso: str) -> tuple[str, str]:
    """Return ``(YYYY, MM)`` from an ISO 8601 timestamp.

    Falls back to the current UTC date if parsing fails. Accepts both
    ``...+00:00`` and ``...Z`` forms.
    """
    try:
        candidate = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(candidate)
    except (ValueError, AttributeError):
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y"), dt.strftime("%m")


def resolve_commitment_path(vault_root: Path, action: ActionInput) -> Path:
    """Compute the canonical vault path for *action*.

    Shape: ``Commitments/{Open|Done}/YYYY/MM/<slug>-<id7>.md``
    where ``YYYY/MM`` is derived from ``action.created_at`` (stable across
    status transitions so the file moves between Open/Done but never
    hops months).
    """
    status = action.status
    bucket = DONE_DIR if status == "done" else OPEN_DIR
    year, month = _parse_iso_date(action.created_at)
    stem = f"{_slugify(action.title)}-{_action_suffix(action.action_id)}.md"
    return vault_root / COMMITMENTS_ROOT / bucket / year / month / stem


# ---------------------------------------------------------------------------
# Frontmatter serialization
# ---------------------------------------------------------------------------

_YAML_NEEDS_QUOTE = re.compile(r'[:\[\]{}&*!|>\'"%@`#,?-]|^\s|\s$')


def _yaml_scalar(value: Any) -> str:
    """Serialize a scalar value for use inside a YAML frontmatter block.

    Handles ``None``, booleans, ints, and strings. Strings are quoted
    when they contain characters that would confuse a naive parser.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if _YAML_NEEDS_QUOTE.search(text) or text.lower() in {
        "null", "true", "false", "yes", "no", "on", "off",
    }:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _yaml_flow_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(_yaml_scalar(v) for v in values) + "]"


def _render_frontmatter(
    action: ActionInput,
    sync_at: str,
) -> str:
    """Produce the YAML frontmatter block (including fences)."""
    lines = [
        "---",
        f"type: {NOTE_TYPE}",
        f"action_id: {_yaml_scalar(action.action_id)}",
        f"capture_id: {_yaml_scalar(action.capture_id)}",
        f"title: {_yaml_scalar(action.title)}",
        f"project: {_yaml_scalar(action.project)}",
        f"status: {_yaml_scalar(action.status)}",
        f"priority: {_yaml_scalar(action.priority)}",
        f"due_at: {_yaml_scalar(action.due_at)}",
        f"postponed_until: {_yaml_scalar(action.postponed_until)}",
        f"requires_ack: {_yaml_scalar(action.requires_ack)}",
        f"escalation_policy: {_yaml_scalar(action.escalation_policy)}",
        f"channels: {_yaml_flow_list(action.channels)}",
        f"source_note: {_yaml_scalar(action.source_note)}",
        f"service_last_synced_at: {_yaml_scalar(sync_at)}",
        "---",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Frontmatter parsing (tolerant, no pyyaml dependency)
# ---------------------------------------------------------------------------

_FM_BLOCK = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def parse_frontmatter(content: str) -> dict[str, str]:
    """Extract frontmatter from *content* into a flat string dict.

    Values retain their raw unquoted form. This is intentionally
    lossy -- the module owns both the writer and the reader, and only
    needs round-trippable string comparison for follow-up-log diffs.
    """
    m = _FM_BLOCK.match(content)
    if not m:
        return {}
    out: dict[str, str] = {}
    for raw in m.group(1).splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        value = rest.strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        elif value.startswith("'") and value.endswith("'") and len(value) >= 2:
            value = value[1:-1]
        out[key] = value
    return out


# ---------------------------------------------------------------------------
# Body helpers
# ---------------------------------------------------------------------------

def _source_note_wikilink(source_note: str | None) -> str:
    if not source_note:
        return "_No source capture recorded._"
    # Obsidian wikilinks drop the .md extension
    target = source_note[:-3] if source_note.endswith(".md") else source_note
    return f"- [[{target}|Source capture]]"


def _extract_block(content: str, begin: str, end: str) -> str | None:
    """Return the inner body of a fenced block, or ``None`` if absent."""
    start = content.find(begin)
    if start == -1:
        return None
    start += len(begin)
    stop = content.find(end, start)
    if stop == -1:
        return None
    inner = content[start:stop]
    return inner.strip("\n")


def _existing_log_entries(content: str | None) -> list[str]:
    if not content:
        return []
    block = _extract_block(content, FOLLOWUP_BEGIN, FOLLOWUP_END)
    if block is None:
        return []
    entries: list[str] = []
    for raw in block.splitlines():
        line = raw.rstrip()
        if line.startswith("- "):
            entries.append(line)
    return entries


def _existing_user_notes(content: str | None) -> str | None:
    if not content:
        return None
    block = _extract_block(content, USER_NOTES_BEGIN, USER_NOTES_END)
    return block


def _existing_frontmatter_values(content: str | None) -> dict[str, str]:
    if not content:
        return {}
    return parse_frontmatter(content)


def _compute_new_log_entries(
    action: ActionInput,
    previous_fm: dict[str, str],
    now_iso: str,
) -> list[str]:
    """Diff *previous_fm* against *action* and return new log lines."""
    if not previous_fm:
        return [f"- {now_iso} -- note created (status={action.status})"]

    entries: list[str] = []
    prev_status = previous_fm.get("status")
    if prev_status is not None and prev_status != action.status:
        entries.append(
            f"- {now_iso} -- status change: {prev_status} -> {action.status}"
        )
    prev_priority = previous_fm.get("priority")
    if prev_priority is not None and prev_priority != action.priority:
        entries.append(
            f"- {now_iso} -- priority change: {prev_priority} -> {action.priority}"
        )
    prev_due = previous_fm.get("due_at")
    new_due = action.due_at if action.due_at is not None else "null"
    if prev_due is not None and prev_due != new_due:
        entries.append(
            f"- {now_iso} -- due_at change: {prev_due} -> {new_due}"
        )
    prev_postponed = previous_fm.get("postponed_until")
    new_postponed = action.postponed_until if action.postponed_until is not None else "null"
    if prev_postponed is not None and prev_postponed != new_postponed:
        entries.append(
            f"- {now_iso} -- postponed_until change: {prev_postponed} -> {new_postponed}"
        )
    return entries


def _render_body(
    action: ActionInput,
    log_entries: list[str],
    user_notes_block: str | None,
) -> str:
    title_line = f"# {action.title}"
    description = (action.description or "").strip()
    description_section = description if description else "_No description provided._"

    meta_lines = [
        "## Metadata",
        f"- Created: {action.created_at}",
        f"- Status: {action.status}",
        f"- Priority: {action.priority}",
        f"- Due: {action.due_at or 'null'}",
        f"- Postponed until: {action.postponed_until or 'null'}",
        f"- Requires acknowledgement: {'yes' if action.requires_ack else 'no'}",
        f"- Escalation policy: {action.escalation_policy or 'null'}",
        f"- Channels: {', '.join(action.channels) if action.channels else 'none'}",
    ]
    if action.status == "done" and action.completed_at:
        meta_lines.append(f"- Completed: {action.completed_at}")

    source_section = [
        "## Source Capture",
        _source_note_wikilink(action.source_note),
    ]

    followup_section = [
        "## Follow-up Log",
        FOLLOWUP_BEGIN,
        *log_entries,
        FOLLOWUP_END,
    ]

    user_notes_inner = (
        user_notes_block
        if user_notes_block is not None
        else "_User-editable area below. Content here is preserved across syncs._"
    )
    notes_section = [
        "## Notes",
        USER_NOTES_BEGIN,
        user_notes_inner,
        USER_NOTES_END,
    ]

    sections = [
        title_line,
        "",
        description_section,
        "",
        *meta_lines,
        "",
        *source_section,
        "",
        *followup_section,
        "",
        *notes_section,
        "",
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------

def render_commitment_note(
    action: ActionInput,
    existing_content: str | None = None,
    now_iso: str | None = None,
) -> str:
    """Render the full note text (frontmatter + body).

    When *existing_content* is supplied, the follow-up log entries and
    the user-notes block are preserved verbatim, and a diff of the
    structured fields is appended to the log only when something
    actually changed.
    """
    sync_at = now_iso or datetime.now(timezone.utc).isoformat()
    previous_fm = _existing_frontmatter_values(existing_content)
    previous_entries = _existing_log_entries(existing_content)
    new_entries = _compute_new_log_entries(action, previous_fm, sync_at)
    all_entries = previous_entries + new_entries
    user_notes_block = _existing_user_notes(existing_content)

    frontmatter = _render_frontmatter(action, sync_at)
    body = _render_body(action, all_entries, user_notes_block)
    return frontmatter + "\n\n" + body


# ---------------------------------------------------------------------------
# Lookup + writer
# ---------------------------------------------------------------------------

_ACTION_ID_LINE = re.compile(r"^action_id:\s*(.+?)\s*$", re.MULTILINE)


def find_commitment_note(vault_root: Path, action_id: str) -> Path | None:
    """Locate an existing commitment note by ``action_id``.

    Scans both ``Commitments/Open/`` and ``Commitments/Done/`` for a
    frontmatter field that matches. Returns ``None`` if no match is
    found. Linear in the number of commitment notes; acceptable for
    the scales this service targets (thousands, not millions).
    """
    root = vault_root / COMMITMENTS_ROOT
    if not root.exists():
        return None
    target = action_id.strip()
    if not target:
        return None
    for md_path in root.rglob("*.md"):
        try:
            head = md_path.read_text(encoding="utf-8", errors="ignore")[:4096]
        except OSError:
            continue
        m = _ACTION_ID_LINE.search(head)
        if not m:
            continue
        raw = m.group(1).strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        elif raw.startswith("'") and raw.endswith("'"):
            raw = raw[1:-1]
        if raw == target:
            return md_path
    return None


def _validate(action: ActionInput) -> None:
    if not action.action_id or not action.action_id.strip():
        raise ValueError("action_id must be a non-empty string")
    if action.status not in _VALID_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(_VALID_STATUSES)}, got {action.status!r}"
        )


def write_commitment_note(
    vault_root: Path,
    action: ActionInput,
    now_iso: str | None = None,
) -> WriteResult:
    """Persist *action* as a commitment note inside *vault_root*.

    Idempotent: repeated calls with the same ``action_id`` update the
    same file. If the action's status moved between ``open`` and
    ``done``, the file is relocated to the correct bucket and the
    follow-up log records the transition.
    """
    _validate(action)
    vault_root = Path(vault_root)

    target_path = resolve_commitment_path(vault_root, action)
    existing_path = find_commitment_note(vault_root, action.action_id)

    existing_content: str | None = None
    if existing_path and existing_path.is_file():
        try:
            existing_content = existing_path.read_text(encoding="utf-8")
        except OSError:
            existing_content = None

    rendered = render_commitment_note(
        action, existing_content=existing_content, now_iso=now_iso
    )

    moved_from: Path | None = None
    created = existing_path is None

    if existing_path is not None and existing_path != target_path:
        moved_from = existing_path

    atomic_write(
        target_path,
        rendered,
        vault_root=vault_root,
        metadata={
            "action_id": action.action_id,
            "capture_id": action.capture_id,
            "status": action.status,
        },
        tool_name=_TOOL_NAME,
        inject_generated_by=False,
    )

    if moved_from is not None and moved_from.exists() and moved_from != target_path:
        try:
            moved_from.unlink()
        except OSError:
            pass
        # Clean up now-empty parent directories up to Commitments/<bucket>
        _prune_empty_dirs(moved_from.parent, vault_root / COMMITMENTS_ROOT)

    return WriteResult(path=target_path, created=created, moved_from=moved_from)


def _prune_empty_dirs(start: Path, stop_at: Path) -> None:
    """Remove empty directories walking up from *start* but never past *stop_at*.

    Safe to call on paths outside *stop_at*; the guard returns early in
    that case. Silently swallows filesystem races.
    """
    try:
        stop_resolved = stop_at.resolve()
    except OSError:
        return
    current = start
    while True:
        try:
            current_resolved = current.resolve()
        except OSError:
            return
        if stop_resolved not in current_resolved.parents:
            return  # walked up past the Commitments tree
        if not current.exists() or not current.is_dir():
            return
        try:
            next(current.iterdir())
            return  # not empty
        except StopIteration:
            pass
        except OSError:
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


__all__ = [
    "ActionInput",
    "WriteResult",
    "FOLLOWUP_BEGIN",
    "FOLLOWUP_END",
    "USER_NOTES_BEGIN",
    "USER_NOTES_END",
    "NOTE_TYPE",
    "COMMITMENTS_ROOT",
    "OPEN_DIR",
    "DONE_DIR",
    "find_commitment_note",
    "parse_frontmatter",
    "render_commitment_note",
    "resolve_commitment_path",
    "write_commitment_note",
]
