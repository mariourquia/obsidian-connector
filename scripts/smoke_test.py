#!/usr/bin/env python3
"""Smoke tests -- call each client function with harmless inputs."""

from __future__ import annotations

import sys
import traceback

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.client import (
    ObsidianCLIError,
    list_tasks,
    log_to_daily,
    read_note,
    run_obsidian,
    search_notes,
)

PASS = 0
FAIL = 0


def smoke(label: str, fn, *args, **kwargs):
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    try:
        result = fn(*args, **kwargs)
        print(f"  OK  type={type(result).__name__}")
        if isinstance(result, str):
            preview = result[:200].replace("\n", "\\n")
            print(f"  preview: {preview!r}")
        elif isinstance(result, list):
            print(f"  count: {len(result)}")
            if result:
                print(f"  first:  {result[0]}")
        elif result is None:
            print(f"  (returned None)")
        PASS += 1
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=2)
        FAIL += 1


def main() -> int:
    # 1. Low-level: run_obsidian
    smoke("run_obsidian -- version", run_obsidian, ["version"])

    # 2. search_notes
    smoke("search_notes('test')", search_notes, "test")

    # 3. read_note (by name)
    smoke("read_note('Medical Exams')", read_note, "Medical Exams")

    # 4. read_note (by path)
    smoke("read_note('Medical Exams.md')", read_note, "Medical Exams.md")

    # 5. list_tasks (all todo)
    smoke("list_tasks(todo)", list_tasks, {"todo": True, "limit": 5})

    # 6. list_tasks (done -- may be empty)
    smoke("list_tasks(done)", list_tasks, {"done": True, "limit": 5})

    # 7. log_to_daily
    smoke(
        "log_to_daily (smoke test line)",
        log_to_daily,
        "[smoke_test.py] connector test at import time -- safe to delete",
    )

    # 8. search with no results
    smoke(
        "search_notes('zzz_no_match_zzz_12345')",
        search_notes,
        "zzz_no_match_zzz_12345",
    )

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
