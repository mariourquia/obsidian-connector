"""Filesystem watcher for incremental re-indexing on vault file changes.

Watches a vault directory for ``.md`` file creates, modifies, and deletes,
then triggers incremental re-indexing of affected files via
:class:`~obsidian_connector.index_store.IndexStore`.

Uses ``watchdog`` when available; falls back to a polling-based watcher
when it is not installed.  Both implementations run in a background thread.

This module never writes to vault files.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

# Optional dependency -- graceful fallback when not installed.
try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    _HAS_WATCHDOG = True
except ImportError:
    _HAS_WATCHDOG = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Staleness helpers
# ---------------------------------------------------------------------------

def get_index_age(index_store: Any) -> float:
    """Return seconds since the last index update.

    Reads the most recent mtime from the index database.  If the database
    is empty or inaccessible, returns ``float('inf')``.

    Parameters
    ----------
    index_store:
        An :class:`~obsidian_connector.index_store.IndexStore` instance.

    Returns
    -------
    float
        Seconds since the newest indexed file was modified.
    """
    try:
        conn = index_store._connect()
        row = conn.execute("SELECT MAX(mtime) FROM notes").fetchone()
        if row and row[0] is not None:
            return time.time() - row[0]
    except Exception:
        logger.debug("get_index_age: unable to query index", exc_info=True)
    return float("inf")


def is_stale(index_store: Any, threshold: float = 60.0) -> bool:
    """Return ``True`` if the index is older than *threshold* seconds.

    Parameters
    ----------
    index_store:
        An :class:`~obsidian_connector.index_store.IndexStore` instance.
    threshold:
        Maximum acceptable age in seconds (default 60).

    Returns
    -------
    bool
    """
    return get_index_age(index_store) > threshold


# ---------------------------------------------------------------------------
# Polling-based fallback watcher
# ---------------------------------------------------------------------------

class _PollingWatcher:
    """Simple polling-based file watcher (fallback when watchdog is absent).

    Scans the vault directory at a fixed interval and detects new, modified,
    or deleted ``.md`` files by comparing mtime/size fingerprints.
    """

    def __init__(
        self,
        vault_path: Path,
        callback: Callable[[str, Path], None],
        interval: float = 2.0,
    ) -> None:
        self._vault_path = vault_path
        self._callback = callback
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._fingerprints: dict[str, tuple[float, int]] = {}

    def start(self) -> None:
        """Start the polling loop in a daemon thread."""
        self._fingerprints = self._scan()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="vault-poller"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling loop to stop and wait for the thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- internals -----------------------------------------------------------

    def _scan(self) -> dict[str, tuple[float, int]]:
        """Walk vault and collect (mtime, size) per .md file."""
        result: dict[str, tuple[float, int]] = {}
        skip = {".obsidian", ".trash", ".git", "node_modules"}
        for dirpath, dirnames, filenames in os.walk(self._vault_path):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for fname in filenames:
                if not fname.endswith(".md"):
                    continue
                full = Path(dirpath) / fname
                try:
                    st = full.stat()
                    result[str(full)] = (st.st_mtime, st.st_size)
                except OSError:
                    continue
        return result

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            if self._stop_event.is_set():
                break
            try:
                current = self._scan()
            except OSError:
                continue

            # Detect creates and modifications.
            for fpath, fp in current.items():
                prev = self._fingerprints.get(fpath)
                if prev is None:
                    self._callback("created", Path(fpath))
                elif prev != fp:
                    self._callback("modified", Path(fpath))

            # Detect deletes.
            for fpath in set(self._fingerprints) - set(current):
                self._callback("deleted", Path(fpath))

            self._fingerprints = current


# ---------------------------------------------------------------------------
# Watchdog-based handler
# ---------------------------------------------------------------------------

if _HAS_WATCHDOG:

    class _WatchdogHandler(FileSystemEventHandler):  # type: ignore[misc]
        """Translates watchdog events into ``(event_type, path)`` callbacks."""

        def __init__(self, callback: Callable[[str, Path], None]) -> None:
            super().__init__()
            self._callback = callback

        def on_created(self, event: FileSystemEvent) -> None:
            if not event.is_directory and event.src_path.endswith(".md"):
                self._callback("created", Path(event.src_path))

        def on_modified(self, event: FileSystemEvent) -> None:
            if not event.is_directory and event.src_path.endswith(".md"):
                self._callback("modified", Path(event.src_path))

        def on_deleted(self, event: FileSystemEvent) -> None:
            if not event.is_directory and event.src_path.endswith(".md"):
                self._callback("deleted", Path(event.src_path))


# ---------------------------------------------------------------------------
# VaultWatcher
# ---------------------------------------------------------------------------

class VaultWatcher:
    """Watch a vault directory for ``.md`` file changes and trigger re-index.

    Parameters
    ----------
    vault_path:
        Absolute path to the vault root.
    index_store:
        An :class:`~obsidian_connector.index_store.IndexStore` instance that
        will receive ``update_incremental`` calls on change.
    exclude_patterns:
        Optional list of glob patterns (e.g. ``["Archive/*", ".trash/*"]``).
        Matching files are ignored.
    debounce_seconds:
        Minimum interval between successive re-index triggers.  Rapid
        changes within this window are coalesced into a single update.
    """

    def __init__(
        self,
        vault_path: Path | str,
        index_store: Any,
        exclude_patterns: list[str] | None = None,
        debounce_seconds: float = 1.0,
    ) -> None:
        self._vault_path = Path(vault_path)
        self._index_store = index_store
        self._exclude_patterns = exclude_patterns or []
        self._debounce_seconds = debounce_seconds

        self._running = False
        self._last_event_time: float | None = None
        self._lock = threading.Lock()

        # Debounce state
        self._pending_timer: threading.Timer | None = None
        self._pending_paths: set[Path] = set()

        # Backend (watchdog Observer or _PollingWatcher)
        self._backend: Any = None

    # -- Properties ----------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether the watcher is currently active."""
        return self._running

    @property
    def last_event_time(self) -> float | None:
        """Epoch timestamp of the most recent change event, or ``None``."""
        return self._last_event_time

    # -- Lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Begin watching the vault directory for ``.md`` file changes.

        Uses ``watchdog`` if available; otherwise falls back to polling.
        """
        if self._running:
            return

        if _HAS_WATCHDOG:
            handler = _WatchdogHandler(self.on_change)
            observer = Observer()
            observer.schedule(handler, str(self._vault_path), recursive=True)
            observer.daemon = True
            observer.start()
            self._backend = observer
            logger.info(
                "Vault watcher started (watchdog): %s", self._vault_path
            )
        else:
            poller = _PollingWatcher(
                self._vault_path, self.on_change, interval=2.0
            )
            poller.start()
            self._backend = poller
            logger.info(
                "Vault watcher started (polling fallback): %s",
                self._vault_path,
            )

        self._running = True

    def stop(self) -> None:
        """Stop watching and clean up background threads."""
        if not self._running:
            return

        with self._lock:
            if self._pending_timer is not None:
                self._pending_timer.cancel()
                self._pending_timer = None

        if self._backend is not None:
            self._backend.stop()
            if _HAS_WATCHDOG and hasattr(self._backend, "join"):
                self._backend.join(timeout=5.0)
            self._backend = None

        self._running = False
        logger.info("Vault watcher stopped: %s", self._vault_path)

    # -- Event handling ------------------------------------------------------

    def on_change(self, event_type: str, path: Path) -> None:
        """Handle a filesystem change event.

        Filters out non-.md files and excluded paths, then schedules a
        debounced incremental re-index.

        Parameters
        ----------
        event_type:
            One of ``"created"``, ``"modified"``, ``"deleted"``.
        path:
            Absolute path to the changed file.
        """
        # Only .md files.
        if not str(path).endswith(".md"):
            return

        # Compute vault-relative path for exclude matching.
        try:
            rel = path.relative_to(self._vault_path)
        except ValueError:
            rel = path
        rel_str = str(rel)

        # Check exclude patterns.
        for pattern in self._exclude_patterns:
            if fnmatch.fnmatch(rel_str, pattern):
                logger.debug("Excluded by pattern %r: %s", pattern, rel_str)
                return

        self._last_event_time = time.time()
        logger.debug("Vault change: %s %s", event_type, rel_str)

        # Debounce: accumulate paths and schedule a single re-index.
        with self._lock:
            self._pending_paths.add(path)
            if self._pending_timer is not None:
                self._pending_timer.cancel()
            self._pending_timer = threading.Timer(
                self._debounce_seconds, self._flush
            )
            self._pending_timer.daemon = True
            self._pending_timer.start()

    def _flush(self) -> None:
        """Run the debounced incremental re-index."""
        with self._lock:
            paths = self._pending_paths.copy()
            self._pending_paths.clear()
            self._pending_timer = None

        if not paths:
            return

        logger.info(
            "Re-indexing %d changed file(s) in %s", len(paths), self._vault_path
        )
        try:
            self._index_store.update_incremental(vault_path=self._vault_path)
        except Exception:
            logger.error(
                "Incremental re-index failed", exc_info=True
            )
