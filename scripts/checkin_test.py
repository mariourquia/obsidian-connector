#!/usr/bin/env python3
"""check_in workflow tests."""

from __future__ import annotations

import sys
import traceback

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.workflows import check_in

PASS = 0
FAIL = 0


def assert_eq(label, actual, expected):
    global PASS, FAIL
    if actual == expected:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}: expected {expected!r}, got {actual!r}")
        FAIL += 1


def assert_in(label, value, container):
    global PASS, FAIL
    if value in container:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}: {value!r} not in {container!r}")
        FAIL += 1


def assert_type(label, value, expected_type):
    global PASS, FAIL
    if isinstance(value, expected_type):
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}: expected {expected_type.__name__}, got {type(value).__name__}")
        FAIL += 1


def main() -> int:
    print("=" * 60)
    print("TEST: check_in returns structured result")
    print("=" * 60)

    try:
        result = check_in()
    except Exception as exc:
        print(f"  FAIL  check_in() raised {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        return 1

    # Structure checks
    assert_type("result is dict", result, dict)
    assert_in("has time_of_day", "time_of_day", result)
    assert_in("time_of_day valid", result.get("time_of_day"), ["morning", "midday", "evening", "night"])
    assert_in("has daily_note_exists", "daily_note_exists", result)
    assert_type("daily_note_exists is bool", result.get("daily_note_exists"), bool)
    assert_in("has completed_rituals", "completed_rituals", result)
    assert_type("completed_rituals is list", result.get("completed_rituals"), list)
    assert_in("has pending_rituals", "pending_rituals", result)
    assert_type("pending_rituals is list", result.get("pending_rituals"), list)
    assert_in("has pending_delegations", "pending_delegations", result)
    assert_type("pending_delegations is int", result.get("pending_delegations"), int)
    assert_in("has unreviewed_drafts", "unreviewed_drafts", result)
    assert_type("unreviewed_drafts is int", result.get("unreviewed_drafts"), int)
    assert_in("has open_loop_count", "open_loop_count", result)
    assert_type("open_loop_count is int", result.get("open_loop_count"), int)
    assert_in("has suggestion", "suggestion", result)
    assert_type("suggestion is str", result.get("suggestion"), str)

    # Ritual logic: completed + pending should cover both rituals
    all_rituals = set(result["completed_rituals"] + result["pending_rituals"])
    assert_eq("morning_briefing accounted for", "morning_briefing" in all_rituals, True)
    assert_eq("evening_close accounted for", "evening_close" in all_rituals, True)

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
