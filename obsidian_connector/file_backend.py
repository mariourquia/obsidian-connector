"""Direct file access backend for vaults.

Used as a fallback when the Obsidian CLI is not available (e.g., Linux
AppImage without CLI support, Windows). Provides the same core operations
as ``client.py`` but via direct file system access using pathlib.

This module does NOT import from ``client.py`` -- it is a standalone
alternative, not a wrapper.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import date
from pathlib import Path

# Directories that should be skipped when scanning vault files.
_SKIP_DIRS = frozenset({".obsidian", ".trash", ".git", "node_modules"})

# Regex for markdown task checkboxes: ``- [ ] text`` or ``- [x] text``.
_TASK_RE = re.compile(r"^(\s*)- \[([ xX])\] (.+)$")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_within_vault(resolved: Path, vault_path: Path) -> None:
    """Raise ``ValueError`` if *resolved* is not inside *vault_path*.

    This is the core path-traversal protection. Every public function that
    resolves a user-supplied path calls this before performing I/O.
    """
    try:
        resolved.relative_to(vault_path)
    except ValueError:
        raise ValueError(
            f"Path escapes vault boundary: {resolved} is not inside {vault_path}"
        ) from None


def _sanitize_name(name: str) -> str:
    """Reject names that contain null bytes or are absolute paths."""
    if "\x00" in name:
        raise ValueError(f"Invalid name (contains null byte): {name!r}")
    if os.path.isabs(name):
        raise ValueError(f"Absolute paths are not allowed: {name!r}")
    return name


def _is_hidden_path(rel_path: Path) -> bool:
    """Return True if any component of *rel_path* starts with ``.`` or is in _SKIP_DIRS."""
    for part in rel_path.parts:
        if part.startswith(".") or part in _SKIP_DIRS:
            return True
    return False


def _iter_md_files(vault_path: Path):
    """Yield ``(relative_path, absolute_path)`` for all ``.md`` files in the vault.

    Skips hidden directories, .obsidian, .trash, .git, and node_modules.
    """
    for md_file in vault_path.rglob("*.md"):
        try:
            rel = md_file.relative_to(vault_path)
        except ValueError:
            continue
        if _is_hidden_path(rel):
            continue
        yield rel, md_file


def _resolve_note_path(name_or_path: str, vault_path: Path) -> Path:
    """Resolve a note name or vault-relative path to an absolute file path.

    Tries, in order:
    1. Exact path (with ``.md`` appended if missing)
    2. Case-insensitive search across all vault ``.md`` files

    Parameters
    ----------
    name_or_path:
        Note name (e.g. ``"MyNote"``) or vault-relative path
        (e.g. ``"sub/folder/note"``).
    vault_path:
        Absolute path to the vault root.

    Returns
    -------
    Path
        Absolute path to the resolved note file.

    Raises
    ------
    FileNotFoundError
        If the note cannot be found.
    ValueError
        If the resolved path is outside the vault.
    """
    name_or_path = _sanitize_name(name_or_path)

    # Append .md if not present.
    if not name_or_path.endswith(".md"):
        name_or_path += ".md"

    # Try exact match first.
    candidate = (vault_path / name_or_path).resolve()
    _validate_within_vault(candidate, vault_path.resolve())
    if candidate.is_file():
        return candidate

    # Fall back to case-insensitive search.
    target_lower = name_or_path.lower()
    for rel, abs_path in _iter_md_files(vault_path):
        if str(rel).lower() == target_lower:
            return abs_path

    # Also try matching just the filename (for bare names without path).
    target_stem = Path(name_or_path).stem.lower()
    for rel, abs_path in _iter_md_files(vault_path):
        if abs_path.stem.lower() == target_stem:
            return abs_path

    raise FileNotFoundError(f"Note not found in vault: {name_or_path}")


def _atomic_write(target: Path, content: str) -> None:
    """Write *content* to *target* atomically via temp file + rename.

    Creates parent directories as needed.
    """
    target.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file in the same directory, then rename.
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(target.parent), suffix=".tmp", prefix=".obsx_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path_str).replace(target)
    except BaseException:
        # Clean up the temp file on any failure.
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def file_search(
    query: str,
    vault_path: Path,
    max_results: int = 50,
) -> list[dict]:
    """Search vault note contents for *query*.

    Performs a case-insensitive search across all ``.md`` files in the vault,
    skipping hidden directories (.obsidian, .trash, .git).

    Parameters
    ----------
    query:
        Search string. Matched literally (case-insensitive).
    vault_path:
        Absolute path to the vault root directory.
    max_results:
        Maximum number of files to return (default 50).

    Returns
    -------
    list[dict]
        Each dict has ``"file"`` (vault-relative path str) and ``"matches"``
        (list of ``{"line": int, "text": str}``).  Matches the format
        returned by ``client.search_notes()``.
    """
    vault_path = vault_path.resolve()
    results: list[dict] = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for rel, abs_path in _iter_md_files(vault_path):
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        matches: list[dict] = []
        for i, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                matches.append({"line": i, "text": line.strip()})

        if matches:
            results.append({
                "file": str(rel),
                "matches": matches,
            })
            if len(results) >= max_results:
                break

    return results


def file_read(name_or_path: str, vault_path: Path) -> str:
    """Read a note by name or vault-relative path.

    If the value contains ``/`` or ends with ``.md``, it is treated as a
    path; otherwise as a note name.  Lookup is case-insensitive.

    Parameters
    ----------
    name_or_path:
        Note name (e.g. ``"MyNote"``) or vault-relative path
        (e.g. ``"sub/folder/note.md"``).
    vault_path:
        Absolute path to the vault root directory.

    Returns
    -------
    str
        Raw markdown content of the note.

    Raises
    ------
    FileNotFoundError
        If the note does not exist.
    ValueError
        If the resolved path would escape the vault boundary.
    """
    vault_path = vault_path.resolve()
    resolved = _resolve_note_path(name_or_path, vault_path)
    return resolved.read_text(encoding="utf-8")


def file_list_tasks(
    vault_path: Path,
    status: str | None = None,
) -> list[dict]:
    """Extract markdown task checkboxes from all vault files.

    Finds lines matching ``- [ ] ...`` (todo) and ``- [x] ...`` (done).

    Parameters
    ----------
    vault_path:
        Absolute path to the vault root directory.
    status:
        Optional single-character filter. ``" "`` for todo, ``"x"`` for done.
        ``None`` returns all tasks.

    Returns
    -------
    list[dict]
        Each dict has ``"text"`` (str), ``"status"`` (``" "`` or ``"x"``),
        ``"file"`` (vault-relative path str), and ``"line"`` (int).
        Matches the format returned by ``client.list_tasks()``.
    """
    vault_path = vault_path.resolve()
    tasks: list[dict] = []

    for rel, abs_path in _iter_md_files(vault_path):
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for i, line in enumerate(content.splitlines(), 1):
            m = _TASK_RE.match(line)
            if not m:
                continue

            status_char = m.group(2)
            is_done = status_char.lower() == "x"
            normalized_status = "x" if is_done else " "

            # Apply status filter if given.
            if status is not None and normalized_status != status:
                continue

            tasks.append({
                "text": m.group(3).strip(),
                "status": normalized_status,
                "file": str(rel),
                "line": i,
            })

    return tasks


def file_log_daily(
    text: str,
    vault_path: Path,
    daily_folder: str = "daily",
) -> dict:
    """Append *text* to today's daily note.

    Creates the daily note file (and folder) if they don't exist.
    Uses atomic writes for safety.

    Parameters
    ----------
    text:
        Markdown text to append.
    vault_path:
        Absolute path to the vault root directory.
    daily_folder:
        Vault-relative folder for daily notes (default ``"daily"``).

    Returns
    -------
    dict
        Result with ``"path"`` (vault-relative str), ``"action"``
        (``"appended"`` or ``"created"``), and ``"date"`` (ISO date str).
    """
    vault_path = vault_path.resolve()
    today = date.today().isoformat()
    daily_dir = vault_path / daily_folder
    daily_file = daily_dir / f"{today}.md"

    # Validate the daily file is within the vault.
    _validate_within_vault(daily_file.resolve() if daily_file.exists() else daily_dir.resolve() if daily_dir.exists() else (vault_path / daily_folder), vault_path)

    if daily_file.exists():
        existing = daily_file.read_text(encoding="utf-8")
        # Ensure there's a newline before appending.
        if existing and not existing.endswith("\n"):
            existing += "\n"
        new_content = existing + text + "\n"
        action = "appended"
    else:
        new_content = text + "\n"
        action = "appended"  # matches CLI behavior: always "appended"

    _atomic_write(daily_file, new_content)

    rel_path = str(daily_file.relative_to(vault_path))
    return {
        "path": rel_path,
        "action": action,
        "date": today,
    }


def file_create_note(
    title: str,
    content: str,
    vault_path: Path,
    folder: str = "",
) -> dict:
    """Create a new note in the vault.

    Uses atomic writes. Refuses to overwrite existing notes.

    Parameters
    ----------
    title:
        Note title (used as the filename, ``.md`` appended).
    content:
        Markdown content for the note.
    vault_path:
        Absolute path to the vault root directory.
    folder:
        Optional vault-relative folder path (created if needed).

    Returns
    -------
    dict
        Result with ``"path"`` (vault-relative str), ``"action"``
        (``"created"``), and ``"title"`` (str).

    Raises
    ------
    FileExistsError
        If a note with that title already exists at the target location.
    ValueError
        If the resolved path would escape the vault boundary.
    """
    vault_path = vault_path.resolve()
    title = _sanitize_name(title)

    # Validate folder path if provided.
    if folder:
        folder = _sanitize_name(folder)
        target_dir = (vault_path / folder).resolve()
        _validate_within_vault(target_dir, vault_path)
    else:
        target_dir = vault_path

    # Build the final filename.
    filename = title if title.endswith(".md") else f"{title}.md"
    note_path = (target_dir / filename).resolve()
    _validate_within_vault(note_path, vault_path)

    if note_path.exists():
        raise FileExistsError(f"Note already exists: {note_path.relative_to(vault_path)}")

    _atomic_write(note_path, content)

    rel_path = str(note_path.relative_to(vault_path))
    return {
        "path": rel_path,
        "action": "created",
        "title": title,
    }
