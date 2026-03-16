#!/usr/bin/env python3
"""Validate the file_backend module: direct file access for CLI-less platforms."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.file_backend import (
    file_create_note,
    file_list_tasks,
    file_log_daily,
    file_read,
    file_search,
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


# ---------------------------------------------------------------------------
# file_search tests
# ---------------------------------------------------------------------------

def test_file_search_basic() -> None:
    print("\n--- file_search: basic ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "note1.md": "The quick brown fox",
            "note2.md": "The lazy dog",
        })

        results = file_search("quick", vault)
        check("finds 1 matching file", len(results) == 1)
        check("note1 matched", any("note1" in r["file"] for r in results))
        check("match has line info", results[0]["matches"][0]["line"] == 1)
        check("match has text", "quick" in results[0]["matches"][0]["text"])


def test_file_search_subdirectory() -> None:
    print("\n--- file_search: subdirectory ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "note1.md": "The quick brown fox",
            "sub/note3.md": "quick fox again",
        })

        results = file_search("quick", vault)
        check("finds 2 matching files", len(results) == 2)
        check("note1 matched", any("note1" in r["file"] for r in results))
        check("sub/note3 matched", any("note3" in r["file"] for r in results))


def test_file_search_case_insensitive() -> None:
    print("\n--- file_search: case insensitive ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "note.md": "Hello World",
        })

        results = file_search("hello", vault)
        check("case-insensitive match", len(results) == 1)


def test_file_search_skips_hidden() -> None:
    print("\n--- file_search: skips hidden dirs ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "visible.md": "findme content",
            ".obsidian/config.md": "findme hidden",
            ".trash/deleted.md": "findme trash",
        })

        results = file_search("findme", vault)
        check("only visible file found", len(results) == 1)
        check("visible.md matched", "visible" in results[0]["file"])


def test_file_search_no_results() -> None:
    print("\n--- file_search: no results ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "note.md": "nothing here",
        })

        results = file_search("nonexistent", vault)
        check("empty results", results == [])


def test_file_search_multiline() -> None:
    print("\n--- file_search: multiline ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "note.md": "line one\nfind this\nline three\nfind again",
        })

        results = file_search("find", vault)
        check("one file found", len(results) == 1)
        check("two matches in file", len(results[0]["matches"]) == 2)
        check("first match at line 2", results[0]["matches"][0]["line"] == 2)
        check("second match at line 4", results[0]["matches"][1]["line"] == 4)


def test_file_search_max_results() -> None:
    print("\n--- file_search: max_results ---")

    with tempfile.TemporaryDirectory() as tmp:
        files = {f"note{i}.md": "common word here" for i in range(10)}
        vault = _make_vault(tmp, files)

        results = file_search("common", vault, max_results=3)
        check("limited to 3 results", len(results) == 3)


# ---------------------------------------------------------------------------
# file_read tests
# ---------------------------------------------------------------------------

def test_file_read_basic() -> None:
    print("\n--- file_read: basic ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "test.md": "# Hello\nWorld",
        })

        content = file_read("test", vault)
        check("reads content", content == "# Hello\nWorld")


def test_file_read_with_extension() -> None:
    print("\n--- file_read: with .md extension ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "test.md": "content here",
        })

        content = file_read("test.md", vault)
        check("reads with .md", content == "content here")


def test_file_read_with_path() -> None:
    print("\n--- file_read: vault-relative path ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "sub/folder/note.md": "deep content",
        })

        content = file_read("sub/folder/note", vault)
        check("reads from subdirectory", content == "deep content")


def test_file_read_case_insensitive() -> None:
    print("\n--- file_read: case-insensitive ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "MyNote.md": "case test",
        })

        content = file_read("mynote", vault)
        check("case-insensitive lookup", content == "case test")


def test_file_read_not_found() -> None:
    print("\n--- file_read: not found ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {})

        try:
            file_read("nonexistent", vault)
            check("raises FileNotFoundError", False)
        except FileNotFoundError:
            check("raises FileNotFoundError", True)


def test_file_read_path_traversal() -> None:
    print("\n--- file_read: path traversal protection ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "safe.md": "safe content",
        })

        # Attempt to escape the vault
        try:
            file_read("../../etc/passwd", vault)
            check("blocks path traversal", False)
        except (ValueError, FileNotFoundError):
            check("blocks path traversal", True)

        # Attempt with ../ embedded
        try:
            file_read("sub/../../../etc/passwd", vault)
            check("blocks embedded traversal", False)
        except (ValueError, FileNotFoundError):
            check("blocks embedded traversal", True)


# ---------------------------------------------------------------------------
# file_list_tasks tests
# ---------------------------------------------------------------------------

def test_file_list_tasks_basic() -> None:
    print("\n--- file_list_tasks: basic ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "tasks.md": (
                "# Tasks\n"
                "- [ ] Buy groceries\n"
                "- [x] Send email\n"
                "- [ ] Write report\n"
            ),
        })

        tasks = file_list_tasks(vault)
        check("finds all tasks", len(tasks) == 3)
        todo = [t for t in tasks if t["status"] == " "]
        done = [t for t in tasks if t["status"] == "x"]
        check("2 todo tasks", len(todo) == 2)
        check("1 done task", len(done) == 1)
        check("task has text", any(t["text"] == "Buy groceries" for t in tasks))
        check("task has file", all("file" in t for t in tasks))
        check("task has line", all("line" in t for t in tasks))


def test_file_list_tasks_filter_status() -> None:
    print("\n--- file_list_tasks: filter by status ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "tasks.md": (
                "- [ ] Open task\n"
                "- [x] Done task\n"
                "- [ ] Another open\n"
            ),
        })

        todo_only = file_list_tasks(vault, status=" ")
        check("todo filter", len(todo_only) == 2)
        check("all todo", all(t["status"] == " " for t in todo_only))

        done_only = file_list_tasks(vault, status="x")
        check("done filter", len(done_only) == 1)
        check("all done", all(t["status"] == "x" for t in done_only))


def test_file_list_tasks_multifile() -> None:
    print("\n--- file_list_tasks: multiple files ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "project.md": "- [ ] Task A\n",
            "personal.md": "- [ ] Task B\n- [x] Task C\n",
        })

        tasks = file_list_tasks(vault)
        check("tasks from multiple files", len(tasks) == 3)
        files = {t["file"] for t in tasks}
        check("tasks from 2 files", len(files) == 2)


def test_file_list_tasks_skips_hidden() -> None:
    print("\n--- file_list_tasks: skips hidden dirs ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "visible.md": "- [ ] Visible task\n",
            ".obsidian/plugin.md": "- [ ] Hidden task\n",
        })

        tasks = file_list_tasks(vault)
        check("only visible task", len(tasks) == 1)
        check("correct task", tasks[0]["text"] == "Visible task")


def test_file_list_tasks_uppercase_x() -> None:
    print("\n--- file_list_tasks: uppercase X ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "note.md": "- [X] Done with uppercase\n",
        })

        tasks = file_list_tasks(vault)
        check("uppercase X parsed", len(tasks) == 1)
        check("status normalized to x", tasks[0]["status"] == "x")


def test_file_list_tasks_empty() -> None:
    print("\n--- file_list_tasks: no tasks ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "note.md": "# Just a heading\nSome text\n",
        })

        tasks = file_list_tasks(vault)
        check("no tasks found", tasks == [])


# ---------------------------------------------------------------------------
# file_log_daily tests
# ---------------------------------------------------------------------------

def test_file_log_daily_creates_file() -> None:
    print("\n--- file_log_daily: creates file ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {})

        result = file_log_daily("Hello world", vault)
        today = date.today().isoformat()
        daily_path = vault / "daily" / f"{today}.md"

        check("daily file created", daily_path.exists())
        content = daily_path.read_text(encoding="utf-8")
        check("content appended", "Hello world" in content)
        check("result has path", "path" in result)
        check("result has action", result.get("action") == "appended")


def test_file_log_daily_appends() -> None:
    print("\n--- file_log_daily: appends to existing ---")

    with tempfile.TemporaryDirectory() as tmp:
        today = date.today().isoformat()
        vault = _make_vault(tmp, {
            f"daily/{today}.md": "# Daily Note\n\nExisting content\n",
        })

        file_log_daily("New entry", vault)

        daily_path = vault / "daily" / f"{today}.md"
        content = daily_path.read_text(encoding="utf-8")
        check("existing content preserved", "Existing content" in content)
        check("new content appended", "New entry" in content)


def test_file_log_daily_result_format() -> None:
    print("\n--- file_log_daily: result format ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {})

        result = file_log_daily("Test entry", vault)
        check("result is dict", isinstance(result, dict))
        check("has path key", "path" in result)
        check("has action key", "action" in result)
        check("has date key", "date" in result)
        check("date is today", result["date"] == date.today().isoformat())


# ---------------------------------------------------------------------------
# file_create_note tests
# ---------------------------------------------------------------------------

def test_file_create_note_basic() -> None:
    print("\n--- file_create_note: basic ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {})

        result = file_create_note("My Note", "# My Note\n\nContent here", vault)
        note_path = vault / "My Note.md"

        check("note file created", note_path.exists())
        content = note_path.read_text(encoding="utf-8")
        check("content written", "Content here" in content)
        check("result has path", "path" in result)
        check("result has action", result.get("action") == "created")


def test_file_create_note_in_folder() -> None:
    print("\n--- file_create_note: in folder ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {})

        result = file_create_note(
            "Sub Note", "content", vault, folder="projects/active"
        )
        note_path = vault / "projects" / "active" / "Sub Note.md"

        check("note in subfolder", note_path.exists())
        check("result path correct", "projects/active" in result["path"])


def test_file_create_note_already_exists() -> None:
    print("\n--- file_create_note: already exists ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Existing.md": "original content",
        })

        try:
            file_create_note("Existing", "new content", vault)
            check("raises FileExistsError", False)
        except FileExistsError:
            check("raises FileExistsError", True)

        # Verify original was not overwritten
        content = (vault / "Existing.md").read_text(encoding="utf-8")
        check("original preserved", content == "original content")


def test_file_create_note_path_traversal() -> None:
    print("\n--- file_create_note: path traversal protection ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {})

        try:
            file_create_note("../../evil", "malicious", vault)
            check("blocks title traversal", False)
        except ValueError:
            check("blocks title traversal", True)

        try:
            file_create_note("note", "content", vault, folder="../../etc")
            check("blocks folder traversal", False)
        except ValueError:
            check("blocks folder traversal", True)


def test_file_create_note_result_format() -> None:
    print("\n--- file_create_note: result format ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {})

        result = file_create_note("Test", "body", vault)
        check("result is dict", isinstance(result, dict))
        check("has path key", "path" in result)
        check("has action key", "action" in result)
        check("has title key", "title" in result)
        check("title matches", result["title"] == "Test")


# ---------------------------------------------------------------------------
# Path traversal edge cases
# ---------------------------------------------------------------------------

def test_path_traversal_edge_cases() -> None:
    print("\n--- path traversal edge cases ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "safe.md": "safe content",
        })

        # Absolute path attempt
        try:
            file_read("/etc/passwd", vault)
            check("blocks absolute path", False)
        except (ValueError, FileNotFoundError):
            check("blocks absolute path", True)

        # Null byte injection
        try:
            file_read("note\x00.md", vault)
            check("blocks null byte", False)
        except (ValueError, FileNotFoundError):
            check("blocks null byte", True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # file_search
    test_file_search_basic()
    test_file_search_subdirectory()
    test_file_search_case_insensitive()
    test_file_search_skips_hidden()
    test_file_search_no_results()
    test_file_search_multiline()
    test_file_search_max_results()

    # file_read
    test_file_read_basic()
    test_file_read_with_extension()
    test_file_read_with_path()
    test_file_read_case_insensitive()
    test_file_read_not_found()
    test_file_read_path_traversal()

    # file_list_tasks
    test_file_list_tasks_basic()
    test_file_list_tasks_filter_status()
    test_file_list_tasks_multifile()
    test_file_list_tasks_skips_hidden()
    test_file_list_tasks_uppercase_x()
    test_file_list_tasks_empty()

    # file_log_daily
    test_file_log_daily_creates_file()
    test_file_log_daily_appends()
    test_file_log_daily_result_format()

    # file_create_note
    test_file_create_note_basic()
    test_file_create_note_in_folder()
    test_file_create_note_already_exists()
    test_file_create_note_path_traversal()
    test_file_create_note_result_format()

    # Edge cases
    test_path_traversal_edge_cases()

    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
