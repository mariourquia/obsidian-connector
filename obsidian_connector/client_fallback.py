"""Client functions with automatic file_backend fallback.

When the Obsidian desktop app is not running or its CLI is not found,
these wrappers transparently fall back to direct file access via
``file_backend.py``.  All other errors propagate unchanged.

Import these instead of ``client.*`` to get fallback behavior.
"""

from __future__ import annotations

import logging

from obsidian_connector.client import (
    ObsidianCLIError,
    batch_read_notes as _cli_batch_read,
    list_tasks as _cli_list_tasks,
    log_to_daily as _cli_log_to_daily,
    read_note as _cli_read_note,
    search_notes as _cli_search_notes,
)
from obsidian_connector.config import resolve_vault_path
from obsidian_connector.errors import ObsidianNotFound, ObsidianNotRunning
from obsidian_connector.file_backend import (
    file_list_tasks,
    file_log_daily,
    file_read,
    file_search,
)

__all__ = [
    "ObsidianCLIError",
    "batch_read_notes",
    "list_tasks",
    "log_to_daily",
    "read_note",
    "search_notes",
]

_log = logging.getLogger(__name__)

_FALLBACK_ERRORS = (ObsidianNotRunning, ObsidianNotFound)


def _extract_status(filter: dict | None) -> str | None:
    """Convert a client.py filter dict to a file_backend status char."""
    if filter is None:
        return None
    if filter.get("status") == "open" or filter.get("todo") is True:
        return " "
    if filter.get("status") == "completed" or filter.get("done") is True:
        return "x"
    return None


def search_notes(query: str, vault: str | None = None) -> list[dict]:
    """Search notes, falling back to file_backend when CLI is unavailable."""
    try:
        return _cli_search_notes(query, vault)
    except _FALLBACK_ERRORS:
        _log.debug("CLI unavailable, falling back to file_backend for search")
        vault_path = resolve_vault_path(vault)
        return file_search(query, vault_path)


def read_note(name_or_path: str, vault: str | None = None) -> str:
    """Read a note, falling back to file_backend when CLI is unavailable."""
    try:
        return _cli_read_note(name_or_path, vault)
    except _FALLBACK_ERRORS:
        _log.debug("CLI unavailable, falling back to file_backend for read")
        vault_path = resolve_vault_path(vault)
        return file_read(name_or_path, vault_path)


def list_tasks(
    filter: dict | None = None, vault: str | None = None
) -> list[dict]:
    """List tasks, falling back to file_backend when CLI is unavailable."""
    try:
        return _cli_list_tasks(filter, vault)
    except _FALLBACK_ERRORS:
        _log.debug("CLI unavailable, falling back to file_backend for list_tasks")
        vault_path = resolve_vault_path(vault)
        return file_list_tasks(vault_path, status=_extract_status(filter))


def log_to_daily(content: str, vault: str | None = None) -> None:
    """Append to daily note, falling back to file_backend when CLI is unavailable."""
    try:
        _cli_log_to_daily(content, vault)
    except _FALLBACK_ERRORS:
        _log.debug("CLI unavailable, falling back to file_backend for log_to_daily")
        vault_path = resolve_vault_path(vault)
        file_log_daily(content, vault_path)


def batch_read_notes(
    paths: list[str],
    vault: str | None = None,
    max_concurrent: int = 4,
) -> dict[str, str]:
    """Batch-read notes, falling back to file_backend when CLI is unavailable."""
    try:
        return _cli_batch_read(paths, vault, max_concurrent)
    except _FALLBACK_ERRORS:
        _log.debug("CLI unavailable, falling back to file_backend for batch_read")
        vault_path = resolve_vault_path(vault)
        results: dict[str, str] = {}
        for p in paths:
            try:
                results[p] = file_read(p, vault_path)
            except FileNotFoundError:
                continue
        return results
