"""Atomic write manager for obsidian-connector.

Provides safe file mutations with rollback, preview, locking, and
protected-folder enforcement.  Every write goes through write-then-rename
for atomicity, with pre-write snapshots to allow rollback.

This module is the gateway for all vault mutations introduced in v0.6.0.
"""

from __future__ import annotations

import difflib
import os
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from obsidian_connector.audit import log_action
from obsidian_connector.errors import (
    ProtectedFolderError,
    RollbackError,
    WriteLockError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SNAPSHOT_DIR_NAME = ".obsidian-connector"
_SNAPSHOTS_SUBDIR = "snapshots"
_TMP_PREFIX = ".obsx_wm_"
_TMP_SUFFIX = ".tmp"
_DEFAULT_LOCK_TIMEOUT = 5.0
_DEFAULT_SNAPSHOT_KEEP = 10

# Thread-level lock registry to prevent concurrent writes to the same path
# within the same process.
_thread_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Path validation helpers
# ---------------------------------------------------------------------------

def _validate_within_vault(resolved: Path, vault_root: Path) -> None:
    """Raise ``ValueError`` if *resolved* escapes the vault boundary.

    Parameters
    ----------
    resolved:
        The fully resolved target path.
    vault_root:
        The fully resolved vault root directory.
    """
    try:
        resolved.relative_to(vault_root)
    except ValueError:
        raise ValueError(
            f"Path traversal blocked: {resolved} is not inside {vault_root}"
        ) from None


def _resolve_and_validate(path: Path, vault_root: Path) -> Path:
    """Resolve *path* and validate it stays within the vault.

    Returns the resolved absolute path.
    """
    vault_root = vault_root.resolve()
    resolved = path.resolve()
    _validate_within_vault(resolved, vault_root)
    return resolved


def _snapshot_base(vault_root: Path) -> Path:
    """Return the base snapshot directory inside the vault."""
    return vault_root / _SNAPSHOT_DIR_NAME / _SNAPSHOTS_SUBDIR


# ---------------------------------------------------------------------------
# Generated-by frontmatter injection
# ---------------------------------------------------------------------------

def _inject_generated_by(
    content: str,
    tool_name: str | None = None,
) -> str:
    """Prepend ``generated_by`` frontmatter to *content* if not already present.

    If the content already starts with a YAML frontmatter block (``---``),
    the ``generated_by`` field is injected into the existing block.
    Otherwise a new block is created.

    Parameters
    ----------
    content:
        The markdown content to annotate.
    tool_name:
        Name of the originating tool (e.g. ``"obsidian_create_note"``).
        Defaults to ``"obsidian-connector"``.
    """
    tool = tool_name or "obsidian-connector"
    now_iso = datetime.now(timezone.utc).isoformat()
    generated_line = f"generated_by: {tool} @ {now_iso}"

    if content.startswith("---\n"):
        # Inject into existing frontmatter block.
        end = content.find("\n---\n", 4)
        if end == -1:
            # Malformed frontmatter -- treat as no frontmatter.
            return f"---\n{generated_line}\n---\n{content}"
        existing_fm = content[4:end]
        # Check if generated_by already exists.
        if "generated_by:" in existing_fm:
            return content
        new_fm = existing_fm + "\n" + generated_line
        return f"---\n{new_fm}\n---\n{content[end + 5:]}"

    # No frontmatter -- create one.
    return f"---\n{generated_line}\n---\n{content}"


# ---------------------------------------------------------------------------
# Core write operations
# ---------------------------------------------------------------------------

def atomic_write(
    path: Path,
    content: str,
    vault_root: Path,
    metadata: dict[str, Any] | None = None,
    tool_name: str | None = None,
    inject_generated_by: bool = False,
) -> Path:
    """Write *content* to *path* atomically via temp-file-then-rename.

    Parameters
    ----------
    path:
        Target file path (absolute or relative to *vault_root*).
    content:
        String content to write.
    vault_root:
        Absolute path to the vault root.  Used for path-traversal validation.
    metadata:
        Optional metadata dict logged to audit trail.
    tool_name:
        Tool name for ``generated_by`` injection and audit logging.
    inject_generated_by:
        If ``True``, prepend ``generated_by`` frontmatter to content.

    Returns
    -------
    Path
        The resolved absolute path of the written file.

    Raises
    ------
    ValueError
        If the path escapes the vault boundary.
    OSError
        If the write or rename fails.
    """
    resolved = _resolve_and_validate(path, vault_root)

    if inject_generated_by:
        content = _inject_generated_by(content, tool_name)

    resolved.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(resolved.parent),
        suffix=_TMP_SUFFIX,
        prefix=_TMP_PREFIX,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path_str).replace(resolved)
    except BaseException:
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        raise

    # Audit the write.
    log_action(
        command="atomic_write",
        args={"tool_name": tool_name, "metadata": metadata},
        vault=str(vault_root),
        affected_path=str(resolved),
        content=content,
    )

    return resolved


