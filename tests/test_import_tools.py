"""Tests for Task 43 connector-side import tools.

Covers :mod:`obsidian_connector.import_tools` (scan, classify, plan,
execute, report) plus the MCP and CLI surfaces that wrap it. HTTP is
mocked at the ``http.client`` layer so no real traffic is issued.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from obsidian_connector import import_tools
from obsidian_connector.import_tools import (
    DEFAULT_MAX_FILES,
    DEFAULT_SOURCE_APP,
    IDEMPOTENCY_KEY_PREFIX,
    INGEST_TEXT_PATH,
    FileCandidate,
    ImportPlan,
    ImportResult,
    PlannedImport,
    classify_candidate,
    default_report_path,
    execute_import,
    plan_import,
    plan_to_dict,
    result_to_dict,
    scan_markdown_files,
    write_import_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class _FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body


class _FakeConnection:
    def __init__(self, netloc: str, *, timeout: float = 10.0, **_: object) -> None:
        self.netloc = netloc
        self.timeout = timeout
        self.requests: list[dict[str, object]] = []
        self.response_status = 200
        self.response_body = "{}"

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.requests.append({
            "method": method,
            "path": path,
            "body": body,
            "headers": dict(headers or {}),
        })

    def getresponse(self) -> _FakeResponse:
        return _FakeResponse(self.response_status, self.response_body)

    def close(self) -> None:  # pragma: no cover
        pass


def _install_fake_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: int = 200,
    body: dict | None = None,
) -> list[_FakeConnection]:
    made: list[_FakeConnection] = []
    payload = json.dumps(body if body is not None else {})

    def _factory(netloc: str, **kwargs: object) -> _FakeConnection:
        conn = _FakeConnection(netloc, **kwargs)
        conn.response_status = status
        conn.response_body = payload
        made.append(conn)
        return conn

    import http.client as hc

    monkeypatch.setattr(hc, "HTTPConnection", _factory)
    monkeypatch.setattr(hc, "HTTPSConnection", _factory)
    return made


def _install_fake_http_sequence(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[tuple[int, dict]],
) -> list[_FakeConnection]:
    """Install a fake that returns a different (status, body) per request."""
    made: list[_FakeConnection] = []
    idx = {"i": 0}

    def _factory(netloc: str, **kwargs: object) -> _FakeConnection:
        conn = _FakeConnection(netloc, **kwargs)
        i = idx["i"]
        status, body = responses[min(i, len(responses) - 1)]
        conn.response_status = status
        conn.response_body = json.dumps(body)
        idx["i"] = i + 1
        made.append(conn)
        return conn

    import http.client as hc

    monkeypatch.setattr(hc, "HTTPConnection", _factory)
    monkeypatch.setattr(hc, "HTTPSConnection", _factory)
    return made


# ---------------------------------------------------------------------------
# scan_markdown_files
# ---------------------------------------------------------------------------


def test_scan_returns_files_in_sorted_order(tmp_path: Path) -> None:
    _write(tmp_path / "z.md", "# Z\nzeta")
    _write(tmp_path / "a.md", "# A\nalpha")
    _write(tmp_path / "sub" / "m.md", "# M\nmiddle")
    rels = [fc.relative_path for fc in scan_markdown_files(tmp_path)]
    assert rels == sorted(rels)
    assert rels == ["a.md", "sub/m.md", "z.md"]


def test_scan_skips_non_markdown_files(tmp_path: Path) -> None:
    _write(tmp_path / "note.md", "hello")
    _write(tmp_path / "image.png", "binary")
    _write(tmp_path / "data.json", "{}")
    rels = [fc.relative_path for fc in scan_markdown_files(tmp_path)]
    assert rels == ["note.md"]


def test_scan_returns_nothing_for_missing_root(tmp_path: Path) -> None:
    rels = list(scan_markdown_files(tmp_path / "does-not-exist"))
    assert rels == []


def test_scan_returns_nothing_for_file_root(tmp_path: Path) -> None:
    f = _write(tmp_path / "x.md", "hello")
    rels = list(scan_markdown_files(f))
    assert rels == []


def test_scan_exclude_globs_drop_paths(tmp_path: Path) -> None:
    _write(tmp_path / "Inbox" / "a.md", "in")
    _write(tmp_path / "Archive" / "b.md", "ar")
    rels = [
        fc.relative_path
        for fc in scan_markdown_files(tmp_path, exclude_globs=["Archive/*"])
    ]
    assert rels == ["Inbox/a.md"]


def test_scan_include_globs_whitelist_paths(tmp_path: Path) -> None:
    _write(tmp_path / "Inbox" / "a.md", "in")
    _write(tmp_path / "Other" / "b.md", "ot")
    rels = [
        fc.relative_path
        for fc in scan_markdown_files(tmp_path, include_globs=["Inbox/*"])
    ]
    assert rels == ["Inbox/a.md"]


def test_scan_max_files_caps_iteration(tmp_path: Path) -> None:
    for i in range(5):
        _write(tmp_path / f"n{i}.md", f"body {i}")
    rels = list(scan_markdown_files(tmp_path, max_files=3))
    assert len(rels) == 3


def test_scan_extracts_frontmatter_dict(tmp_path: Path) -> None:
    body = """---
