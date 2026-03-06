#!/usr/bin/env python3
"""Validate the IndexStore: SQLite persistence and incremental updates."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.index_store import IndexStore

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_full() -> None:
    print("\n--- IndexStore build_full ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Alpha.md": "---\ntitle: Alpha\n---\n[[Beta]] #topic",
            "Beta.md": "# Beta\n[[Alpha]]\n#topic",
            "Gamma.md": "# Gamma\nOrphan note.",
        })

        db_path = Path(tmp) / "test.sqlite"
        store = IndexStore(db_path=db_path)
        try:
            index = store.build_full(vault_path=vault)

            check("3 notes indexed", len(index.notes) == 3)
            check("Alpha in index", "Alpha.md" in index.notes)
            check("Beta in index", "Beta.md" in index.notes)
            check("Gamma in index", "Gamma.md" in index.notes)

            # Verify forward links
            check(
                "Alpha links to Beta",
                "Beta.md" in index.forward_links.get("Alpha.md", set()),
            )

            # Verify backlinks
            check(
                "Alpha has backlink from Beta",
                "Beta.md" in index.backlinks.get("Alpha.md", set()),
            )

            # Verify tags
            check("#topic has 2 notes", len(index.tags.get("#topic", set())) == 2)

            # Verify orphan detection
            check("Gamma is orphan", "Gamma.md" in index.orphans)

            # Verify DB file was created
            check("SQLite file exists", db_path.is_file())
        finally:
            store.close()


def test_get_index() -> None:
    print("\n--- IndexStore get_index ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Note1.md": "[[Note2]]",
            "Note2.md": "[[Note1]]",
        })

        db_path = Path(tmp) / "test.sqlite"
        store = IndexStore(db_path=db_path)
        try:
            # Build first
            store.build_full(vault_path=vault)

            # Close and reopen to test loading from disk
            store.close()

            store2 = IndexStore(db_path=db_path)
            index = store2.get_index()

            check("get_index returns NoteIndex", index is not None)
            if index is not None:
                check("2 notes loaded", len(index.notes) == 2)
                check("Note1 loaded", "Note1.md" in index.notes)
                check("Note2 loaded", "Note2.md" in index.notes)
                check(
                    "forward links preserved",
                    "Note2.md" in index.forward_links.get("Note1.md", set()),
                )
                check(
                    "backlinks preserved",
                    "Note1.md" in index.backlinks.get("Note2.md", set()),
                )
            store2.close()
        finally:
            store.close()


def test_get_index_empty() -> None:
    print("\n--- IndexStore get_index (empty) ---")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "empty.sqlite"
        store = IndexStore(db_path=db_path)
        try:
            index = store.get_index()
            check("empty DB returns None", index is None)
        finally:
            store.close()


def test_update_incremental() -> None:
    print("\n--- IndexStore update_incremental ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Stable.md": "[[Other]] content",
            "Other.md": "Some text #tag",
            "ToDelete.md": "will be removed",
        })

        db_path = Path(tmp) / "test.sqlite"
        store = IndexStore(db_path=db_path)
        try:
            # Build initial index
            index1 = store.build_full(vault_path=vault)
            check("initial: 3 notes", len(index1.notes) == 3)

            # Wait a moment so mtime differs on modification
            time.sleep(0.1)

            # Modify one file
            (vault / "Other.md").write_text("Updated [[Stable]] #newtag", encoding="utf-8")

            # Delete one file
            (vault / "ToDelete.md").unlink()

            # Add a new file
            (vault / "New.md").write_text("I am new [[Stable]]", encoding="utf-8")

            # Run incremental update
            index2 = store.update_incremental(vault_path=vault)

            check("incremental: 3 notes (1 deleted, 1 added)", len(index2.notes) == 3)
            check("ToDelete removed", "ToDelete.md" not in index2.notes)
            check("New added", "New.md" in index2.notes)
            check("Stable still present", "Stable.md" in index2.notes)
            check("Other still present", "Other.md" in index2.notes)

            # Check updated content was re-parsed
            other_entry = index2.notes.get("Other.md")
            check(
                "Other has updated link to Stable",
                other_entry is not None
                and "Stable.md" in index2.forward_links.get("Other.md", set()),
            )
            check(
                "Other has #newtag",
                other_entry is not None and "#newtag" in other_entry.tags,
            )
        finally:
            store.close()


def test_unchanged_files_not_reprocessed() -> None:
    print("\n--- IndexStore incremental skips unchanged ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "A.md": "[[B]]",
            "B.md": "[[A]]",
        })

        db_path = Path(tmp) / "test.sqlite"
        store = IndexStore(db_path=db_path)
        try:
            index1 = store.build_full(vault_path=vault)
            check("initial: 2 notes", len(index1.notes) == 2)

            # Run incremental with no changes
            index2 = store.update_incremental(vault_path=vault)
            check("no-change update: 2 notes", len(index2.notes) == 2)
            check("A still present", "A.md" in index2.notes)
            check("B still present", "B.md" in index2.notes)
            check(
                "links preserved after no-op update",
                "B.md" in index2.forward_links.get("A.md", set()),
            )
        finally:
            store.close()


def test_fingerprint() -> None:
    print("\n--- IndexStore fingerprint ---")

    with tempfile.TemporaryDirectory() as tmp:
        test_file = Path(tmp) / "test.md"
        test_file.write_text("hello", encoding="utf-8")

        store = IndexStore(db_path=Path(tmp) / "db.sqlite")
        try:
            mtime, size = store.fingerprint(test_file)
            check("mtime is float", isinstance(mtime, float))
            check("size is correct", size == 5)

            # Modify the file
            time.sleep(0.1)
            test_file.write_text("hello world", encoding="utf-8")
            mtime2, size2 = store.fingerprint(test_file)
            check("mtime changed after write", mtime2 > mtime)
            check("size changed after write", size2 == 11)
        finally:
            store.close()


def test_build_full_replaces_previous() -> None:
    print("\n--- IndexStore build_full replaces previous ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Old.md": "old note",
        })

        db_path = Path(tmp) / "test.sqlite"
        store = IndexStore(db_path=db_path)
        try:
            index1 = store.build_full(vault_path=vault)
            check("first build: 1 note", len(index1.notes) == 1)

            # Remove old file, add new
            (vault / "Old.md").unlink()
            (vault / "New.md").write_text("new note", encoding="utf-8")

            index2 = store.build_full(vault_path=vault)
            check("rebuild: 1 note", len(index2.notes) == 1)
            check("Old removed after rebuild", "Old.md" not in index2.notes)
            check("New present after rebuild", "New.md" in index2.notes)
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    test_build_full()
    test_get_index()
    test_get_index_empty()
    test_update_incremental()
    test_unchanged_files_not_reprocessed()
    test_fingerprint()
    test_build_full_replaces_previous()

    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
