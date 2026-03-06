"""SQLite-backed persistent note index with change detection.

Stores extracted metadata (links, tags, frontmatter) in a local SQLite
database so that incremental rebuilds only re-process changed files.

This module never writes to vault files.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from obsidian_connector.config import resolve_vault_path
from obsidian_connector.graph import (
    NoteEntry,
    NoteIndex,
    _SKIP_DIRS,
    _resolve_link_target,
    extract_frontmatter,
    extract_links,
    extract_tags,
)

_DEFAULT_DB = Path.home() / ".obsidian-connector" / "index.sqlite"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS notes (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    content_hash TEXT,
    links_json TEXT,
    tags_json TEXT,
    frontmatter_json TEXT
);
"""


class IndexStore:
    """SQLite-backed persistent note index with change detection."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # -- Connection management -----------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open (or reuse) a SQLite connection with WAL mode."""
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(_SCHEMA)
        conn.commit()
        self._conn = conn
        return conn

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- Public API ----------------------------------------------------------

    def build_full(self, vault_path: Path | None = None) -> NoteIndex:
        """Drop and rebuild all tables, then return a fresh NoteIndex.

        Parameters
        ----------
        vault_path:
            Absolute path to the vault directory.  Resolved automatically
            if ``None``.

        Returns
        -------
        NoteIndex
        """
        root = Path(vault_path) if vault_path else resolve_vault_path()
        conn = self._connect()

        conn.execute("DELETE FROM notes")
        conn.commit()

        entries: dict[str, NoteEntry] = {}
        title_to_path: dict[str, str] = {}

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if not fname.endswith(".md"):
                    continue

                full = Path(dirpath) / fname
                rel = str(full.relative_to(root))
                title = fname[:-3]

                try:
                    stat = full.stat()
                    content = full.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                links = extract_links(content)
                tags = extract_tags(content)
                fm = extract_frontmatter(content)

                conn.execute(
                    "INSERT OR REPLACE INTO notes "
                    "(path, mtime, size, content_hash, links_json, tags_json, frontmatter_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        rel,
                        stat.st_mtime,
                        stat.st_size,
                        None,
                        json.dumps(links),
                        json.dumps(tags),
                        json.dumps(fm),
                    ),
                )

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

        conn.commit()
        return _build_index_from_entries(entries, title_to_path)

    def update_incremental(self, vault_path: Path | None = None) -> NoteIndex:
        """Incrementally update the index based on file mtime changes.

        Compares on-disk mtimes with stored mtimes.  Only re-processes
        changed or new files, and removes deleted files.

        Parameters
        ----------
        vault_path:
            Absolute path to the vault directory.  Resolved automatically
            if ``None``.

        Returns
        -------
        NoteIndex
        """
        root = Path(vault_path) if vault_path else resolve_vault_path()
        conn = self._connect()

        # Load existing fingerprints from DB.
        stored: dict[str, tuple[float, int]] = {}
        for row in conn.execute("SELECT path, mtime, size FROM notes"):
            stored[row[0]] = (row[1], row[2])

        # Scan disk.
        on_disk: set[str] = set()
        changed: list[tuple[str, Path]] = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if not fname.endswith(".md"):
                    continue
                full = Path(dirpath) / fname
                rel = str(full.relative_to(root))
                on_disk.add(rel)
                stat = full.stat()
                prev = stored.get(rel)
                if prev is None or prev[0] != stat.st_mtime or prev[1] != stat.st_size:
                    changed.append((rel, full))

        # Remove deleted files.
        deleted = set(stored.keys()) - on_disk
        for rel in deleted:
            conn.execute("DELETE FROM notes WHERE path = ?", (rel,))

        # Re-process changed/new files.
        for rel, full in changed:
            title = full.stem
            try:
                stat = full.stat()
                content = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            links = extract_links(content)
            tags = extract_tags(content)
            fm = extract_frontmatter(content)

            conn.execute(
                "INSERT OR REPLACE INTO notes "
                "(path, mtime, size, content_hash, links_json, tags_json, frontmatter_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    rel,
                    stat.st_mtime,
                    stat.st_size,
                    None,
                    json.dumps(links),
                    json.dumps(tags),
                    json.dumps(fm),
                ),
            )

        conn.commit()

        # Rebuild in-memory index from the full DB.
        return self.get_index() or NoteIndex()

    def get_index(self) -> NoteIndex | None:
        """Load NoteIndex from SQLite without re-scanning vault files.

        Returns
        -------
        NoteIndex | None
            Loaded index, or ``None`` if the database is empty.
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT path, mtime, size, links_json, tags_json, frontmatter_json "
            "FROM notes"
        ).fetchall()

        if not rows:
            return None

        entries: dict[str, NoteEntry] = {}
        title_to_path: dict[str, str] = {}

        for path, mtime, size, links_json, tags_json, fm_json in rows:
            title = Path(path).stem
            try:
                links = json.loads(links_json) if links_json else []
                tags = json.loads(tags_json) if tags_json else []
                fm = json.loads(fm_json) if fm_json else {}
            except json.JSONDecodeError:
                continue

            entry = NoteEntry(
                path=path,
                title=title,
                links=tuple(links),
                tags=tuple(tags),
                frontmatter=fm,
                mtime=mtime,
                size=size,
            )
            entries[path] = entry
            title_to_path[title.lower()] = path

        return _build_index_from_entries(entries, title_to_path)

    @staticmethod
    def fingerprint(path: Path) -> tuple[float, int]:
        """Return ``(mtime, size)`` for change detection.

        Parameters
        ----------
        path:
            Absolute file path.

        Returns
        -------
        tuple[float, int]
        """
        stat = path.stat()
        return (stat.st_mtime, stat.st_size)


# ---------------------------------------------------------------------------
# Shared index builder
# ---------------------------------------------------------------------------

def _build_index_from_entries(
    entries: dict[str, NoteEntry],
    title_to_path: dict[str, str],
) -> NoteIndex:
    """Build a NoteIndex from pre-parsed NoteEntry objects."""
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

    for path in entries:
        index.backlinks.setdefault(path, set())

    for path in entries:
        has_outgoing = bool(index.forward_links.get(path))
        has_incoming = bool(index.backlinks.get(path))
        if not has_outgoing and not has_incoming:
            index.orphans.add(path)
        elif has_incoming and not has_outgoing:
            index.dead_ends.add(path)

    for path, entry in entries.items():
        for tag in entry.tags:
            index.tags.setdefault(tag, set()).add(path)

    return index


def load_or_build_index(vault: str | None = None) -> NoteIndex | None:
    """Try to load NoteIndex from SQLite, fall back to in-memory build.

    Returns ``None`` if the index cannot be loaded or built (e.g., vault
    not found, SQLite error). Specific errors are logged but not raised,
    since graph features degrade gracefully.
    """
    store = IndexStore()
    try:
        idx = store.get_index()
        if idx is not None:
            return idx
        from obsidian_connector.config import resolve_vault_path

        vault_path = resolve_vault_path(vault)
        return store.build_full(vault_path)
    except (sqlite3.Error, OSError) as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Index load/build failed (graph features degraded): %s: %s",
            type(exc).__name__,
            exc,
        )
        return None
    finally:
        store.close()
