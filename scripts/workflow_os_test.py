#!/usr/bin/env python3
"""Workflow OS smoke tests -- exercise the new Workflow OS functions."""

from __future__ import annotations

import json
import sys
import traceback

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.workflows import (
    close_day_reflection,
    list_open_loops,
    my_world_snapshot,
    today_brief,
)

PASS = 0
FAIL = 0


def smoke(label: str, fn, *args, expected_type=None, **kwargs):
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    try:
        result = fn(*args, **kwargs)
        print(f"  OK  type={type(result).__name__}")

        # Type check
        if expected_type is not None and not isinstance(result, expected_type):
            print(f"  FAIL  expected {expected_type.__name__}, got {type(result).__name__}")
            FAIL += 1
            return

        if isinstance(result, dict):
            print(f"  keys: {list(result.keys())}")
            print(json.dumps(result, indent=4, default=str)[:600])
        elif isinstance(result, list):
            print(f"  count: {len(result)}")
            if result:
                print(f"  first: {json.dumps(result[0], indent=4, default=str)[:200]}")
        elif result is None:
            print("  (returned None)")

        PASS += 1
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        FAIL += 1


def main() -> int:
    # 1. list_open_loops
    smoke(
        "list_open_loops()",
        list_open_loops,
        expected_type=list,
    )

    # 2. my_world_snapshot
    smoke(
        "my_world_snapshot(lookback_days=3)",
        my_world_snapshot,
        lookback_days=3,
        expected_type=dict,
    )

    # 3. today_brief
    smoke(
        "today_brief()",
        today_brief,
        expected_type=dict,
    )

    # 4. close_day_reflection
    smoke(
        "close_day_reflection()",
        close_day_reflection,
        expected_type=dict,
    )

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