# ---------------------------------------------------------------------------
# Snapshot operations
# ---------------------------------------------------------------------------

def snapshot(path: Path, vault_root: Path) -> Path | None:
    """Create a pre-write snapshot of *path* before mutation.

    Copies the original file to
    ``{vault_root}/.obsidian-connector/snapshots/{ISO-timestamp}/{relative-path}``.

    Parameters
    ----------
    path:
        File to snapshot (must exist).
    vault_root:
        Absolute path to the vault root.

    Returns
    -------
    Path or None
        Absolute path to the snapshot copy, or ``None`` if the source
        file does not exist (nothing to snapshot).
    """
    resolved = _resolve_and_validate(path, vault_root)
    vault_root = vault_root.resolve()

    if not resolved.is_file():
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    rel = resolved.relative_to(vault_root)
    snap_dir = _snapshot_base(vault_root) / timestamp
    snap_file = snap_dir / rel

    snap_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(resolved), str(snap_file))

    log_action(
        command="snapshot",
        args={"timestamp": timestamp},
        vault=str(vault_root),
        affected_path=str(resolved),
    )

    return snap_file


def list_snapshots(vault_root: Path) -> list[str]:
    """Return available snapshot directory names sorted by timestamp.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault root.

    Returns
    -------
    list[str]
        Sorted list of snapshot directory names (ISO timestamp strings).
    """
    vault_root = vault_root.resolve()
    base = _snapshot_base(vault_root)

    if not base.is_dir():
        return []

    dirs = [
        d.name
        for d in sorted(base.iterdir())
        if d.is_dir()
    ]
    return sorted(dirs)


def cleanup_snapshots(vault_root: Path, keep: int = _DEFAULT_SNAPSHOT_KEEP) -> list[str]:
    """Remove old snapshots beyond the *keep* retention count.

    Keeps the most recent *keep* snapshots and removes the rest.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault root.
    keep:
        Number of most-recent snapshots to retain.

    Returns
    -------
    list[str]
        Names of removed snapshot directories.
    """
    vault_root = vault_root.resolve()
    all_snaps = list_snapshots(vault_root)

    if len(all_snaps) <= keep:
        return []

    to_remove = all_snaps[: len(all_snaps) - keep]
    base = _snapshot_base(vault_root)
    removed: list[str] = []

    for snap_name in to_remove:
        snap_path = base / snap_name
        if snap_path.is_dir():
            shutil.rmtree(str(snap_path))
            removed.append(snap_name)

    if removed:
        log_action(
            command="cleanup_snapshots",
            args={"keep": keep, "removed_count": len(removed)},
            vault=str(vault_root),
        )

    return removed


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def rollback(
    vault_root: Path,
    snapshot_dir: str | None = None,
) -> dict[str, list[str]]:
    """Restore files from a snapshot.

    Parameters
    ----------
    vault_root:
        Absolute path to the vault root.
    snapshot_dir:
        Specific snapshot directory name to restore.  If ``None``, the most
        recent snapshot is used.

    Returns
    -------
    dict
        ``{"restored": [...], "snapshot": "..."}`` with the list of
        restored file paths and the snapshot name used.

    Raises
    ------
    RollbackError
        If no snapshots exist or the specified snapshot is not found.
    """
    vault_root = vault_root.resolve()
    base = _snapshot_base(vault_root)

    if snapshot_dir is None:
        snaps = list_snapshots(vault_root)
        if not snaps:
            raise RollbackError("no snapshots available for rollback")
        snapshot_dir = snaps[-1]
    else:
        snap_path = base / snapshot_dir
        if not snap_path.is_dir():
            raise RollbackError(f"snapshot not found: {snapshot_dir}")

    snap_root = base / snapshot_dir
    restored: list[str] = []

    for snap_file in snap_root.rglob("*"):
        if not snap_file.is_file():
            continue
        rel = snap_file.relative_to(snap_root)
        target = vault_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(snap_file), str(target))
        restored.append(str(rel))

    log_action(
        command="rollback",
        args={"snapshot": snapshot_dir, "restored_count": len(restored)},
        vault=str(vault_root),
    )

    return {"restored": restored, "snapshot": snapshot_dir}


# ---------------------------------------------------------------------------
# Preview (diff)
# ---------------------------------------------------------------------------

