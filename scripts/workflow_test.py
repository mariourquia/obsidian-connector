#!/usr/bin/env python3
"""Workflow smoke tests -- exercise higher-level functions."""

from __future__ import annotations

import json
import sys
import traceback

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.workflows import (
    find_prior_work,
    log_decision,
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
        if isinstance(result, list):
            print(f"  count: {len(result)}")
            for item in result:
                print(json.dumps(item, indent=4))
        elif isinstance(result, str):
            print(f"  value: {result!r}")
        elif result is None:
            print("  (returned None)")
        PASS += 1
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        FAIL += 1


def main() -> int:
    # 1. log_decision
    smoke(
        "log_decision (dummy project)",
        log_decision,
        project="obsidian-connector",
        summary="Chose subprocess list-args over shell strings for safety.",
        details="Passing args as a list to subprocess.run avoids shell injection.\nThis is the standard pattern for any CLI wrapper.",
    )

    # 2. find_prior_work -- use a topic likely to hit note content
    smoke(
        "find_prior_work('learning')",
        find_prior_work,
        "learning",
        top_n=3,
    )

    # 3. find_prior_work -- no results expected
    smoke(
        "find_prior_work('zzz_no_match_xyz_99999')",
        find_prior_work,
        "zzz_no_match_xyz_99999",
        top_n=3,
    )

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
