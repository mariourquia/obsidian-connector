"""Graph-aware vault indexing for obsidian-connector.

Provides read-only extraction of links, tags, and frontmatter from vault
markdown files, plus a :class:`NoteIndex` with backlinks, orphan detection,
neighbourhood traversal, and shortest-path queries.

This module never writes to vault files.
"""

from __future__ import annotations

import os
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Frontmatter parser (no PyYAML dependency)
# ---------------------------------------------------------------------------

_FRONTMATTER_FENCE = re.compile(r"^---\s*$")
_YAML_KV = re.compile(r"^(\w[\w\s]*):\s*(.*)$")
_YAML_LIST_ITEM = re.compile(r"^\s*-\s+(.*)$")


def extract_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter between ``---`` fences at the start of a file.

    Uses a simple regex-based parser (no PyYAML dependency).  Supports
    scalar values, simple lists, and quoted strings.

    Parameters
    ----------
    content:
        Full markdown file content.

    Returns
    -------
    dict
        Parsed frontmatter key-value pairs, or ``{}`` if no frontmatter.
    """
    lines = content.split("\n")
    if not lines or not _FRONTMATTER_FENCE.match(lines[0]):
        return {}

    fm_lines: list[str] = []
    for line in lines[1:]:
        if _FRONTMATTER_FENCE.match(line):
            break
        fm_lines.append(line)
    else:
        # No closing fence found -- not valid frontmatter.
        return {}

    result: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in fm_lines:
        # Blank line -- reset list context.
        if not line.strip():
            if current_key and current_list is not None:
                result[current_key] = current_list
                current_list = None
                current_key = None
            continue

        list_match = _YAML_LIST_ITEM.match(line)
        if list_match and current_key is not None:
            if current_list is None:
                current_list = []
            current_list.append(_unquote(list_match.group(1).strip()))
            continue

        # Flush any pending list before processing a new key.
        if current_key and current_list is not None:
            result[current_key] = current_list
            current_list = None
            current_key = None

        kv_match = _YAML_KV.match(line)
        if kv_match:
            key = kv_match.group(1).strip()
            raw_value = kv_match.group(2).strip()
            current_key = key
            if raw_value == "":
                # Value may be a list on subsequent lines.
                current_list = []
            else:
                result[key] = _parse_scalar(raw_value)
                current_key = key
                current_list = None
        # Lines that don't match are ignored (e.g. comments).

    # Flush trailing list.
    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


def _unquote(value: str) -> str:
    """Strip surrounding quotes from a YAML value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def _parse_scalar(raw: str) -> Any:
    """Coerce a raw YAML scalar string into a Python type."""
    raw = _unquote(raw)
    lower = raw.lower()
    if lower in ("true", "yes"):
        return True
    if lower in ("false", "no"):
        return False
    if lower in ("null", "~", ""):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


# ---------------------------------------------------------------------------
# Code-block detection helpers
# ---------------------------------------------------------------------------

_FENCED_CODE_RE = re.compile(r"^(`{3,}|~{3,})")


def _mask_code_blocks(content: str) -> str:
    """Replace content inside fenced code blocks and inline code with spaces.

    This lets link/tag regexes run on the masked text without hitting
    false positives inside code.
    """
    lines = content.split("\n")
    result: list[str] = []
    in_fence = False
    fence_marker = ""

    for line in lines:
        if in_fence:
            if line.strip().startswith(fence_marker):
                in_fence = False
            result.append(" " * len(line))
            continue

        m = _FENCED_CODE_RE.match(line.strip())
        if m:
            in_fence = True
            fence_marker = m.group(1)
            result.append(" " * len(line))
            continue

        # Mask inline code spans: replace `...` content with spaces.
        masked = re.sub(r"`[^`]+`", lambda ma: " " * len(ma.group(0)), line)
        result.append(masked)

    return "\n".join(result)


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------

# Matches [[target]] and [[target|alias]].
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def extract_links(content: str) -> list[str]:
    """Parse ``[[wikilinks]]`` and ``[[wikilink|alias]]`` from markdown.

    Skips links inside fenced code blocks and inline code spans.

    Parameters
    ----------
    content:
        Full markdown file content.

    Returns
    -------
    list[str]
        Link targets (the part before ``|``), deduplicated, in order of
        first appearance.
    """
    masked = _mask_code_blocks(content)
    seen: set[str] = set()
    result: list[str] = []
    for m in _WIKILINK_RE.finditer(masked):
        target = m.group(1).strip()
        if target and target not in seen:
            seen.add(target)
            result.append(target)
    return result


