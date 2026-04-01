#!/usr/bin/env python3
"""Tests for reports.py and telemetry.py.

Uses tempfile for test directories and plain assertions.
No pytest dependency required.  Run with:

    python3 scripts/reports_test.py
"""

from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.reports import (
    ReportResult,
    ReportType,
    _format_date_range,
    _write_report,
    generate_report,
    monthly_review,
    project_status,
    vault_health,
    weekly_review,
)
from obsidian_connector.telemetry import (
    SessionTelemetry,
    TelemetryCollector,
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


def test(label: str, fn):
    """Run a single test function and track pass/fail."""
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    try:
        fn()
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        FAIL += 1


# ---------------------------------------------------------------------------
# Vault helpers
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


def _make_stale_file(vault: Path, rel_path: str, content: str) -> None:
    """Create a file and backdate its mtime to > 90 days ago."""
    full = vault / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    old_time = time.time() - (100 * 86400)  # 100 days ago
    os.utime(str(full), (old_time, old_time))


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------

def test_write_report_creates_dir():
    """_write_report creates Reports/ directory."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        vault.mkdir()
        path = _write_report(str(vault), "test-report.md", "# Test")
        check("Reports dir created", (vault / "Reports").is_dir())
        check("Report file exists", Path(path).is_file())
        check("Report content correct", Path(path).read_text() == "# Test")


def test_format_date_range():
    """_format_date_range produces human-readable ranges."""
    start = datetime(2026, 3, 23, tzinfo=timezone.utc)
    end = datetime(2026, 3, 30, tzinfo=timezone.utc)
    result = _format_date_range(start, end)
    check("date range format", result == "2026-03-23 to 2026-03-30")

    same = _format_date_range(start, start)
    check("same-day range", same == "2026-03-23")


def test_generate_report_creates_file():
    """generate_report creates file in Reports/ folder."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Note1.md": "# Hello\n\nSome content.",
            "Note2.md": "# World\n\n- [ ] Task open",
        })
        result = generate_report(str(vault), "weekly")
        check("result is ReportResult", isinstance(result, ReportResult))
        check("report file exists", Path(result.path).is_file())
        check("report in Reports/", "Reports/" in result.path or "Reports\\" in result.path)
        check("report_type is weekly", result.report_type == "weekly")
        check("generated_at is ISO", "T" in result.generated_at)


def test_report_filename_has_iso_date():
    """Report filename has ISO date prefix."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {"A.md": "content"})
        result = generate_report(str(vault), "weekly")
        filename = Path(result.path).name
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        check("filename starts with ISO date", filename.startswith(today))


def test_weekly_review_includes_note_counts():
    """weekly_review includes note counts."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "New1.md": "# New note\n\nCreated today.",
            "New2.md": "# Another\n\nAlso today.\n- [x] Done\n- [ ] Open",
        })
        result = weekly_review(str(vault))
        check("summary has notes_modified", "notes_modified" in result.summary)
        check("notes_modified >= 2", result.summary["notes_modified"] >= 2)
        check("summary has notes_created", "notes_created" in result.summary)
        check("summary has tasks_done", result.summary["tasks_done"] >= 1)
        check("summary has tasks_open", result.summary["tasks_open"] >= 1)


def test_vault_health_detects_orphans():
    """vault_health detects orphan notes."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Connected.md": "[[Other]]",
            "Other.md": "[[Connected]]",
            "Orphan.md": "No links at all.",
        })
        result = vault_health(str(vault))
        check("orphans count >= 1", result.summary["orphans"] >= 1)


def test_vault_health_detects_stale():
    """vault_health detects stale notes."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Recent.md": "# Recent\n\nFresh content.",
        })
        _make_stale_file(vault, "Old.md", "# Old\n\nStale content.")
        result = vault_health(str(vault))
        check("stale_notes >= 1", result.summary["stale_notes"] >= 1)


def test_vault_health_reports_coverage():
    """vault_health reports index coverage."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "A.md": "# A",
            "B.md": "# B",
            "C.md": "# C",
        })
        result = vault_health(str(vault))
        check("coverage_pct is present", "coverage_pct" in result.summary)
        check("coverage is 100%", result.summary["coverage_pct"] == 100.0)
        check("indexed_count == 3", result.summary["indexed_count"] == 3)
        check("total_files == 3", result.summary["total_files"] == 3)


def test_monthly_review():
    """monthly_review aggregates data."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Note.md": "# Note\n\n- [x] Done\n- [ ] Open",
        })
        result = monthly_review(str(vault))
        check("monthly report_type", result.report_type == "monthly")
        check("total_notes >= 1", result.summary["total_notes"] >= 1)


def test_project_status():
    """project_status reads from Project Tracking/ folder."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Project Tracking/AMOS.md": "# AMOS\n\n- [x] Setup\n- [ ] Build",
            "Project Tracking/Keiki.md": "# Keiki\n\n- [ ] Design",
        })
        result = project_status(str(vault))
        check("project_count == 2", result.summary["project_count"] == 2)


# ---------------------------------------------------------------------------
# Telemetry tests
# ---------------------------------------------------------------------------

def test_start_session_initializes_counters():
    """start_session initializes counters to 0."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TelemetryCollector(storage_dir=tmp)
        tc.start_session()
        s = tc.session_summary()
        check("notes_read starts at 0", s["notes_read"] == 0)
        check("notes_written starts at 0", s["notes_written"] == 0)
        check("tools_called starts empty", s["tools_called"] == {})
        check("errors starts at 0", s["errors"] == 0)


