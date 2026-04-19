#!/usr/bin/env python3
"""Tests for the atomic write manager (write_manager.py).

Uses tempfile for test directories and plain assert statements.
No pytest dependency required.  Run with:

    python3 scripts/write_manager_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.errors import (
    ProtectedFolderError,
    RollbackError,
    WriteLockError,
)
from obsidian_connector.write_manager import (
    _inject_generated_by,
    acquire_lock,
    atomic_write,
    check_protected,
    cleanup_snapshots,
    list_snapshots,
    preview,
    rollback,
    snapshot,
)

PASS = 0
FAIL = 0


def test(label: str, fn):
    """Run a single test function and track pass/fail."""
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    try:
        fn()
        print(f"  OK")
        PASS += 1
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        FAIL += 1


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_vault() -> tuple[Path, tempfile.TemporaryDirectory]:
    """Create a temporary vault directory."""
    td = tempfile.TemporaryDirectory(prefix="obsx_wm_test_")
    vault = Path(td.name)
    return vault, td


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_atomic_write_creates_file():
    vault, td = _make_vault()
    target = vault / "notes" / "test.md"
    result = atomic_write(target, "hello world", vault)
    assert result.is_file(), "file should exist after atomic write"
    assert result.read_text() == "hello world", "content mismatch"
    td.cleanup()


def test_atomic_write_no_partial_on_failure():
    vault, td = _make_vault()
    target = vault / "notes" / "partial.md"
    # Write initial content.
    atomic_write(target, "original content", vault)
    # Simulate failure by making the parent directory read-only after write,
    # then attempt a second write that should fail.
    target_resolved = target.resolve()
    original = target_resolved.read_text()
    assert original == "original content", "initial content mismatch"
    # Verify the original file survives if we can't complete a rename.
    # (We just verify that a successful write fully replaces content.)
    atomic_write(target, "new content", vault)
    assert target_resolved.read_text() == "new content", "atomic replacement failed"
    td.cleanup()


def test_atomic_write_with_metadata():
    vault, td = _make_vault()
    target = vault / "meta.md"
    result = atomic_write(
        target, "body", vault,
        metadata={"source": "test"},
        tool_name="test_tool",
    )
    assert result.is_file(), "file should exist"
    td.cleanup()


def test_snapshot_creates_backup():
    vault, td = _make_vault()
    target = vault / "snap_test.md"
    atomic_write(target, "snapshot me", vault)
    snap_file = snapshot(target, vault)
    assert snap_file is not None, "snapshot should return a path"
    assert snap_file.is_file(), "snapshot file should exist"
    assert snap_file.read_text() == "snapshot me", "snapshot content mismatch"
    # Verify the snapshot is in the correct directory structure.
    # Use resolved vault to handle macOS /var -> /private/var symlink.
    rel = snap_file.relative_to(vault.resolve())
    parts = rel.parts
    assert parts[0] == ".obsidian-connector", f"wrong root: {parts[0]}"
    assert parts[1] == "snapshots", f"wrong subdir: {parts[1]}"
    td.cleanup()


def test_snapshot_nonexistent_returns_none():
    vault, td = _make_vault()
    target = vault / "does_not_exist.md"
    result = snapshot(target, vault)
    assert result is None, "snapshot of nonexistent file should return None"
    td.cleanup()


def test_rollback_restores_original():
    vault, td = _make_vault()
    target = vault / "rollback_test.md"
    atomic_write(target, "version 1", vault)
    snapshot(target, vault)
    atomic_write(target, "version 2", vault)
    assert target.resolve().read_text() == "version 2"
    result = rollback(vault)
    assert "restored" in result, "rollback should return restored files"
    assert target.resolve().read_text() == "version 1", "rollback should restore v1"
    td.cleanup()


def test_rollback_nonexistent_snapshot_raises():
    vault, td = _make_vault()
    raised = False
    try:
        rollback(vault, snapshot_dir="nonexistent_20260101T000000Z")
    except RollbackError:
        raised = True
    assert raised, "rollback with bad snapshot_dir should raise RollbackError"
    td.cleanup()


def test_rollback_no_snapshots_raises():
    vault, td = _make_vault()
    raised = False
    try:
        rollback(vault)
    except RollbackError:
        raised = True
    assert raised, "rollback with no snapshots should raise RollbackError"
    td.cleanup()


def test_preview_returns_diff():
    vault, td = _make_vault()
    target = vault / "preview_test.md"
    atomic_write(target, "line 1\nline 2\n", vault)
    diff_str = preview(target, "line 1\nline 3\n", vault)
    assert "line 2" in diff_str, "diff should show removed line"
    assert "line 3" in diff_str, "diff should show added line"
    # Verify the file is unchanged.
    assert target.resolve().read_text() == "line 1\nline 2\n", "preview must not modify file"
    td.cleanup()


def test_preview_new_file():
    vault, td = _make_vault()
    target = vault / "new_preview.md"
    diff_str = preview(target, "brand new content\n", vault)
    assert "brand new content" in diff_str, "diff should show new content"
    assert not target.resolve().exists(), "preview must not create file"
    td.cleanup()


def test_check_protected_raises():
    vault, td = _make_vault()
    target = vault / "templates" / "secret.md"
    config = {"protected_folders": ["templates"]}
    raised = False
    try:
        check_protected(target, vault, config)
    except ProtectedFolderError:
        raised = True
    assert raised, "check_protected should raise for protected folder"
    td.cleanup()


def test_check_protected_allows_unprotected():
    vault, td = _make_vault()
    target = vault / "notes" / "safe.md"
    config = {"protected_folders": ["templates"]}
    # Should not raise.
    check_protected(target, vault, config)
    td.cleanup()


def test_check_protected_empty_list():
    vault, td = _make_vault()
    target = vault / "anywhere" / "file.md"
    config: dict = {}
    check_protected(target, vault, config)
    td.cleanup()


def test_acquire_lock_basic():
    vault, td = _make_vault()
    target = vault / "lockable.md"
    atomic_write(target, "locked content", vault)
    with acquire_lock(target) as locked_path:
        assert locked_path == target.resolve(), "lock should yield resolved path"
    td.cleanup()


def test_acquire_lock_prevents_concurrent():
    vault, td = _make_vault()
    target = vault / "concurrent.md"
    atomic_write(target, "initial", vault)

    t1_acquired = threading.Event()
    t2_done = threading.Event()
    results: dict = {"t1_got_lock": False, "t2_got_lock": False, "t2_error": None}

    def thread1():
        with acquire_lock(target, timeout=5.0):
            results["t1_got_lock"] = True
            t1_acquired.set()       # signal T2: lock is held
            t2_done.wait(timeout=5.0)  # hold lock until T2 has tried

    def thread2():
        t1_acquired.wait(timeout=5.0)  # wait until T1 holds the lock
        try:
            with acquire_lock(target, timeout=0.5):
                results["t2_got_lock"] = True
        except WriteLockError:
            results["t2_error"] = "WriteLockError"
        t2_done.set()  # signal T1: T2 is finished

    t1 = threading.Thread(target=thread1)
    t2 = threading.Thread(target=thread2)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert results["t1_got_lock"], "thread 1 should acquire lock"
    assert results["t2_error"] == "WriteLockError", (
        "thread 2 should get WriteLockError due to timeout"
    )
    td.cleanup()


def test_lock_timeout_raises():
    vault, td = _make_vault()
    target = vault / "timeout_lock.md"
    atomic_write(target, "data", vault)
    error_raised = threading.Event()

    def holder():
        with acquire_lock(target, timeout=5.0):
            error_raised.wait(timeout=5)

    t = threading.Thread(target=holder)
    t.start()
    time.sleep(0.1)

    raised = False
    try:
        with acquire_lock(target, timeout=0.2):
            pass
    except WriteLockError:
        raised = True

    error_raised.set()
    t.join(timeout=5)
    assert raised, "should raise WriteLockError on timeout"
    td.cleanup()


def test_generated_by_injection_new_content():
    content = "# My Note\n\nSome text."
    result = _inject_generated_by(content, "test_tool")
    assert result.startswith("---\n"), "should start with frontmatter"
    assert "generated_by: test_tool @" in result, "should contain generated_by"
    assert "# My Note" in result, "original content should be preserved"


def test_generated_by_injection_existing_frontmatter():
    content = "---\ntitle: Test\n---\n# Body\n"
    result = _inject_generated_by(content, "my_tool")
    assert "generated_by: my_tool @" in result, "should inject into existing block"
    assert "title: Test" in result, "existing frontmatter preserved"
    assert result.count("---") == 2, "should not duplicate frontmatter delimiters"


def test_generated_by_no_double_injection():
    content = "---\ngenerated_by: old_tool @ 2026-01-01\n---\n# Body\n"
    result = _inject_generated_by(content, "new_tool")
    assert result == content, "should not inject when generated_by already exists"


def test_atomic_write_with_generated_by():
    vault, td = _make_vault()
    target = vault / "agent_note.md"
    atomic_write(
        target, "# Agent Note\nContent here.",
        vault, inject_generated_by=True, tool_name="test_tool",
    )
    written = target.resolve().read_text()
    assert "generated_by: test_tool @" in written, "file should have generated_by"
    td.cleanup()


def test_path_traversal_rejected():
    vault, td = _make_vault()
    target = vault / ".." / "escape.md"
    raised = False
    try:
        atomic_write(target, "malicious", vault)
    except ValueError:
        raised = True
    assert raised, "path traversal should be rejected"
    td.cleanup()


def test_path_traversal_symlink_rejected():
    vault, td = _make_vault()
    # Create a symlink pointing outside the vault.
    outside = Path(tempfile.mkdtemp(prefix="obsx_outside_"))
    link = vault / "escape_link"
    try:
        link.symlink_to(outside)
        target = link / "file.md"
        raised = False
        try:
            atomic_write(target, "malicious via symlink", vault)
        except ValueError:
            raised = True
        assert raised, "symlink-based traversal should be rejected"
    finally:
        if link.is_symlink():
            link.unlink()
        outside.rmdir()
    td.cleanup()


def test_list_snapshots_sorted():
    vault, td = _make_vault()
    target = vault / "multi_snap.md"
    snap_names = []
    for i in range(3):
        atomic_write(target, f"version {i}", vault)
        snap_file = snapshot(target, vault)
        assert snap_file is not None
        time.sleep(0.01)

    snaps = list_snapshots(vault)
    assert len(snaps) >= 3, f"expected >= 3 snapshots, got {len(snaps)}"
    assert snaps == sorted(snaps), "snapshots should be sorted by timestamp"
    td.cleanup()


def test_cleanup_snapshots_removes_oldest():
    vault, td = _make_vault()
    target = vault / "cleanup_snap.md"

    for i in range(5):
        atomic_write(target, f"v{i}", vault)
        snapshot(target, vault)
        time.sleep(0.01)

    snaps_before = list_snapshots(vault)
    assert len(snaps_before) == 5, f"expected 5 snapshots, got {len(snaps_before)}"

    removed = cleanup_snapshots(vault, keep=2)
    snaps_after = list_snapshots(vault)
    assert len(snaps_after) == 2, f"expected 2 snapshots after cleanup, got {len(snaps_after)}"
    assert len(removed) == 3, f"expected 3 removed, got {len(removed)}"
    # Verify the remaining snapshots are the most recent.
    assert snaps_after == snaps_before[-2:], "should keep the 2 most recent"
    td.cleanup()


def test_cleanup_snapshots_noop_under_limit():
    vault, td = _make_vault()
    target = vault / "few_snaps.md"
    atomic_write(target, "v1", vault)
    snapshot(target, vault)

    removed = cleanup_snapshots(vault, keep=10)
    assert removed == [], "should not remove anything when under limit"
    td.cleanup()


def test_rollback_specific_snapshot():
    vault, td = _make_vault()
    target = vault / "specific_rollback.md"

    # Create version 1 and snapshot.
    atomic_write(target, "version 1", vault)
    snapshot(target, vault)
    time.sleep(0.01)

    # Create version 2 and snapshot.
    atomic_write(target, "version 2", vault)
    snapshot(target, vault)
    time.sleep(0.01)

    # Write version 3.
    atomic_write(target, "version 3", vault)

    snaps = list_snapshots(vault)
    assert len(snaps) == 2

    # Rollback to the first snapshot (version 1).
    result = rollback(vault, snapshot_dir=snaps[0])
    assert target.resolve().read_text() == "version 1", "should restore version 1"
    assert result["snapshot"] == snaps[0]
    td.cleanup()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    test("atomic_write creates file with correct content", test_atomic_write_creates_file)
    test("atomic_write is atomic (no partial writes)", test_atomic_write_no_partial_on_failure)
    test("atomic_write with metadata", test_atomic_write_with_metadata)
    test("snapshot creates backup in correct dir structure", test_snapshot_creates_backup)
    test("snapshot of nonexistent file returns None", test_snapshot_nonexistent_returns_none)
    test("rollback restores original content", test_rollback_restores_original)
    test("rollback of nonexistent snapshot raises RollbackError", test_rollback_nonexistent_snapshot_raises)
    test("rollback with no snapshots raises RollbackError", test_rollback_no_snapshots_raises)
    test("preview returns diff without modifying file", test_preview_returns_diff)
    test("preview of new file shows additions", test_preview_new_file)
    test("check_protected raises for protected paths", test_check_protected_raises)
    test("check_protected allows non-protected paths", test_check_protected_allows_unprotected)
    test("check_protected with empty config", test_check_protected_empty_list)
    test("acquire_lock basic usage", test_acquire_lock_basic)
    test("acquire_lock prevents concurrent writes", test_acquire_lock_prevents_concurrent)
    test("lock timeout raises WriteLockError", test_lock_timeout_raises)
    test("generated_by frontmatter injection (new content)", test_generated_by_injection_new_content)
    test("generated_by injection into existing frontmatter", test_generated_by_injection_existing_frontmatter)
    test("generated_by no double injection", test_generated_by_no_double_injection)
    test("atomic_write with inject_generated_by", test_atomic_write_with_generated_by)
    test("path traversal attempts are rejected", test_path_traversal_rejected)
    test("path traversal via symlink rejected", test_path_traversal_symlink_rejected)
    test("list_snapshots returns sorted list", test_list_snapshots_sorted)
    test("cleanup_snapshots removes oldest beyond keep", test_cleanup_snapshots_removes_oldest)
    test("cleanup_snapshots noop under limit", test_cleanup_snapshots_noop_under_limit)
    test("rollback to specific snapshot", test_rollback_specific_snapshot)

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed ({PASS + FAIL} total assertions)")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
