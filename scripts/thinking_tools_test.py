#!/usr/bin/env python3
"""Thinking Tools smoke tests -- exercise the three thinking tool functions."""

from __future__ import annotations

import json
import sys
import traceback

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.workflows import (
    challenge_belief,
    connect_domains,
    emerge_ideas,
)

PASS = 0
FAIL = 0


def smoke(label: str, fn, *args, expected_type=None, expected_keys=None, **kwargs):
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

            # Key check
            if expected_keys is not None:
                missing = set(expected_keys) - set(result.keys())
                if missing:
                    print(f"  FAIL  missing keys: {missing}")
                    FAIL += 1
                    return

            print(json.dumps(result, indent=4, default=str)[:800])
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
    # 1. challenge_belief
    smoke(
        "challenge_belief('note-taking improves memory')",
        challenge_belief,
        "note-taking improves memory",
        expected_type=dict,
        expected_keys=["belief", "counter_evidence", "supporting_evidence", "verdict"],
    )

    # 2. emerge_ideas
    smoke(
        "emerge_ideas('project')",
        emerge_ideas,
        "project",
        expected_type=dict,
        expected_keys=["topic", "total_notes", "clusters"],
    )

    # 3. connect_domains
    smoke(
        "connect_domains('health', 'work')",
        connect_domains,
        "health",
        "work",
        expected_type=dict,
        expected_keys=["domain_a", "domain_b", "connections", "domain_a_only", "domain_b_only"],
    )

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
