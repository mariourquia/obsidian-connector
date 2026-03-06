#!/usr/bin/env python3
"""Performance tests -- batch_read_notes vs sequential reads."""

from __future__ import annotations

import sys
import time
import traceback

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.client import (
    ObsidianCLIError,
    batch_read_notes,
    read_note,
    search_notes,
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
# Tests
# ---------------------------------------------------------------------------

def test_batch_empty() -> None:
    print("\n--- batch_read_notes: empty list ---")
    result = batch_read_notes([])
    check("empty input returns empty dict", result == {})


def test_batch_single() -> None:
    print("\n--- batch_read_notes: single note ---")
    # Find a real note to read.
    try:
        hits = search_notes("test", vault=None)
    except ObsidianCLIError:
        print("  SKIP  (cannot search vault)")
        return

    if not hits:
        print("  SKIP  (no search results)")
        return

    path = hits[0].get("file", "")
    if not path:
        print("  SKIP  (no file in result)")
        return

    result = batch_read_notes([path])
    check("single path returns 1 entry", len(result) == 1)
    check("path key present", path in result)
    check("content is non-empty string", isinstance(result.get(path, ""), str))


def test_batch_multiple_and_benchmark() -> None:
    print("\n--- batch_read_notes: multiple + benchmark ---")
    try:
        hits = search_notes("the", vault=None)
    except ObsidianCLIError:
        print("  SKIP  (cannot search vault)")
        return

    if len(hits) < 2:
        print("  SKIP  (fewer than 2 search results)")
        return

    paths = [h.get("file", "") for h in hits[:4] if h.get("file")]
    if len(paths) < 2:
        print("  SKIP  (not enough file paths)")
        return

    print(f"  Reading {len(paths)} notes...")

    # Sequential baseline.
    t0 = time.monotonic()
    seq_results: dict[str, str] = {}
    for p in paths:
        try:
            seq_results[p] = read_note(p, vault=None)
        except ObsidianCLIError:
            seq_results[p] = ""
    seq_ms = int((time.monotonic() - t0) * 1000)

    # Batch read.
    t0 = time.monotonic()
    batch_results = batch_read_notes(paths, max_concurrent=4)
    batch_ms = int((time.monotonic() - t0) * 1000)

    check("batch returns correct count", len(batch_results) == len(paths))
    check("all paths present in batch", all(p in batch_results for p in paths))

    # Content should match (both should read the same notes).
    content_match = all(
        batch_results.get(p, "") == seq_results.get(p, "")
        for p in paths
    )
    check("batch content matches sequential", content_match)

    print(f"  Timing: sequential={seq_ms}ms, batch={batch_ms}ms")
    if batch_ms > 0 and seq_ms > 0:
        ratio = seq_ms / batch_ms
        print(f"  Speedup: {ratio:.2f}x")


def test_batch_nonexistent() -> None:
    print("\n--- batch_read_notes: nonexistent note ---")
    result = batch_read_notes(["zzz_does_not_exist_12345.md"])
    check("returns 1 entry", len(result) == 1)
    check("value is empty string for missing note",
          result.get("zzz_does_not_exist_12345.md", None) == "")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    test_batch_empty()
    test_batch_single()
    test_batch_multiple_and_benchmark()
    test_batch_nonexistent()

    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