def test_record_read():
    """record_read increments counter."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TelemetryCollector(storage_dir=tmp)
        tc.start_session()
        tc.record_read()
        tc.record_read()
        check("notes_read == 2", tc.session_summary()["notes_read"] == 2)


def test_record_write():
    """record_write increments counter."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TelemetryCollector(storage_dir=tmp)
        tc.start_session()
        tc.record_write()
        check("notes_written == 1", tc.session_summary()["notes_written"] == 1)


def test_record_tool():
    """record_tool tracks per-tool counts."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TelemetryCollector(storage_dir=tmp)
        tc.start_session()
        tc.record_tool("search")
        tc.record_tool("search")
        tc.record_tool("read")
        s = tc.session_summary()
        check("search called 2x", s["tools_called"]["search"] == 2)
        check("read called 1x", s["tools_called"]["read"] == 1)


def test_end_session_writes_jsonl():
    """end_session writes JSONL file."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TelemetryCollector(storage_dir=tmp)
        tc.start_session()
        tc.record_read()
        tc.record_write()
        tc.record_error()
        result = tc.end_session()

        check("end_session returns path", result is not None)
        check("JSONL file exists", result.is_file())
        check("file ends with .jsonl", result.suffix == ".jsonl")

        content = result.read_text().strip()
        record = json.loads(content)
        check("record has session_start", "session_start" in record)
        check("record has session_end", "session_end" in record)
        check("record notes_read == 1", record["notes_read"] == 1)
        check("record notes_written == 1", record["notes_written"] == 1)
        check("record errors == 1", record["errors"] == 1)


def test_session_summary():
    """session_summary returns correct dict."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TelemetryCollector(storage_dir=tmp)
        # No session active.
        check("empty summary before start", tc.session_summary() == {})

        tc.start_session()
        tc.record_read()
        tc.record_retrieval_miss()
        tc.record_write_risk()
        s = tc.session_summary()
        check("retrieval_misses == 1", s["retrieval_misses"] == 1)
        check("write_risk_events == 1", s["write_risk_events"] == 1)


def test_weekly_summary():
    """weekly_summary aggregates multiple sessions."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TelemetryCollector(storage_dir=tmp)

        # Session 1.
        tc.start_session()
        tc.record_read()
        tc.record_read()
        tc.record_tool("search")
        tc.end_session()

        # Session 2.
        tc.start_session()
        tc.record_read()
        tc.record_write()
        tc.record_tool("search")
        tc.record_tool("write")
        tc.end_session()

        summary = tc.weekly_summary()
        check("total sessions == 2", summary["sessions"] == 2)
        check("total notes_read == 3", summary["notes_read"] == 3)
        check("total notes_written == 1", summary["notes_written"] == 1)
        check("tool search == 2", summary["tools_called"].get("search") == 2)
        check("tool write == 1", summary["tools_called"].get("write") == 1)


def test_rotate_deletes_old_files():
    """rotate deletes old files."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TelemetryCollector(storage_dir=tmp)

        # Create an old file (> 30 days).
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")
        old_file = Path(tmp) / f"{old_date}.jsonl"
        old_file.write_text('{"notes_read":1}\n')

        # Create a recent file.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        recent_file = Path(tmp) / f"{today}.jsonl"
        recent_file.write_text('{"notes_read":2}\n')

        deleted = tc.rotate(max_age_days=30)
        check("old file deleted", not old_file.exists())
        check("deleted count == 1", deleted == 1)


def test_rotate_keeps_recent_files():
    """rotate keeps recent files."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TelemetryCollector(storage_dir=tmp)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        recent_file = Path(tmp) / f"{today}.jsonl"
        recent_file.write_text('{"notes_read":1}\n')

        deleted = tc.rotate(max_age_days=30)
        check("recent file kept", recent_file.exists())
        check("nothing deleted", deleted == 0)


def test_no_network_imports():
    """Verify telemetry.py has no network-related imports."""
    telemetry_path = (
        Path(__file__).resolve().parent.parent
        / "obsidian_connector"
        / "telemetry.py"
    )
    source = telemetry_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    banned = {"urllib", "socket", "requests", "http", "http.client", "httplib"}
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in banned:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in banned:
                found.append(node.module)

    check(
        f"no network imports (found: {found})",
        len(found) == 0,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # Reports tests.
    test("_write_report creates Reports/ directory", test_write_report_creates_dir)
    test("_format_date_range", test_format_date_range)
    test("generate_report creates file", test_generate_report_creates_file)
    test("report filename has ISO date prefix", test_report_filename_has_iso_date)
    test("weekly_review includes note counts", test_weekly_review_includes_note_counts)
    test("vault_health detects orphan notes", test_vault_health_detects_orphans)
    test("vault_health detects stale notes", test_vault_health_detects_stale)
    test("vault_health reports index coverage", test_vault_health_reports_coverage)
    test("monthly_review aggregates", test_monthly_review)
    test("project_status reads projects", test_project_status)

    # Telemetry tests.
    test("start_session initializes counters to 0", test_start_session_initializes_counters)
    test("record_read increments counter", test_record_read)
    test("record_write increments counter", test_record_write)
    test("record_tool tracks per-tool counts", test_record_tool)
    test("end_session writes JSONL file", test_end_session_writes_jsonl)
    test("session_summary returns correct dict", test_session_summary)
    test("weekly_summary aggregates multiple sessions", test_weekly_summary)
    test("rotate deletes old files", test_rotate_deletes_old_files)
    test("rotate keeps recent files", test_rotate_keeps_recent_files)
    test("no network imports in telemetry", test_no_network_imports)

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
