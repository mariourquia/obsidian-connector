"""Entity note renderer and writer (Task 15.A).

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

Out of scope for 15.A (tracked separately):

- Related-block regeneration on commitment notes.
- LLM-generated wiki body (15.C).
- Embedding-backed similarity list (15.B).
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

    # 15.C: Wiki fence — LLM-generated summary. When entity.wiki_content is set,
    # it replaces the fence content. Otherwise the existing fence content is
    # preserved across re-renders. New notes get an empty placeholder.
    effective_wiki = (
        entity.wiki_content.strip()
        if entity.wiki_content is not None
        else existing_wiki
    )
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
    "resolve_entity_path",
    "write_entity_note",
]
