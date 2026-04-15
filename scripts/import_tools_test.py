#!/usr/bin/env python3
"""Coverage-driving smoke tests for obsidian_connector.import_tools (Task 43).

The `tests/test_import_tools.py` pytest suite has the deep coverage. This
script is a CI-runnable shim so the legacy `coverage run --append
scripts/*_test.py` pipeline picks the module up. Mirrors the style of
the existing `scripts/<module>_test.py` files: prints `PASS` / `FAIL`
lines and exits non-zero on the first failure.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Repo root on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.import_tools import (  # noqa: E402
    DEFAULT_MAX_FILES,
    IDEMPOTENCY_KEY_PREFIX,
    INGEST_TEXT_PATH,
    FileCandidate,
    ImportPlan,
    ImportResult,
    classify_candidate,
    default_report_path,
    execute_import,
    plan_import,
    plan_to_dict,
    result_to_dict,
    scan_markdown_files,
    write_import_report,
)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS: {label}")
    else:
        FAIL += 1
        print(f"FAIL: {label}")


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_scan_returns_sorted_candidates() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root / "z.md", "# Z\nzeta")
        _write(root / "a.md", "# A\nalpha")
        _write(root / "sub" / "m.md", "# M\nmiddle")
        rels = [fc.relative_path for fc in scan_markdown_files(root)]
        check("scan returns sorted paths", rels == ["a.md", "sub/m.md", "z.md"])


def test_scan_glob_filters() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root / "Inbox" / "a.md", "in")
        _write(root / "Archive" / "b.md", "ar")
        rels = [
            fc.relative_path
            for fc in scan_markdown_files(root, exclude_globs=["Archive/*"])
        ]
        check("exclude_globs drops paths", rels == ["Inbox/a.md"])


def test_classifier_branches() -> None:
    def _fc(rel="Inbox/n.md", size=500, fm=None, body="body") -> FileCandidate:
        return FileCandidate(
            path=Path("/tmp/x") / rel,
            relative_path=rel,
            size_bytes=size,
            modified_at="2026-04-14T12:00:00+00:00",
            title_guess="t",
            content_sha256="a" * 64,
            has_frontmatter=bool(fm),
            frontmatter_dict=dict(fm or {}),
            body_preview=body,
        )

    check(
        "frontmatter type=commitment is managed",
        classify_candidate(_fc(fm={"type": "commitment"}))["classification"]
        == "already_managed",
    )
    check(
        "frontmatter type=entity is managed",
        classify_candidate(_fc(fm={"type": "entity"}))["classification"]
        == "already_managed",
    )
    check(
        "Commitments/ path is managed",
        classify_candidate(_fc(rel="Commitments/Open/a.md"))["classification"]
        == "already_managed",
    )
    check(
        "Entities/ path is managed",
        classify_candidate(_fc(rel="Entities/Person/x.md"))["classification"]
        == "already_managed",
    )
    check(
        "Dashboards/ path is managed",
        classify_candidate(_fc(rel="Dashboards/d.md"))["classification"]
        == "already_managed",
    )
    check(
        "Analytics/ path is managed",
        classify_candidate(_fc(rel="Analytics/x.md"))["classification"]
        == "already_managed",
    )
    check(
        "Archive/ path is managed",
        classify_candidate(_fc(rel="Archive/x.md"))["classification"]
        == "already_managed",
    )
    capture_v = classify_candidate(_fc(body="text #capture"))
    check(
        "#capture body tag -> ready (high)",
        capture_v["classification"] == "ready_capture"
        and capture_v["confidence"] == "high",
    )
    fm_capture = classify_candidate(_fc(fm={"tags": ["capture"]}))
    check(
        "#capture frontmatter tag -> ready (high)",
        fm_capture["classification"] == "ready_capture",
    )
    idea = classify_candidate(_fc(body="text #idea"))
    check(
        "#idea -> ready (low)",
        idea["classification"] == "ready_capture" and idea["confidence"] == "low",
    )
    check(
        "#todo -> ready (low)",
        classify_candidate(_fc(body="x #todo"))["confidence"] == "low",
    )
    check(
        "#action -> ready (low)",
        classify_candidate(_fc(body="x #action"))["confidence"] == "low",
    )
    small = classify_candidate(_fc(size=100, body="small"))
    check("small file no tags -> unknown", small["classification"] == "unknown")
    check(
        "regular note no tags -> unknown",
        classify_candidate(_fc(body="just prose"))["classification"] == "unknown",
    )
    fence = classify_candidate(
        _fc(body="ok\n```\n#capture\n```\nmore prose")
    )
    check(
        "tag inside code fence is ignored",
        fence["classification"] == "unknown",
    )


def test_plan_import_buckets() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root / "Inbox" / "ready.md", "#capture body " * 10)
        _write(root / "Commitments" / "x.md", "managed body " * 10)
        _write(root / "Inbox" / "tiny.md", "x")
        _write(root / "Inbox" / "note.md", "regular prose " * 30)
        plan = plan_import(root)
        rels_capture = [
            p.candidate.relative_path for p in plan.to_import_as_capture
        ]
        check(
            "plan buckets: ready_capture",
            "Inbox/ready.md" in rels_capture,
        )
        check(
            "plan buckets: already_managed",
            any(
                fc.relative_path == "Commitments/x.md"
                for fc in plan.to_skip_already_managed
            ),
        )
        check(
            "plan buckets: size_out_of_range",
            any(
                fc.relative_path == "Inbox/tiny.md"
                for fc in plan.to_skip_size_out_of_range
            ),
        )
        check(
            "plan buckets: unknown_kind",
            any(
                fc.relative_path == "Inbox/note.md"
                for fc in plan.to_skip_unknown_kind
            ),
        )
        # Idempotency key shape.
        key = plan.to_import_as_capture[0].idempotency_key
        check(
            "idempotency key prefix",
            key.startswith(IDEMPOTENCY_KEY_PREFIX),
        )
        check(
            "idempotency key length",
            len(key) == len(IDEMPOTENCY_KEY_PREFIX) + 16,
        )


def test_plan_import_max_files_overflow() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for i in range(5):
            _write(root / f"n{i}.md", f"body {i}")
        try:
            plan_import(root, max_files=3)
        except ValueError as exc:
            check("max_files overflow refused", "max_files" in str(exc))
        else:
            check("max_files overflow refused", False)


def test_plan_to_dict_is_serializable() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root / "a.md", "#capture body " * 10)
        plan = plan_import(root)
        d = plan_to_dict(plan)
        check(
            "plan_to_dict json round-trip",
            json.loads(json.dumps(d))["total_scanned"] == 1,
        )


def test_execute_import_default_dry_run() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root / "a.md", "#capture body " * 10)
        plan = plan_import(root)
        result = execute_import(plan)
        check("execute_import default dry-run", result.dry_run is True)
        check("execute_import dry-run posts nothing", result.posted == ())


def test_execute_import_half_confirmed_still_dry_run() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root / "a.md", "#capture body " * 10)
        plan = plan_import(root)
        r1 = execute_import(plan, confirm=True)  # missing dry_run=False
        r2 = execute_import(plan, dry_run=False, confirm=False)
        check("confirm alone is still dry-run", r1.dry_run is True)
        check("dry_run=False alone is still dry-run", r2.dry_run is True)


def test_default_report_path_layout() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        p = default_report_path(
            root, timestamp="2026-04-14T12:00:00+00:00"
        )
        check(
            "default report under Analytics/Import",
            p.parent.name == "Import" and p.parent.parent.name == "Analytics",
        )
        check("colon sanitized in path", ":" not in p.name)


def test_write_import_report_renders_markdown() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root / "a.md", "#capture body " * 10)
        plan = plan_import(root)
        result = execute_import(plan)
        target = default_report_path(root, timestamp="2026-04-14T12-00-00+00-00")
        written = write_import_report(result, target, vault_root=root)
        body = written.read_text(encoding="utf-8")
        check("report exists", written.exists())
        check("report frontmatter present", "type: import-report" in body)
        check("report says dry-run", "dry-run" in body)


def test_result_to_dict_is_serializable() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write(root / "a.md", "#capture body " * 10)
        plan = plan_import(root)
        result = execute_import(plan)
        d = result_to_dict(result)
        check(
            "result_to_dict json round-trip",
            json.loads(json.dumps(d))["dry_run"] is True,
        )


def test_constants_exist() -> None:
    check("DEFAULT_MAX_FILES is positive", DEFAULT_MAX_FILES > 0)
    check("INGEST_TEXT_PATH is the v1 path", INGEST_TEXT_PATH == "/api/v1/ingest/text")


def main() -> int:
    test_scan_returns_sorted_candidates()
    test_scan_glob_filters()
    test_classifier_branches()
    test_plan_import_buckets()
    test_plan_import_max_files_overflow()
    test_plan_to_dict_is_serializable()
    test_execute_import_default_dry_run()
    test_execute_import_half_confirmed_still_dry_run()
    test_default_report_path_layout()
    test_write_import_report_renders_markdown()
    test_result_to_dict_is_serializable()
    test_constants_exist()
    print(f"\nimport_tools_test: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
