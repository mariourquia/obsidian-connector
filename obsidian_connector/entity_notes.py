"""Entity note renderer and writer (Task 15.A / 30).

Represents semantic-memory entities emitted by
``obsidian-capture-service`` as vault-native notes. Each entity is stored
at a deterministic path under ``Entities/<Kind>/<slug>.md`` so the service
remains the system of record while the vault becomes a navigable
wiki-style surface.

Scope (Phase 15.A):

- Idempotent write keyed on ``entity_id``.
- Minimal frontmatter (``type: entity``, kind, canonical name, aliases).
- Simple body with aliases list and a wiki-linked list of actions.
- Preserves any user-authored content in a fenced ``user-notes`` block
  across re-renders, mirroring the pattern used by
  :mod:`obsidian_connector.commitment_notes`.

Task 30 adds a deterministic first-pass wiki body rendered *inside* the
``service:entity-wiki:begin/end`` fence when the caller does not supply
``EntityInput.wiki_content``. It projects peer entities (projects /
people / areas / topics / tools) computed upstream from
``action_entities`` joins into kind-specific Markdown subsections.

The fence contract is preserved: when Task 15.C later supplies an
LLM-generated overview via ``wiki_content``, the scaffold steps aside
and the LLM output wins. The connector never parses the body; the
fence is the only boundary it respects.

Out of scope (tracked separately):

- Related-block regeneration on commitment notes (Task 15.A.2).
- LLM-generated wiki body (Task 15.C) — wraps the scaffold via
  ``wiki_content``.
- Embedding-backed similarity list (Task 15.B).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obsidian_connector.write_manager import atomic_write


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTITY_USER_NOTES_BEGIN = "<!-- service:entity-user-notes:begin -->"
ENTITY_USER_NOTES_END = "<!-- service:entity-user-notes:end -->"
ENTITY_WIKI_BEGIN = "<!-- service:entity-wiki:begin -->"
ENTITY_WIKI_END = "<!-- service:entity-wiki:end -->"

NOTE_TYPE = "entity"
ENTITIES_ROOT = "Entities"

# Kind -> subdirectory name (pluralised for vault ergonomics).
_KIND_DIRS: dict[str, str] = {
    "person": "People",
    "project": "Projects",
    "topic": "Topics",
    "tool": "Tools",
    "org": "Orgs",
    "place": "Places",
    "area": "Areas",
}

_VALID_KINDS = frozenset(_KIND_DIRS.keys())

_TOOL_NAME = "obsidian-connector/entity-notes"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LinkedAction:
    """Minimal action projection for an entity page."""

    action_id: str
    title: str
    status: str
    commitment_path: str | None = None  # vault-relative path to commitment note


@dataclass(frozen=True)
class EntityInput:
    """Structured entity input from ``obsidian-capture-service``."""

    entity_id: str
    kind: str
    canonical_name: str
    slug: str
    aliases: list[str] = field(default_factory=list)
    description: str | None = None
    open_actions: list[LinkedAction] = field(default_factory=list)
    done_actions: list[LinkedAction] = field(default_factory=list)
    # 15.C: LLM-generated wiki body. When set, written inside the wiki fence.
    # Preserved across re-renders when not supplied (wiki_content=None).
    wiki_content: str | None = None
    # Task 30: deterministic projection payload supplied by the service
    # so ``render_first_pass_wiki_body`` can render peer subsections
    # (projects / people / areas / topics / tools) without a round-trip.
    # Shape: ``{kind: [{entity_id, canonical_name, kind, slug?,
    # co_occurrence_count?}, ...]}``. Every kind the service knows
    # about should be present; missing kinds degrade gracefully.
    related_entities_by_kind: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict
    )
    # Task 30: timestamps surfaced in the "At a glance" header. Both
    # are optional — when absent the header drops those columns.
    first_seen_at: str | None = None
    last_activity_at: str | None = None


@dataclass(frozen=True)
class EntityWriteResult:
    path: Path
    created: bool


# ---------------------------------------------------------------------------
# Slug / path helpers
# ---------------------------------------------------------------------------

_FALLBACK_DIR = "Other"


def _validate_kind(kind: str) -> str:
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"invalid entity kind: {kind!r}; expected one of {sorted(_VALID_KINDS)}"
        )
    return _KIND_DIRS[kind]


_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


def _validate_slug(slug: str) -> str:
    """Defence-in-depth for path construction.

    The service-side ``slugify`` already returns a safe string, but the
    connector guards against path traversal regardless.
    """
    if not slug or not _SAFE_SLUG.match(slug):
        raise ValueError(f"unsafe entity slug: {slug!r}")
    return slug


def resolve_entity_path(vault_root: Path, entity: EntityInput) -> Path:
    """Compute the canonical vault path for *entity*.

    Shape: ``Entities/<Kind>/<slug>.md``.
    """
    subdir = _validate_kind(entity.kind)
    slug = _validate_slug(entity.slug)
    return vault_root / ENTITIES_ROOT / subdir / f"{slug}.md"


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

_YAML_NEEDS_QUOTE = re.compile(r'[:\[\]{}&*!|>\'"%@`#,?-]|^\s|\s$')


def _yaml_scalar(value: Any) -> str:
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


def _yaml_string_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(_yaml_scalar(v) for v in values) + "]"


def _render_frontmatter(entity: EntityInput, sync_at: str) -> str:
    lines = [
        "---",
        f"type: {NOTE_TYPE}",
        f"entity_id: {_yaml_scalar(entity.entity_id)}",
        f"kind: {_yaml_scalar(entity.kind)}",
        f"canonical_name: {_yaml_scalar(entity.canonical_name)}",
        f"slug: {_yaml_scalar(entity.slug)}",
        f"description: {_yaml_scalar(entity.description)}",
        f"aliases: {_yaml_string_list(entity.aliases)}",
        f"service_last_synced_at: {_yaml_scalar(sync_at)}",
        "---",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------


def _commitment_wikilink(action: LinkedAction) -> str:
    if action.commitment_path:
        path = action.commitment_path
        if path.endswith(".md"):
            path = path[:-3]
        return f"- [[{path}|{action.title}]]"
    return f"- {action.title}"


# ---------------------------------------------------------------------------
# Task 30: deterministic first-pass wiki body
# ---------------------------------------------------------------------------

_EMPTY_PLACEHOLDER = "_No linked data yet._"

# Which peer-entity kinds surface in which entity-kind wiki body. Order
# is deliberate: more specific first. Kept as tuples for determinism.
_SUBSECTIONS_BY_KIND: dict[str, tuple[tuple[str, str], ...]] = {
    "person": (
        ("Projects this person appears in", "project"),
        ("Areas", "area"),
    ),
    "project": (
        ("People involved", "person"),
        ("Areas", "area"),
    ),
    "area": (
        ("Projects in this area", "project"),
        ("People", "person"),
    ),
    "topic": (
        ("Related projects", "project"),
        ("People", "person"),
    ),
    "tool": (
        ("Related projects", "project"),
        ("People", "person"),
    ),
    "org": (
        ("Related projects", "project"),
        ("People", "person"),
    ),
    "place": (
        ("Related projects", "project"),
        ("People", "person"),
    ),
}


def _kind_display(kind: str) -> str:
    return kind[:1].upper() + kind[1:]


def _date_only(iso: str | None) -> str | None:
    """Return the ``YYYY-MM-DD`` prefix of an ISO timestamp, or None.

    Tolerant of trailing ``Z`` / timezone suffixes; never raises. Used
    in the "At a glance" header so cross-run determinism does not depend
    on preserving subsecond precision.
    """
    if not iso:
        return None
    # Fast path: the DB stores ``YYYY-MM-DDTHH:MM:SS...`` — slice the
    # date prefix without parsing.
    if len(iso) >= 10 and iso[4] == "-" and iso[7] == "-":
        return iso[:10]
    return None


def _entity_kind_dir(kind: str) -> str:
    return _KIND_DIRS.get(kind, _FALLBACK_DIR)


def _entity_wikilink(entity: dict[str, Any]) -> str:
    """Render a single peer entity as a ``[[Entities/<Kind>/<slug>|name]]``
    wikilink bullet with its co-occurrence count.

    Falls back to a plain name bullet when no slug is present (defence
    against partial projections from older service versions).
    """
    name = entity.get("canonical_name") or ""
    slug = entity.get("slug")
    kind = entity.get("kind") or ""
    count = entity.get("co_occurrence_count")

    count_suffix = ""
    if isinstance(count, int) and count > 0:
        count_suffix = f" ({count})"

    if slug and kind:
        subdir = _entity_kind_dir(kind)
        target = f"{ENTITIES_ROOT}/{subdir}/{slug}"
        return f"- [[{target}|{name}]]{count_suffix}"
    return f"- {name}{count_suffix}"


def _render_peer_section(
    heading: str,
    peers: list[dict[str, Any]],
) -> str:
    if not peers:
        return f"### {heading}\n{_EMPTY_PLACEHOLDER}"
    # Sort: (co_occurrence_count DESC, canonical_name ASC). The service
    # already sorts this way, but we re-sort here so any caller with a
    # partial / unsorted projection gets stable output.
    sorted_peers = sorted(
        peers,
        key=lambda p: (
            -int(p.get("co_occurrence_count") or 0),
            (p.get("canonical_name") or "").lower(),
        ),
    )
    bullets = "\n".join(_entity_wikilink(p) for p in sorted_peers)
    return f"### {heading}\n{bullets}"


def _render_commitments_section(
    heading: str, actions: list[LinkedAction]
) -> str:
    if not actions:
        return f"### {heading}\n{_EMPTY_PLACEHOLDER}"
    bullets = "\n".join(_commitment_wikilink(a) for a in actions)
    return f"### {heading}\n{bullets}"


def _render_at_a_glance(entity: EntityInput) -> str:
    parts: list[str] = [f"kind: {entity.kind}"]
    parts.append(f"{len(entity.open_actions)} open")
    parts.append(f"{len(entity.done_actions)} done")
    first = _date_only(entity.first_seen_at)
    if first:
        parts.append(f"first seen {first}")
    last = _date_only(entity.last_activity_at)
    if last:
        parts.append(f"last active {last}")
    separator = " \u00b7 "
    return f"**At a glance:** {separator.join(parts)}"


def _has_first_pass_inputs(entity: EntityInput) -> bool:
    """Return True when *entity* carries enough data for a first-pass body.

    The scaffold is always safe to render — it degrades to
    ``_No linked data yet._`` placeholders for empty sections — but we
    only *substitute* it for the legacy fence contents when the caller
    has actually supplied Task 30 data. This keeps pre-Task-30 service
    versions (which don't populate the new fields) writing the same
    empty fence they always did.
    """
    if entity.related_entities_by_kind:
        # A non-empty projection dict is the unambiguous signal.
        return True
    if entity.first_seen_at or entity.last_activity_at:
        return True
    # Actions alone indicate a Task 15.A capable service; treat that as
    # enough to render the scaffold. The existing fence (if any) is
    # replaced by a body whose sections accurately reflect the action
    # state; wiping stale 15.A content this way is desired.
    return bool(entity.open_actions or entity.done_actions)


def render_first_pass_wiki_body(
    entity: EntityInput,
    related_entities_by_kind: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """Return a deterministic Markdown body for the entity wiki fence.

    Task 30 — this is the first-pass projection of an entity's neighborhood
    used inside the ``service:entity-wiki:begin/end`` fence before Task
    15.C supplies an LLM-generated overview.

    The body is derived purely from relational inputs (kind, counts,
    aliases, linked actions, and peer entities bucketed by kind). Given
    the same ``EntityInput`` plus the same ``related_entities_by_kind``
    map, this function produces byte-identical output.

    Section layout:

    - "At a glance" summary line (kind, open/done counts, first-seen,
      last-activity).
    - Zero or more peer subsections chosen by ``entity.kind`` (e.g.
      a ``person`` page gets "Projects this person appears in" and
      "Areas"; a ``project`` page gets "People involved" and "Areas").
      Empty peer lists render ``_No linked data yet._``.
    - An activity subsection listing open / done commitments linked to
      the entity with stable wikilinks.

    Parameters
    ----------
    entity:
        The entity being rendered. Must carry aliases / actions /
        timestamps.
    related_entities_by_kind:
        Optional override of ``entity.related_entities_by_kind``. When
        ``None`` the field on ``entity`` is used. Passing an explicit
        map is useful in tests where the caller constructs the
        projection separately.
    """
    related = (
        related_entities_by_kind
        if related_entities_by_kind is not None
        else dict(entity.related_entities_by_kind or {})
    )

    sections: list[str] = [_render_at_a_glance(entity)]

    # Kind-specific peer subsections. If entity.kind is unknown (e.g. a
    # future kind) we fall back to a generic projects + people view.
    layout = _SUBSECTIONS_BY_KIND.get(
        entity.kind,
        (("Related projects", "project"), ("People", "person")),
    )
    for heading, peer_kind in layout:
        peers = list(related.get(peer_kind, []))
        sections.append(_render_peer_section(heading, peers))

    # Activity subsections: kind-conditioned headings.
    open_heading, done_heading = _activity_headings(entity.kind)
    sections.append(_render_commitments_section(open_heading, entity.open_actions))
    sections.append(
        _render_commitments_section(done_heading, entity.done_actions)
    )

    return "\n\n".join(sections)


def _activity_headings(kind: str) -> tuple[str, str]:
    """Return ``(open, done)`` headings matched to the entity kind."""
    if kind == "person":
        return (
            "Recent commitments with this person",
            "Past commitments with this person",
        )
    if kind == "project":
        return ("Open commitments on this project", "Completed on this project")
    if kind == "area":
        return ("Open commitments in this area", "Completed in this area")
    if kind == "topic":
        return ("Mentions (open)", "Mentions (done)")
    # tool / org / place share a generic label.
    return ("Seen on commitments", "Seen on completed commitments")


def _render_body(entity: EntityInput, existing_user_notes: str, existing_wiki: str) -> str:
    sections: list[str] = [f"# {entity.canonical_name}"]

    if entity.description:
        sections.append(entity.description)

    if entity.aliases:
        alias_items = "\n".join(f"- {alias}" for alias in entity.aliases)
        sections.append("## Aliases\n" + alias_items)

    if entity.open_actions:
        items = "\n".join(_commitment_wikilink(a) for a in entity.open_actions)
        sections.append("## Open commitments\n" + items)
    else:
        sections.append("## Open commitments\n_No open commitments._")

    if entity.done_actions:
        items = "\n".join(_commitment_wikilink(a) for a in entity.done_actions)
        sections.append("## Completed commitments\n" + items)

    # Wiki fence policy:
    #
    # - ``wiki_content`` is explicitly supplied -> that exact content
    #   fills the fence. This is the Task 15.C handoff: an LLM body
    #   replaces the scaffold without touching this renderer.
    # - ``wiki_content`` is ``None`` AND ``EntityInput`` carries enough
    #   data to render the Task 30 first-pass body -> we render the
    #   deterministic scaffold from the projection.
    # - ``wiki_content`` is ``None`` AND the entity carries no projection
    #   -> preserve whatever existed before (legacy 15.A behavior, keeps
    #   early vaults compatible).
    if entity.wiki_content is not None:
        effective_wiki = entity.wiki_content.strip()
    elif _has_first_pass_inputs(entity):
        effective_wiki = render_first_pass_wiki_body(entity).strip()
    else:
        effective_wiki = existing_wiki
    sections.append(
        f"## Overview\n{ENTITY_WIKI_BEGIN}\n{effective_wiki}\n{ENTITY_WIKI_END}"
    )

    # Preserve user-authored free-form content across re-renders.
    user_block = existing_user_notes.strip()
    sections.append(
        f"{ENTITY_USER_NOTES_BEGIN}\n{user_block}\n{ENTITY_USER_NOTES_END}"
    )
    return "\n\n".join(sections)


def _extract_user_notes(content: str | None) -> str:
    if not content:
        return ""
    begin = content.find(ENTITY_USER_NOTES_BEGIN)
    if begin == -1:
        return ""
    begin += len(ENTITY_USER_NOTES_BEGIN)
    end = content.find(ENTITY_USER_NOTES_END, begin)
    if end == -1:
        return ""
    return content[begin:end].strip("\n")


def _extract_wiki(content: str | None) -> str:
    """Extract existing wiki fence content; returns empty string when absent."""
    if not content:
        return ""
    begin = content.find(ENTITY_WIKI_BEGIN)
    if begin == -1:
        return ""
    begin += len(ENTITY_WIKI_BEGIN)
    end = content.find(ENTITY_WIKI_END, begin)
    if end == -1:
        return ""
    return content[begin:end].strip("\n")


# ---------------------------------------------------------------------------
# Public writer
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_entity_note(
    vault_root: Path,
    entity: EntityInput,
    *,
    sync_at: str | None = None,
) -> EntityWriteResult:
    """Upsert the entity note for *entity* under *vault_root*.

    Idempotent: re-running with the same input rewrites the managed
    sections and preserves any content inside the ``user-notes`` fence.
    """
    path = resolve_entity_path(vault_root, entity)
    existing_content = path.read_text(encoding="utf-8") if path.exists() else None
    created = existing_content is None
    user_notes = _extract_user_notes(existing_content)
    existing_wiki = _extract_wiki(existing_content)

    frontmatter = _render_frontmatter(entity, sync_at or _now_iso())
    body = _render_body(entity, user_notes, existing_wiki)
    rendered = f"{frontmatter}\n\n{body}\n"

    atomic_write(
        path,
        rendered,
        vault_root=vault_root,
        metadata={
            "entity_id": entity.entity_id,
            "kind": entity.kind,
            "slug": entity.slug,
        },
        tool_name=_TOOL_NAME,
        inject_generated_by=False,
    )
    return EntityWriteResult(path=path, created=created)


__all__ = [
    "ENTITIES_ROOT",
    "ENTITY_USER_NOTES_BEGIN",
    "ENTITY_USER_NOTES_END",
    "ENTITY_WIKI_BEGIN",
    "ENTITY_WIKI_END",
    "EntityInput",
    "EntityWriteResult",
    "LinkedAction",
    "render_first_pass_wiki_body",
    "resolve_entity_path",
    "write_entity_note",
]