title: Hello
type: note
tags: [foo, bar]
---

# Hello
World here.
"""
    _write(tmp_path / "h.md", body)
    fcs = list(scan_markdown_files(tmp_path))
    assert len(fcs) == 1
    fc = fcs[0]
    assert fc.has_frontmatter is True
    assert fc.frontmatter_dict.get("title") == "Hello"
    assert fc.frontmatter_dict.get("type") == "note"
    assert fc.frontmatter_dict.get("tags") == ["foo", "bar"]
    assert fc.title_guess == "Hello"


def test_scan_handles_no_frontmatter(tmp_path: Path) -> None:
    _write(tmp_path / "plain.md", "# Header\n\nbody text")
    fcs = list(scan_markdown_files(tmp_path))
    assert fcs[0].has_frontmatter is False
    assert fcs[0].title_guess == "Header"


def test_scan_content_sha256_is_full_hex(tmp_path: Path) -> None:
    _write(tmp_path / "n.md", "hello\n")
    fcs = list(scan_markdown_files(tmp_path))
    assert len(fcs[0].content_sha256) == 64
    # Same input -> same hash on re-run.
    fcs2 = list(scan_markdown_files(tmp_path))
    assert fcs[0].content_sha256 == fcs2[0].content_sha256


# ---------------------------------------------------------------------------
# classify_candidate (every branch)
# ---------------------------------------------------------------------------


def _candidate(
    *,
    rel: str = "Inbox/n.md",
    size: int = 500,
    fm: dict | None = None,
    body: str = "body content",
    title: str = "n",
) -> FileCandidate:
    return FileCandidate(
        path=Path("/tmp/fake") / rel,
        relative_path=rel,
        size_bytes=size,
        modified_at="2026-04-14T12:00:00+00:00",
        title_guess=title,
        content_sha256="a" * 64,
        has_frontmatter=bool(fm),
        frontmatter_dict=dict(fm or {}),
        body_preview=body,
    )


def test_classify_frontmatter_type_commitment_is_managed() -> None:
    fc = _candidate(fm={"type": "commitment"})
    assert classify_candidate(fc)["classification"] == "already_managed"


def test_classify_frontmatter_type_entity_is_managed() -> None:
    fc = _candidate(fm={"type": "entity"})
    assert classify_candidate(fc)["classification"] == "already_managed"


def test_classify_path_under_commitments_is_managed() -> None:
    fc = _candidate(rel="Commitments/Open/foo.md")
    assert classify_candidate(fc)["classification"] == "already_managed"


def test_classify_path_under_entities_is_managed() -> None:
    fc = _candidate(rel="Entities/Person/alice.md")
    assert classify_candidate(fc)["classification"] == "already_managed"


def test_classify_path_under_dashboards_is_managed() -> None:
    fc = _candidate(rel="Dashboards/Daily.md")
    assert classify_candidate(fc)["classification"] == "already_managed"


def test_classify_path_under_analytics_is_managed() -> None:
    fc = _candidate(rel="Analytics/Weekly/2026/2026-W15.md")
    assert classify_candidate(fc)["classification"] == "already_managed"


def test_classify_path_under_archive_is_managed() -> None:
    fc = _candidate(rel="Archive/old.md")
    assert classify_candidate(fc)["classification"] == "already_managed"


def test_classify_capture_tag_in_body_is_ready_high() -> None:
    fc = _candidate(body="Some content with #capture tag.")
    verdict = classify_candidate(fc)
    assert verdict["classification"] == "ready_capture"
    assert verdict["confidence"] == "high"


def test_classify_capture_tag_in_frontmatter_is_ready_high() -> None:
    fc = _candidate(fm={"tags": ["capture"]})
    verdict = classify_candidate(fc)
    assert verdict["classification"] == "ready_capture"
    assert verdict["confidence"] == "high"


def test_classify_idea_tag_is_ready_low() -> None:
    fc = _candidate(body="thoughts here #idea")
    verdict = classify_candidate(fc)
    assert verdict["classification"] == "ready_capture"
    assert verdict["confidence"] == "low"


def test_classify_todo_tag_is_ready_low() -> None:
    fc = _candidate(body="thing #todo")
    verdict = classify_candidate(fc)
    assert verdict["classification"] == "ready_capture"
    assert verdict["confidence"] == "low"


def test_classify_action_tag_is_ready_low() -> None:
    fc = _candidate(body="do this #action")
    verdict = classify_candidate(fc)
    assert verdict["classification"] == "ready_capture"
    assert verdict["confidence"] == "low"


def test_classify_small_file_no_tags_is_unknown() -> None:
    fc = _candidate(size=200, body="tiny note", fm={})
    verdict = classify_candidate(fc)
    assert verdict["classification"] == "unknown"
    assert "small" in verdict["reason"]


def test_classify_normal_file_no_tags_is_unknown() -> None:
    fc = _candidate(size=500, body="just prose, nothing actionable")
    verdict = classify_candidate(fc)
    assert verdict["classification"] == "unknown"


def test_classify_capture_tag_inside_code_fence_is_ignored() -> None:
    body = "regular text\n```\n#capture\n```\nmore prose"
    fc = _candidate(body=body)
    verdict = classify_candidate(fc)
    assert verdict["classification"] == "unknown"


# ---------------------------------------------------------------------------
# plan_import (buckets, warnings, max_files cap)
# ---------------------------------------------------------------------------


def test_plan_import_buckets_correctly(tmp_path: Path) -> None:
    _write(
        tmp_path / "Inbox" / "ready.md",
        "# Ready\n\nbody #capture text " * 10,
    )
    _write(
        tmp_path / "Commitments" / "Open" / "x.md",
        "# Done already\n\nfrom service",
    )
    _write(tmp_path / "Inbox" / "tiny.md", "x")  # size out of range
    _write(tmp_path / "Inbox" / "note.md", "regular prose " * 30)  # unknown
    plan = plan_import(tmp_path, min_size=10, max_size=100_000)
    rels_capture = [p.candidate.relative_path for p in plan.to_import_as_capture]
    rels_managed = [fc.relative_path for fc in plan.to_skip_already_managed]
    rels_size = [fc.relative_path for fc in plan.to_skip_size_out_of_range]
    rels_unknown = [fc.relative_path for fc in plan.to_skip_unknown_kind]
    assert "Inbox/ready.md" in rels_capture
    assert "Commitments/Open/x.md" in rels_managed
    assert "Inbox/tiny.md" in rels_size
    assert "Inbox/note.md" in rels_unknown


def test_plan_import_size_filter_overrides_classification(tmp_path: Path) -> None:
    # Even though it has #capture, the file is too small.
    _write(tmp_path / "tiny.md", "#capture")  # 8 bytes
    plan = plan_import(tmp_path, min_size=20, max_size=100_000)
    assert len(plan.to_import_as_capture) == 0
    assert len(plan.to_skip_size_out_of_range) == 1


def test_plan_import_max_size_filter(tmp_path: Path) -> None:
    big = "x" * 5000
    _write(tmp_path / "big.md", "#capture\n" + big)
    plan = plan_import(tmp_path, min_size=10, max_size=1000)
    assert len(plan.to_import_as_capture) == 0
    assert len(plan.to_skip_size_out_of_range) == 1


def test_plan_import_emits_idempotency_keys_with_prefix(tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "# A\n\nbody #capture " * 5)
    plan = plan_import(tmp_path)
    assert len(plan.to_import_as_capture) == 1
    key = plan.to_import_as_capture[0].idempotency_key
    assert key.startswith(IDEMPOTENCY_KEY_PREFIX)
    # 16-char hex suffix.
    assert len(key) == len(IDEMPOTENCY_KEY_PREFIX) + 16


def test_plan_import_warns_on_duplicate_content_hash(tmp_path: Path) -> None:
    body = "shared body #capture " * 10
    _write(tmp_path / "a.md", body)
    _write(tmp_path / "b.md", body)
    plan = plan_import(tmp_path)
    assert len(plan.to_import_as_capture) == 2
    assert len(plan.warnings) == 1
    assert "duplicate content_sha256" in plan.warnings[0]


def test_plan_import_refuses_on_max_files_overflow(tmp_path: Path) -> None:
    for i in range(6):
        _write(tmp_path / f"n{i}.md", f"body #capture {i} " * 5)
    with pytest.raises(ValueError, match="max_files"):
        plan_import(tmp_path, max_files=5)


def test_plan_import_refuses_for_missing_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        plan_import(tmp_path / "missing")


def test_plan_import_refuses_for_invalid_max_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        plan_import(tmp_path, max_files=0)


def test_plan_import_returns_frozen_dataclass(tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "body")
    plan = plan_import(tmp_path)
    assert isinstance(plan, ImportPlan)
    with pytest.raises((AttributeError, Exception)):
        plan.total_scanned = 999  # type: ignore[misc]


def test_plan_import_deterministic_across_runs(tmp_path: Path) -> None:
    _write(tmp_path / "Inbox" / "a.md", "#capture body " * 10)
    _write(tmp_path / "Inbox" / "b.md", "#capture body " * 10)
    p1 = plan_import(tmp_path)
    p2 = plan_import(tmp_path)
    keys_1 = [p.idempotency_key for p in p1.to_import_as_capture]
    keys_2 = [p.idempotency_key for p in p2.to_import_as_capture]
    assert keys_1 == keys_2


# ---------------------------------------------------------------------------
# execute_import (HTTP-mocked)
# ---------------------------------------------------------------------------


def _make_simple_plan(tmp_path: Path, *, n: int = 1) -> ImportPlan:
    for i in range(n):
        _write(
            tmp_path / f"n{i}.md",
            f"# Note {i}\n\nbody #capture content {i} " * 4,
        )
    return plan_import(tmp_path)


def test_execute_import_dry_run_default_no_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    made = _install_fake_http(monkeypatch, body={"capture_id": "cap_x"})
    plan = _make_simple_plan(tmp_path, n=2)
    result = execute_import(plan)
    assert result.dry_run is True
    assert result.posted == ()
    assert result.succeeded == 0 and result.failed == 0
    assert made == []  # never instantiated a connection


def test_execute_import_confirm_alone_is_still_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    made = _install_fake_http(monkeypatch, body={"capture_id": "cap_x"})
    plan = _make_simple_plan(tmp_path, n=2)
    # confirm=True alone (without dry_run=False) must NOT post.
    result = execute_import(plan, confirm=True)
    assert result.dry_run is True
    assert made == []


def test_execute_import_dry_run_false_alone_is_still_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    made = _install_fake_http(monkeypatch, body={"capture_id": "cap_x"})
    plan = _make_simple_plan(tmp_path, n=2)
    # dry_run=False alone (without confirm=True) also must NOT post.
    result = execute_import(plan, dry_run=False, confirm=False)
    assert result.dry_run is True
    assert made == []


def test_execute_import_happy_path_posts_each_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-xyz")
    plan = _make_simple_plan(tmp_path, n=2)
    keys = [p.idempotency_key for p in plan.to_import_as_capture]
    rels = [p.candidate.relative_path for p in plan.to_import_as_capture]
    sequence = [
        (200, {
            "ok": True,
            "capture_id": f"cap_{rels[0]}",
            "duplicate": False,
            "import_metadata": {
                "source_path": rels[0],
                "source_modified_at": "2026-04-14T12:00:00+00:00",
            },
        }),
        (200, {
            "ok": True,
            "capture_id": f"cap_{rels[1]}",
            "duplicate": False,
            "import_metadata": {
                "source_path": rels[1],
                "source_modified_at": "2026-04-14T12:00:00+00:00",
            },
        }),
    ]
    made = _install_fake_http_sequence(monkeypatch, sequence)
    result = execute_import(
        plan,
        dry_run=False,
        confirm=True,
        throttle_seconds=0.0,
    )
    assert result.dry_run is False
    assert result.succeeded == 2
    assert result.failed == 0
    assert len(result.posted) == 2
    # Idempotency keys + path + auth header all present on the wire.
    for i, conn in enumerate(made):
        req = conn.requests[0]
        assert req["method"] == "POST"
        assert req["path"].endswith(INGEST_TEXT_PATH)
        assert req["headers"]["X-Idempotency-Key"] == keys[i]
        assert req["headers"]["Authorization"] == "Bearer tok-xyz"
        assert req["headers"]["Content-Type"] == "application/json"
    # Each posted result echoes import_metadata correctly.
    for r in result.posted:
        assert r.ok is True
        assert r.import_metadata_echoed is True


def test_execute_import_per_file_failure_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    plan = _make_simple_plan(tmp_path, n=3)
    sequence = [
        (200, {"ok": True, "capture_id": "cap_a", "duplicate": False}),
        (500, {"detail": "boom"}),
        (200, {"ok": True, "capture_id": "cap_c", "duplicate": True}),
    ]
    made = _install_fake_http_sequence(monkeypatch, sequence)
    result = execute_import(
        plan,
        dry_run=False,
        confirm=True,
        throttle_seconds=0.0,
    )
    assert len(made) == 3
    assert result.succeeded == 2
    assert result.failed == 1
    assert result.duplicates == 1
    # The failed entry surfaces the status code + error.
    statuses = [r.status_code for r in result.posted]
    oks = [r.ok for r in result.posted]
    assert oks == [True, False, True]
    assert statuses[1] == 500


def test_execute_import_idempotency_key_stable_across_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    plan_a = _make_simple_plan(tmp_path, n=1)
    # Re-plan the same vault; key must not drift.
    plan_b = plan_import(tmp_path)
    assert plan_a.to_import_as_capture[0].idempotency_key == \
        plan_b.to_import_as_capture[0].idempotency_key
    sequence = [
        (200, {"ok": True, "capture_id": "cap_dup_1", "duplicate": False}),
        (200, {"ok": True, "capture_id": "cap_dup_1", "duplicate": True}),
    ]
    made = _install_fake_http_sequence(monkeypatch, sequence)
    r1 = execute_import(plan_a, dry_run=False, confirm=True, throttle_seconds=0.0)
    r2 = execute_import(plan_b, dry_run=False, confirm=True, throttle_seconds=0.0)
    # Both POSTs carry the same X-Idempotency-Key.
    assert made[0].requests[0]["headers"]["X-Idempotency-Key"] == \
        made[1].requests[0]["headers"]["X-Idempotency-Key"]
    # Service collapses to the same capture_id; second call is duplicate=True.
    assert r1.posted[0].capture_id == r2.posted[0].capture_id
    assert r2.posted[0].duplicate is True
    assert r2.duplicates == 1


def test_execute_import_honors_throttle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    plan = _make_simple_plan(tmp_path, n=3)
    sequence = [
        (200, {"ok": True, "capture_id": f"c{i}"}) for i in range(3)
    ]
    _install_fake_http_sequence(monkeypatch, sequence)
    sleeps: list[float] = []
    monotonic_calls = {"i": 0}

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def fake_monotonic() -> float:
        # Each successive call returns a tick 0, 1, 2, ...
        # so the perceived elapsed time between two calls is exactly 1s.
        monotonic_calls["i"] += 1
        return float(monotonic_calls["i"])

    result = execute_import(
        plan,
        dry_run=False,
        confirm=True,
        throttle_seconds=5.0,
        sleep=fake_sleep,
        monotonic=fake_monotonic,
    )
    assert result.succeeded == 3
    # Two waits between three POSTs. Throttle target 5s, perceived
    # elapsed 1s per gap -> wait 4s each time.
    assert sleeps == [4.0, 4.0]


def test_execute_import_no_throttle_when_throttle_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    plan = _make_simple_plan(tmp_path, n=2)
    _install_fake_http_sequence(
        monkeypatch,
        [(200, {"ok": True, "capture_id": "c"})] * 2,
    )
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    execute_import(
        plan,
        dry_run=False,
        confirm=True,
        throttle_seconds=0.0,
        sleep=fake_sleep,
    )
    assert sleeps == []


def test_execute_import_missing_service_url_marks_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    plan = _make_simple_plan(tmp_path, n=1)
    result = execute_import(plan, dry_run=False, confirm=True, throttle_seconds=0.0)
    assert result.failed == 1
    assert result.succeeded == 0
    assert "service not configured" in (result.posted[0].error or "")


def test_execute_import_invalid_scheme_marks_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _make_simple_plan(tmp_path, n=1)
    result = execute_import(
        plan,
        service_url="ftp://nope",
        dry_run=False,
        confirm=True,
        throttle_seconds=0.0,
    )
    assert result.failed == 1
    assert "http" in (result.posted[0].error or "").lower()


def test_execute_import_body_carries_extra_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    plan = _make_simple_plan(tmp_path, n=1)
    rel = plan.to_import_as_capture[0].candidate.relative_path
    sha = plan.to_import_as_capture[0].candidate.content_sha256
    made = _install_fake_http_sequence(
        monkeypatch,
        [(200, {"ok": True, "capture_id": "c"})],
    )
    execute_import(plan, dry_run=False, confirm=True, throttle_seconds=0.0)
    body = json.loads(made[0].requests[0]["body"].decode("utf-8"))
    assert body["source_app"] == DEFAULT_SOURCE_APP
    ctx = body["context"]
    assert ctx["entrypoint"] == "vault_import"
    assert ctx["capture_mode"] == "import"
    assert ctx["extra"]["source_path"] == rel
    assert ctx["extra"]["source_sha256"] == sha
    assert "title_guess" in ctx["extra"]
    assert "import_confidence" in ctx["extra"]


# ---------------------------------------------------------------------------
# Reports + serialization helpers
# ---------------------------------------------------------------------------


def test_default_report_path_uses_analytics_import(tmp_path: Path) -> None:
    p = default_report_path(tmp_path, timestamp="2026-04-14T12:00:00+00:00")
    assert p.parent == tmp_path / "Analytics" / "Import"
    # Colons are sanitized for cross-platform safety.
    assert ":" not in p.name


def test_write_import_report_renders_markdown(tmp_path: Path) -> None:
    plan = _make_simple_plan(tmp_path, n=1)
    result = execute_import(plan)  # dry-run
    target = default_report_path(tmp_path, timestamp="2026-04-14T12-00-00+00-00")
    written = write_import_report(result, target, vault_root=tmp_path)
    assert written.exists()
    body = written.read_text(encoding="utf-8")
    assert "# Vault Import Report" in body
    assert "type: import-report" in body
    assert "dry-run" in body


def test_plan_to_dict_round_trip(tmp_path: Path) -> None:
    plan = _make_simple_plan(tmp_path, n=2)
    d = plan_to_dict(plan)
    assert d["total_scanned"] == 2
    assert len(d["to_import_as_capture"]) == 2
    assert all("idempotency_key" in row for row in d["to_import_as_capture"])
    # JSON-serializable.
    json.dumps(d)


def test_result_to_dict_round_trip(tmp_path: Path) -> None:
    plan = _make_simple_plan(tmp_path, n=1)
    result = execute_import(plan)
    d = result_to_dict(result)
    assert d["dry_run"] is True
    json.dumps(d)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    """Invoke obsidian_connector.cli.main and capture stdout/stderr."""
    from obsidian_connector import cli as cli_module

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with patch.object(sys, "stdout", out_buf), patch.object(sys, "stderr", err_buf):
        rc = cli_module.main(argv)
    return rc, out_buf.getvalue(), err_buf.getvalue()


def test_cli_plan_import_runs(tmp_path: Path) -> None:
    _write(tmp_path / "Inbox" / "a.md", "#capture body " * 10)
    rc, out, _ = _run_cli(["plan-import", "--root", str(tmp_path)])
    assert rc == 0
    assert "Import plan" in out
    assert "ready_capture: 1" in out


def test_cli_plan_import_max_files_overflow_surfaces_error(tmp_path: Path) -> None:
    for i in range(3):
        _write(tmp_path / f"n{i}.md", "body")
    rc, out, _ = _run_cli([
        "plan-import", "--root", str(tmp_path), "--max-files", "1",
    ])
    # The CLI catches the ValueError and surfaces it via the human
    # output; rc is 0 because the envelope reports ok=false in --json
    # mode. The plain-text path prints "Plan failed: ..." to stdout.
    assert rc == 0
    assert "Plan failed" in out
    assert "max_files" in out


def test_cli_execute_import_default_is_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    _write(tmp_path / "a.md", "#capture body " * 10)
    made = _install_fake_http(monkeypatch, body={"capture_id": "c"})
    rc, out, _ = _run_cli(["execute-import", "--root", str(tmp_path)])
    assert rc == 0
    assert "dry-run" in out
    assert made == []  # never POSTed


def test_cli_execute_import_yes_without_execute_still_dry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    _write(tmp_path / "a.md", "#capture body " * 10)
    made = _install_fake_http(monkeypatch, body={"capture_id": "c"})
    # --yes alone (without --execute) should still be dry-run; the
    # default --dry-run wins.
    rc, _, _ = _run_cli([
        "execute-import", "--root", str(tmp_path), "--yes",
    ])
    assert rc == 0
    assert made == []


def test_cli_execute_import_execute_yes_actually_posts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    _write(tmp_path / "a.md", "#capture body " * 10)
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "capture_id": "cap_a", "duplicate": False},
    )
    rc, out, _ = _run_cli([
        "execute-import",
        "--root", str(tmp_path),
        "--execute", "--yes",
        "--throttle", "0",
    ])
    assert rc == 0
    assert "executed" in out
    assert len(made) == 1
    assert made[0].requests[0]["headers"]["X-Idempotency-Key"].startswith(
        IDEMPOTENCY_KEY_PREFIX
    )


def test_cli_execute_import_prompt_declined_no_post(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interactive prompt: typing anything other than 'yes' aborts."""
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    _write(tmp_path / "a.md", "#capture body " * 10)
    made = _install_fake_http(monkeypatch, body={"capture_id": "c"})

    # Force tty-detection true and inject a 'no' answer.
    import obsidian_connector.cli as cli_module

    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "no")
    rc, _, _ = _run_cli([
        "execute-import",
        "--root", str(tmp_path),
        "--execute",
        "--throttle", "0",
    ])
    assert rc == 0
    assert made == []


