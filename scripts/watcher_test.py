#!/usr/bin/env python3
"""Validate VaultWatcher: debounce, exclude patterns, staleness helpers.

Uses mocked filesystem events -- does NOT require watchdog to be installed.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.watcher import (
    VaultWatcher,
    get_index_age,
    is_stale,
    _HAS_WATCHDOG,
    _PollingWatcher,
)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}")
        FAIL += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp: str, files: dict[str, str]) -> Path:
    """Create a temporary vault directory with the given files."""
    root = Path(tmp) / "vault"
    root.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        full = root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return root


def _mock_index_store() -> MagicMock:
    """Create a mock IndexStore with a realistic _connect."""
    store = MagicMock()
    # Simulate _connect returning a mock connection whose execute returns
    # a row with a recent mtime.
    mock_conn = MagicMock()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: time.time() if idx == 0 else None
    mock_conn.execute.return_value.fetchone.return_value = (time.time(),)
    store._connect.return_value = mock_conn
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_watcher_init() -> None:
    print("\n--- VaultWatcher __init__ ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {"Note.md": "content"})
        store = _mock_index_store()

        watcher = VaultWatcher(vault, store)
        check("vault_path stored", watcher._vault_path == vault)
        check("not running on init", not watcher.is_running)
        check("last_event_time is None on init", watcher.last_event_time is None)
        check("default debounce is 1.0", watcher._debounce_seconds == 1.0)


def test_watcher_custom_params() -> None:
    print("\n--- VaultWatcher custom parameters ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {"A.md": "a"})
        store = _mock_index_store()

        watcher = VaultWatcher(
            vault, store,
            exclude_patterns=["Archive/*"],
            debounce_seconds=0.5,
        )
        check("exclude_patterns stored", watcher._exclude_patterns == ["Archive/*"])
        check("debounce_seconds is 0.5", watcher._debounce_seconds == 0.5)


def test_on_change_md_file() -> None:
    print("\n--- on_change triggers index update for .md files ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {"Note.md": "content"})
        store = _mock_index_store()

        watcher = VaultWatcher(vault, store, debounce_seconds=0.05)
        # Simulate a change event without starting the full watcher.
        watcher.on_change("modified", vault / "Note.md")

        # Wait for debounce to fire.
        time.sleep(0.2)

        check(
            "update_incremental called",
            store.update_incremental.called,
        )
        check(
            "update_incremental called with vault_path",
            store.update_incremental.call_args is not None
            and store.update_incremental.call_args[1].get("vault_path") == vault,
        )
        check("last_event_time set", watcher.last_event_time is not None)


def test_on_change_ignores_non_md() -> None:
    print("\n--- on_change ignores non-.md files ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {"Note.md": "content"})
        store = _mock_index_store()

        watcher = VaultWatcher(vault, store, debounce_seconds=0.05)
        watcher.on_change("created", vault / "image.png")
        watcher.on_change("modified", vault / "data.json")

        time.sleep(0.2)

        check(
            "update_incremental NOT called for non-.md",
            not store.update_incremental.called,
        )
        check(
            "last_event_time still None for non-.md",
            watcher.last_event_time is None,
        )


def test_exclude_patterns() -> None:
    print("\n--- Exclude patterns respected ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Archive/old.md": "old",
            "Notes/active.md": "active",
        })
        store = _mock_index_store()

        watcher = VaultWatcher(
            vault, store,
            exclude_patterns=["Archive/*"],
            debounce_seconds=0.05,
        )
        watcher.on_change("modified", vault / "Archive" / "old.md")

        time.sleep(0.2)
        check(
            "excluded file does NOT trigger update",
            not store.update_incremental.called,
        )

        # Non-excluded file should trigger.
        watcher.on_change("modified", vault / "Notes" / "active.md")
        time.sleep(0.2)
        check(
            "non-excluded file DOES trigger update",
            store.update_incremental.called,
        )


def test_debounce_coalesces_rapid_events() -> None:
    print("\n--- Debounce coalesces rapid events ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "A.md": "a",
            "B.md": "b",
            "C.md": "c",
        })
        store = _mock_index_store()

        watcher = VaultWatcher(vault, store, debounce_seconds=0.15)

        # Fire 3 events rapidly (within debounce window).
        watcher.on_change("modified", vault / "A.md")
        watcher.on_change("modified", vault / "B.md")
        watcher.on_change("modified", vault / "C.md")

        # Wait for debounce + buffer.
        time.sleep(0.4)

        check(
            "update_incremental called exactly once",
            store.update_incremental.call_count == 1,
        )


def test_get_index_age_fresh() -> None:
    print("\n--- get_index_age returns correct seconds ---")

    store = MagicMock()
    now = time.time()
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (now - 10,)
    store._connect.return_value = mock_conn

    age = get_index_age(store)
    check("age is approximately 10s", 9.0 <= age <= 12.0)


def test_is_stale_true() -> None:
    print("\n--- is_stale returns True when old ---")

    store = MagicMock()
    mock_conn = MagicMock()
    # Index is 120 seconds old.
    mock_conn.execute.return_value.fetchone.return_value = (time.time() - 120,)
    store._connect.return_value = mock_conn

    check("is_stale with 120s age, 60s threshold", is_stale(store, threshold=60))


def test_is_stale_false() -> None:
    print("\n--- is_stale returns False when fresh ---")

    store = MagicMock()
    mock_conn = MagicMock()
    # Index is 5 seconds old.
    mock_conn.execute.return_value.fetchone.return_value = (time.time() - 5,)
    store._connect.return_value = mock_conn

    check("not stale with 5s age, 60s threshold", not is_stale(store, threshold=60))


def test_is_stale_empty_db() -> None:
    print("\n--- is_stale with empty database ---")

    store = MagicMock()
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (None,)
    store._connect.return_value = mock_conn

    check("empty db is stale (returns inf)", is_stale(store, threshold=60))


def test_watchdog_fallback() -> None:
    print("\n--- Graceful watchdog fallback ---")

    # Patch _HAS_WATCHDOG to False to simulate missing watchdog.
    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {"Note.md": "content"})
        store = _mock_index_store()

        with patch("obsidian_connector.watcher._HAS_WATCHDOG", False):
            watcher = VaultWatcher(vault, store, debounce_seconds=0.05)
            watcher.start()
            check("watcher running with polling fallback", watcher.is_running)
            check(
                "backend is _PollingWatcher",
                isinstance(watcher._backend, _PollingWatcher),
            )
            watcher.stop()
            check("watcher stopped after polling", not watcher.is_running)


def test_start_stop_lifecycle() -> None:
    print("\n--- start/stop lifecycle ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {"A.md": "a"})
        store = _mock_index_store()

        # Force polling backend so test doesn't need watchdog.
        with patch("obsidian_connector.watcher._HAS_WATCHDOG", False):
            watcher = VaultWatcher(vault, store, debounce_seconds=0.05)

            check("not running before start", not watcher.is_running)
            watcher.start()
            check("running after start", watcher.is_running)
            watcher.stop()
            check("not running after stop", not watcher.is_running)

            # Double stop is safe.
            watcher.stop()
            check("double stop is safe", not watcher.is_running)

            # Restart works.
            watcher.start()
            check("running after restart", watcher.is_running)
            watcher.stop()


def test_start_idempotent() -> None:
    print("\n--- start is idempotent ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {"A.md": "a"})
        store = _mock_index_store()

        with patch("obsidian_connector.watcher._HAS_WATCHDOG", False):
            watcher = VaultWatcher(vault, store, debounce_seconds=0.05)
            watcher.start()
            backend1 = watcher._backend
            watcher.start()  # Second start should be no-op.
            backend2 = watcher._backend
            check("backend unchanged on double start", backend1 is backend2)
            watcher.stop()


def test_polling_watcher_detects_changes() -> None:
    print("\n--- _PollingWatcher detects file changes ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {"Existing.md": "initial"})

        events: list[tuple[str, Path]] = []
        lock = threading.Lock()

        def callback(etype: str, path: Path) -> None:
            with lock:
                events.append((etype, path))

        poller = _PollingWatcher(vault, callback, interval=0.1)
        poller.start()

        # Create a new file.
        time.sleep(0.15)
        (vault / "New.md").write_text("new file", encoding="utf-8")
        time.sleep(0.3)

        poller.stop()

        with lock:
            event_types = [e[0] for e in events]
            created_paths = [str(e[1].name) for e in events if e[0] == "created"]

        check("poller detected creation", "created" in event_types)
        check("created file is New.md", "New.md" in created_paths)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    test_watcher_init()
    test_watcher_custom_params()
    test_on_change_md_file()
    test_on_change_ignores_non_md()
    test_exclude_patterns()
    test_debounce_coalesces_rapid_events()
    test_get_index_age_fresh()
    test_is_stale_true()
    test_is_stale_false()
    test_is_stale_empty_db()
    test_watchdog_fallback()
    test_start_stop_lifecycle()
    test_start_idempotent()
    test_polling_watcher_detects_changes()

    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