# ---------------------------------------------------------------------------
# Tag extraction
# ---------------------------------------------------------------------------

# Matches #tag and #nested/tag.
# Must be preceded by whitespace or start-of-line.
# Must NOT be inside a URL or look like a CSS color (#fff, #a1b2c3).
_TAG_RE = re.compile(r"(?:^|(?<=\s))#([\w][\w/]*[\w]|[\w]+)(?=\s|$|[,;:!?\)\]\.])")
_CSS_COLOR_RE = re.compile(r"^[0-9a-fA-F]{3,8}$")


def extract_tags(content: str) -> list[str]:
    """Parse ``#tags`` and ``#nested/tags`` from markdown.

    Skips tags inside fenced code blocks, inline code, and YAML frontmatter.
    Ignores CSS color codes (e.g. ``#fff``, ``#a1b2c3``) and bare numbers.

    Parameters
    ----------
    content:
        Full markdown file content.

    Returns
    -------
    list[str]
        Tags including the ``#`` prefix, deduplicated, in order of first
        appearance.
    """
    # Strip frontmatter before masking code.
    body = _strip_frontmatter(content)
    masked = _mask_code_blocks(body)

    seen: set[str] = set()
    result: list[str] = []
    for m in _TAG_RE.finditer(masked):
        tag_body = m.group(1)
        # Skip CSS color codes and pure numeric strings.
        if _CSS_COLOR_RE.match(tag_body):
            continue
        if tag_body.isdigit():
            continue
        tag = f"#{tag_body}"
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter block from the start of content."""
    lines = content.split("\n")
    if not lines or not _FRONTMATTER_FENCE.match(lines[0]):
        return content
    for i, line in enumerate(lines[1:], start=1):
        if _FRONTMATTER_FENCE.match(line):
            return "\n".join(lines[i + 1 :])
    return content


# ---------------------------------------------------------------------------
# NoteEntry and NoteIndex
# ---------------------------------------------------------------------------

@dataclass
class NoteEntry:
    """Metadata for a single vault note."""

    path: str  # vault-relative path
    title: str  # filename without .md
    links: list[str]  # outgoing [[wikilinks]]
    tags: list[str]  # #tags
    frontmatter: dict[str, Any]  # YAML frontmatter
    mtime: float  # file modification time
    size: int  # file size in bytes


class NoteIndex:
    """In-memory graph index of vault notes.

    Provides forward links, backlinks, tag index, orphan/dead-end
    detection, neighbourhood traversal, and shortest-path queries.
    """

    def __init__(self) -> None:
        self.notes: dict[str, NoteEntry] = {}
        self.backlinks: dict[str, set[str]] = {}
        self.forward_links: dict[str, set[str]] = {}
        self.tags: dict[str, set[str]] = {}
        self.orphans: set[str] = set()
        self.dead_ends: set[str] = set()
        self.unresolved: dict[str, set[str]] = {}

    # -- Query methods -------------------------------------------------------

    def neighborhood(self, path: str, depth: int = 1) -> set[str]:
        """Return all notes reachable within *depth* link hops from *path*.

        Parameters
        ----------
        path:
            Vault-relative path of the starting note.
        depth:
            Maximum traversal depth (default 1).

        Returns
        -------
        set[str]
            Vault-relative paths of neighbouring notes (excludes *path*
            itself).
        """
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(path, 0)])

        while queue:
            current, d = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            if d >= depth:
                continue
            # Follow both forward links and backlinks.
            neighbours = self.forward_links.get(current, set()) | self.backlinks.get(
                current, set()
            )
            for nb in neighbours:
                if nb not in visited and nb in self.notes:
                    queue.append((nb, d + 1))

        visited.discard(path)
        return visited

    def shortest_path(self, source: str, target: str) -> list[str] | None:
        """BFS shortest path from *source* to *target* through forward links.

        Parameters
        ----------
        source:
            Vault-relative path of the source note.
        target:
            Vault-relative path of the target note.

        Returns
        -------
        list[str] | None
            Ordered list of paths from source to target (inclusive), or
            ``None`` if no path exists.
        """
        if source == target:
            return [source]
        if source not in self.notes or target not in self.notes:
            return None

        visited: set[str] = {source}
        queue: deque[list[str]] = deque([[source]])

        while queue:
            path_so_far = queue.popleft()
            current = path_so_far[-1]
            for nb in self.forward_links.get(current, set()):
                if nb == target:
                    return path_so_far + [nb]
                if nb not in visited and nb in self.notes:
                    visited.add(nb)
                    queue.append(path_so_far + [nb])

        return None

    def notes_by_tag(self, tag: str) -> set[str]:
        """Return paths of notes with the given tag.

        Parameters
        ----------
        tag:
            Tag string (with or without ``#`` prefix).

        Returns
        -------
        set[str]
            Vault-relative paths.
        """
        if not tag.startswith("#"):
            tag = f"#{tag}"
        return set(self.tags.get(tag, set()))

    def notes_by_property(self, key: str, value: str | None = None) -> set[str]:
        """Return paths of notes whose frontmatter contains *key*.

        If *value* is given, only notes where ``frontmatter[key] == value``
        (string comparison) are returned.

        Parameters
        ----------
        key:
            Frontmatter property name.
        value:
            Optional value to match (compared as strings).

        Returns
        -------
        set[str]
            Vault-relative paths.
        """
        result: set[str] = set()
        for path, entry in self.notes.items():
            if key in entry.frontmatter:
                if value is None:
                    result.add(path)
                elif str(entry.frontmatter[key]) == str(value):
                    result.add(path)
        return result


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

_SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules"}


def _resolve_link_target(
    link: str, title_to_path: dict[str, str]
) -> str | None:
    """Resolve a wikilink target string to a vault-relative path.

    Tries case-insensitive filename matching.  Returns ``None`` if
    the link cannot be resolved.
    """
    # Normalize: strip .md if the link includes it.
    normalized = link
    if normalized.lower().endswith(".md"):
        normalized = normalized[:-3]

    # If the link contains a path separator, try exact match first.
    if "/" in normalized:
        candidate = normalized + ".md"
        if candidate in title_to_path.values():
            return candidate
        # Try case-insensitive on the full path.
        lower = candidate.lower()
        for path in title_to_path.values():
            if path.lower() == lower:
                return path

    # Match by title (filename without extension).
    lower_target = normalized.lower()
    result = title_to_path.get(lower_target)
    if result is not None:
        return result

    return None


def build_note_index(vault_path: str | None = None) -> NoteIndex:
    """Build a :class:`NoteIndex` by scanning all ``.md`` files in a vault.

    Parameters
    ----------
    vault_path:
        Absolute path to the vault directory.  If ``None``, uses
        :func:`~obsidian_connector.config.resolve_vault_path` to find it.

    Returns
    -------
    NoteIndex
        Fully populated index.
    """
    from obsidian_connector.config import resolve_vault_path

    if vault_path is not None:
        root = Path(vault_path)
    else:
        root = resolve_vault_path()

    # -- Phase 1: scan files and extract per-note metadata -------------------
    entries: dict[str, NoteEntry] = {}
    # title (lowercase) -> vault-relative path, for link resolution.
    title_to_path: dict[str, str] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories (modifies dirnames in-place).
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        for fname in filenames:
            if not fname.endswith(".md"):
                continue

            full = Path(dirpath) / fname
            rel = str(full.relative_to(root))
            title = fname[:-3]  # strip .md

            stat = full.stat()
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            links = extract_links(content)
            tags = extract_tags(content)
            fm = extract_frontmatter(content)

            entry = NoteEntry(
                path=rel,
                title=title,
                links=links,
                tags=tags,
                frontmatter=fm,
                mtime=stat.st_mtime,
                size=stat.st_size,
            )
            entries[rel] = entry
            title_to_path[title.lower()] = rel

    # -- Phase 2: build graph edges ------------------------------------------
    index = NoteIndex()
    index.notes = entries

    for path, entry in entries.items():
        resolved: set[str] = set()
        for link in entry.links:
            target = _resolve_link_target(link, title_to_path)
            if target is not None:
                resolved.add(target)
                index.backlinks.setdefault(target, set()).add(path)
            else:
                index.unresolved.setdefault(link, set()).add(path)

        index.forward_links[path] = resolved

    # Ensure every note has a backlinks entry (even if empty).
    for path in entries:
        index.backlinks.setdefault(path, set())

    # -- Phase 3: classify orphans and dead ends -----------------------------
    for path in entries:
        has_outgoing = bool(index.forward_links.get(path))
        has_incoming = bool(index.backlinks.get(path))

        if not has_outgoing and not has_incoming:
            index.orphans.add(path)
        elif has_incoming and not has_outgoing:
            index.dead_ends.add(path)

    # -- Phase 4: build tag index --------------------------------------------
    for path, entry in entries.items():
        for tag in entry.tags:
            index.tags.setdefault(tag, set()).add(path)

    return index