def test_cli_execute_import_prompt_accepted_posts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    _write(tmp_path / "a.md", "#capture body " * 10)
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "capture_id": "cap_a"},
    )

    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "yes")
    rc, _, _ = _run_cli([
        "execute-import",
        "--root", str(tmp_path),
        "--execute",
        "--throttle", "0",
    ])
    assert rc == 0
    assert len(made) == 1


# ---------------------------------------------------------------------------
# MCP tool surfaces
# ---------------------------------------------------------------------------


def test_mcp_obsidian_plan_import_returns_envelope(tmp_path: Path) -> None:
    _write(tmp_path / "a.md", "#capture body " * 10)
    from obsidian_connector.mcp_server import obsidian_plan_import

    raw = obsidian_plan_import(root=str(tmp_path))
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert "data" in payload
    assert payload["data"]["total_scanned"] == 1
    assert len(payload["data"]["to_import_as_capture"]) == 1


def test_mcp_obsidian_plan_import_max_files_overflow(tmp_path: Path) -> None:
    for i in range(3):
        _write(tmp_path / f"n{i}.md", "body")
    from obsidian_connector.mcp_server import obsidian_plan_import

    raw = obsidian_plan_import(root=str(tmp_path), max_files=1)
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert "max_files" in payload["error"]


def test_mcp_obsidian_execute_import_dry_run_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    _write(tmp_path / "a.md", "#capture body " * 10)
    made = _install_fake_http(monkeypatch, body={"capture_id": "c"})

    from obsidian_connector.mcp_server import obsidian_execute_import

    raw = obsidian_execute_import(root=str(tmp_path))
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True
    assert made == []


def test_mcp_obsidian_execute_import_explicit_posts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://h:8787")
    _write(tmp_path / "a.md", "#capture body " * 10)
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "capture_id": "cap_a", "duplicate": False},
    )

    from obsidian_connector.mcp_server import obsidian_execute_import

    raw = obsidian_execute_import(
        root=str(tmp_path),
        dry_run=False,
        confirm=True,
        throttle_seconds=0.0,
    )
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is False
    assert payload["data"]["succeeded"] == 1
    assert len(made) == 1
