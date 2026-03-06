#!/usr/bin/env python3
"""Validate the audit log module."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.audit import log_action

PASS = 0
FAIL = 0
REQUIRED_KEYS = {"timestamp", "command", "args", "vault", "dry_run", "affected_path", "content_hash"}
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
TEST_CMD = "__audit_test__"


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}")
        FAIL += 1


def main() -> int:
    # -- Test 1: log without content -----------------------------------------
    print("\n--- log_action without content ---")
    log_path = log_action(
        command=TEST_CMD,
        args={"query": "test", "limit": 5},
        vault="TestVault",
        dry_run=True,
        affected_path="/notes/test.md",
    )
    check("log file exists", log_path.exists())

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    last_line = lines[-1]
    try:
        record = json.loads(last_line)
        valid_json = True
    except json.JSONDecodeError:
        record = {}
        valid_json = False

    check("last line is valid JSON", valid_json)
    check("required keys present", REQUIRED_KEYS.issubset(record.keys()))
    check("command matches", record.get("command") == TEST_CMD)
    check("content_hash is null (no content)", record.get("content_hash") is None)

    # -- Test 2: log with content ---------------------------------------------
    print("\n--- log_action with content ---")
    log_path_2 = log_action(
        command=TEST_CMD,
        args={"action": "write"},
        vault="TestVault",
        content="Hello, audit log!",
    )
    check("same log file path", log_path_2 == log_path)

    lines_2 = log_path_2.read_text(encoding="utf-8").strip().splitlines()
    last_line_2 = lines_2[-1]
    record_2 = json.loads(last_line_2)

    content_hash = record_2.get("content_hash", "")
    check("content_hash is valid 64-char hex", bool(HEX_RE.match(str(content_hash))))
    check("content_hash is correct SHA-256", content_hash == "292efb0bfa42e56ae2d06cc6dd8dac5c896afbae4b9f9f1c0d9629be4094b080")

    # -- Test 3: return type --------------------------------------------------
    print("\n--- return value ---")
    check("return type is Path", isinstance(log_path, Path))
    check("filename ends with .jsonl", log_path.suffix == ".jsonl")

    # -- Summary --------------------------------------------------------------
    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