def preview(path: Path, content: str, vault_root: Path) -> str:
    """Return a unified diff of the proposed write without modifying any file.

    Parameters
    ----------
    path:
        Target file path.
    content:
        Proposed new content.
    vault_root:
        Absolute path to the vault root.

    Returns
    -------
    str
        Unified diff string.  If the file does not exist, shows a
        full-file addition.
    """
    resolved = _resolve_and_validate(path, vault_root)

    if resolved.is_file():
        original = resolved.read_text(encoding="utf-8").splitlines(keepends=True)
    else:
        original = []

    proposed = content.splitlines(keepends=True)
    rel = str(resolved.relative_to(vault_root.resolve()))

    diff = difflib.unified_diff(
        original,
        proposed,
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    )
    return "".join(diff)


# ---------------------------------------------------------------------------
# Protected-folder check
# ---------------------------------------------------------------------------

def check_protected(path: Path, vault_root: Path, config: dict[str, Any]) -> None:
    """Raise ``ProtectedFolderError`` if *path* is inside a protected folder.

    Parameters
    ----------
    path:
        Target file path.
    vault_root:
        Absolute path to the vault root.
    config:
        Configuration dict containing an optional ``protected_folders`` list
        of vault-relative folder paths.

    Raises
    ------
    ProtectedFolderError
        If the path falls within any protected folder.
    """
    resolved = _resolve_and_validate(path, vault_root)
    vault_root = vault_root.resolve()

    protected: list[str] = config.get("protected_folders", [])
    if not protected:
        return

    rel = resolved.relative_to(vault_root)

    for folder in protected:
        folder_path = Path(folder)
        try:
            rel.relative_to(folder_path)
            raise ProtectedFolderError(
                f"write to protected folder denied: {rel} is inside "
                f"protected folder '{folder}'"
            )
        except ValueError:
            continue


# ---------------------------------------------------------------------------
# File locking
# ---------------------------------------------------------------------------

def _get_thread_lock(key: str) -> threading.Lock:
    """Return a per-path threading lock, creating it if needed."""
    with _registry_lock:
        if key not in _thread_locks:
            _thread_locks[key] = threading.Lock()
        return _thread_locks[key]


@contextmanager
def acquire_lock(
    path: Path,
    timeout: float = _DEFAULT_LOCK_TIMEOUT,
) -> Generator[Path, None, None]:
    """Platform-aware file lock as a context manager.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows.
    Also acquires a per-path threading lock to prevent concurrent writes
    within the same process.

    Parameters
    ----------
    path:
        File to lock.  A ``.lock`` sibling is created if the file itself
        is not suitable for locking.
    timeout:
        Maximum seconds to wait for the lock.

    Yields
    ------
    Path
        The locked file path.

    Raises
    ------
    WriteLockError
        If the lock cannot be acquired within *timeout*.
    """
    resolved = path.resolve()
    lock_file = resolved.parent / (resolved.name + ".lock")
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    key = str(lock_file)
    tlock = _get_thread_lock(key)

    acquired = tlock.acquire(timeout=timeout)
    if not acquired:
        raise WriteLockError(
            f"thread lock timeout ({timeout}s) for {resolved}"
        )

    fd = None
    try:
        fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR)

        if sys.platform == "win32":
            _win_lock(fd, timeout)
        else:
            _posix_lock(fd, timeout)

        yield resolved

    except WriteLockError:
        raise
    except Exception as exc:
        raise WriteLockError(f"lock acquisition failed: {exc}") from exc
    finally:
        if fd is not None:
            if sys.platform == "win32":
                _win_unlock(fd)
            else:
                _posix_unlock(fd)
            os.close(fd)
            try:
                os.unlink(str(lock_file))
            except OSError:
                pass
        tlock.release()


def _posix_lock(fd: int, timeout: float) -> None:
    """Acquire a POSIX file lock with timeout via polling."""
    import fcntl
    import time

    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except (IOError, OSError):
            if time.monotonic() >= deadline:
                raise WriteLockError(
                    f"POSIX file lock timeout ({timeout}s)"
                )
            time.sleep(0.05)


def _posix_unlock(fd: int) -> None:
    """Release a POSIX file lock."""
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except (IOError, OSError):
        pass


def _win_lock(fd: int, timeout: float) -> None:
    """Acquire a Windows file lock with timeout via polling."""
    import msvcrt
    import time

    deadline = time.monotonic() + timeout
    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except (IOError, OSError):
            if time.monotonic() >= deadline:
                raise WriteLockError(
                    f"Windows file lock timeout ({timeout}s)"
                )
            time.sleep(0.05)


def _win_unlock(fd: int) -> None:
    """Release a Windows file lock."""
    import msvcrt
    try:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except (IOError, OSError):
        pass
