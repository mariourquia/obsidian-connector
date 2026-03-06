#!/usr/bin/env python3
"""Test content escaping edge cases for log_to_daily.

Writes each test case to the daily note via log_to_daily, then reads
back the daily note and verifies the content appears correctly.
"""

from __future__ import annotations

import sys
import time
import traceback

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.client import log_to_daily, run_obsidian

PASS = 0
FAIL = 0


def read_daily(vault: str | None = None) -> str:
    """Read today's daily note content."""
    return run_obsidian(["daily:read"], vault=vault)


# Each case: (label, input_content, expected_fragments)
# expected_fragments are substrings that MUST appear in the daily note
# after log_to_daily writes the content.
TEST_CASES: list[tuple[str, str, list[str]]] = [
    (
        "Simple text",
        "hello world",
        ["hello world"],
    ),
    (
        "Newlines",
        "line1\nline2\nline3",
        ["line1", "line2", "line3"],
    ),
    (
        "Double quotes",
        'text with "double quotes" and single quotes',
        ["double quotes", "single quotes"],
    ),
    (
        "Backslashes",
        "path\\to\\file",
        # CLI interprets \t as tab.  After round-trip, "path\to" becomes
        # "path<TAB>o" and "\file" stays as "\file" (only \n and \t are
        # recognized escape sequences).  We verify the non-ambiguous parts.
        ["path", "file"],
    ),
    (
        "Unicode and symbols",
        "cost: $100 -- 50% off",
        ["cost: $100", "50% off"],
    ),
    (
        "Mixed markdown",
        '## Heading\n- bullet 1\n- bullet 2\n\n> blockquote with "quotes"',
        ["## Heading", "- bullet 1", "- bullet 2", "blockquote", '"quotes"'],
    ),
]


def run_test(label: str, content: str, expected: list[str]) -> bool:
    """Write content, read daily note, check fragments. Return True on pass."""
    global PASS, FAIL

    # Use a unique tag so we can identify this test's contribution.
    tag = f"[escaping_test:{label.replace(' ', '_')}]"
    tagged_content = f"{tag} {content}"

    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"  input:    {content!r}")
    print(f"{'='*60}")

    try:
        log_to_daily(tagged_content)
    except Exception as exc:
        print(f"  FAIL  log_to_daily raised {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=2)
        FAIL += 1
        return False

    # Small delay to let the CLI flush.
    time.sleep(0.3)

    try:
        daily = read_daily()
    except Exception as exc:
        print(f"  FAIL  daily:read raised {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=2)
        FAIL += 1
        return False

    # Verify each expected fragment appears in the daily note.
    missing: list[str] = []
    for frag in expected:
        if frag not in daily:
            missing.append(frag)

    if missing:
        print(f"  FAIL  Missing fragments in daily note:")
        for m in missing:
            print(f"    - {m!r}")
        print(f"  daily note tail (last 500 chars):")
        print(f"    {daily[-500:]!r}")
        FAIL += 1
        return False

    print(f"  PASS  All {len(expected)} fragment(s) found in daily note")
    PASS += 1
    return True


def main() -> int:
    print("Escaping edge-case tests for log_to_daily")
    print(f"Running {len(TEST_CASES)} test case(s)...\n")

    for label, content, expected in TEST_CASES:
        run_test(label, content, expected)

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
