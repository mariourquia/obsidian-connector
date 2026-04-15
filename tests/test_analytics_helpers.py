"""Tests for Task 39 analytics helpers, MCP passthrough, CLI, and dashboard.

Covers:

- HTTP wrappers in :mod:`obsidian_connector.analytics_ops`.
- Note projection (round-trip + user-notes fence preservation + path
  determinism).
- `Dashboards/Analytics.md` renderer + generator (with + without
  service URL).
- CLI passthrough for ``weekly-report``, ``weekly-report-markdown``,
  ``weeks-available``, and ``write-weekly-report``.

HTTP is mocked at ``http.client`` level so no real traffic is issued.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector import analytics_ops
from obsidian_connector.commitment_dashboards import (
    _DASHBOARD_ANALYTICS_PATH,
    _render_analytics_md,
    generate_analytics_index_dashboard,
)


# ---------------------------------------------------------------------------
# Shared HTTP fake (mirrors test_admin_helpers.py)
# ---------------------------------------------------------------------------


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
        self.requests: list[dict] = []
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
    body: object | str = None,
) -> list[_FakeConnection]:
    """Install a single-response fake. ``body`` may be dict (JSON) or str."""
    made: list[_FakeConnection] = []
    if isinstance(body, str):
        payload = body
    elif body is None:
        payload = "{}"
    else:
        payload = json.dumps(body)

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
    responses: list[tuple[int, object | str]],
) -> list[_FakeConnection]:
    made: list[_FakeConnection] = []
    idx = {"i": 0}

    def _factory(netloc: str, **kwargs: object) -> _FakeConnection:
        conn = _FakeConnection(netloc, **kwargs)
        i = idx["i"]
        status, body = responses[min(i, len(responses) - 1)]
        if isinstance(body, str):
            payload = body
        else:
            payload = json.dumps(body)
        conn.response_status = status
        conn.response_body = payload
        idx["i"] = i + 1
        made.append(conn)
        return conn

    import http.client as hc

    monkeypatch.setattr(hc, "HTTPConnection", _factory)
    monkeypatch.setattr(hc, "HTTPSConnection", _factory)
    return made


# ---------------------------------------------------------------------------
# get_weekly_report
# ---------------------------------------------------------------------------


def test_get_weekly_report_builds_query_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-w")
    body = {"window": {"week_label": "2026-W16"}}
    made = _install_fake_http(monkeypatch, body=body)

    result = analytics_ops.get_weekly_report(week_offset=-2)
    assert result["ok"] is True
    assert result["data"] == body
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"].startswith("/api/v1/analytics/weekly?")
    assert "week_offset=-2" in req["path"]
    assert req["headers"].get("Authorization") == "Bearer tok-w"


def test_get_weekly_report_default_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    made = _install_fake_http(monkeypatch, body={})
    analytics_ops.get_weekly_report()
    req = made[0].requests[0]
    assert "week_offset=0" in req["path"]


def test_get_weekly_report_missing_url_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = analytics_ops.get_weekly_report(service_url=None)
    assert result["ok"] is False
    assert "not configured" in result["error"]


def test_get_weekly_report_http_error_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(monkeypatch, status=500, body={"detail": "boom"})
    result = analytics_ops.get_weekly_report()
    assert result["ok"] is False
    assert result.get("status_code") == 500


# ---------------------------------------------------------------------------
# get_weekly_report_markdown
# ---------------------------------------------------------------------------


def test_get_weekly_report_markdown_returns_string_in_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-md")
    made = _install_fake_http(monkeypatch, body="# Weekly Activity\n\nHi!\n")
    result = analytics_ops.get_weekly_report_markdown(week_offset=0)
    assert result["ok"] is True
    assert result["data"]["markdown"].startswith("# Weekly Activity")
    req = made[0].requests[0]
    assert req["path"].startswith("/api/v1/analytics/weekly/markdown?")
    assert req["headers"].get("Accept") == "text/markdown"
    assert req["headers"].get("Authorization") == "Bearer tok-md"


def test_get_weekly_report_markdown_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = analytics_ops.get_weekly_report_markdown()
    assert result["ok"] is False
    assert "not configured" in result["error"]


def test_get_weekly_report_markdown_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(monkeypatch, status=422, body={"detail": "bad"})
    result = analytics_ops.get_weekly_report_markdown()
    assert result["ok"] is False
    assert result.get("status_code") == 422


def test_get_weekly_report_markdown_bad_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = analytics_ops.get_weekly_report_markdown(service_url="ftp://x")
    assert result["ok"] is False
    assert "http" in result["error"]


# ---------------------------------------------------------------------------
# list_weeks_available
# ---------------------------------------------------------------------------


def test_list_weeks_available_builds_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    body = {"weeks_back": 4, "items": [{"week_label": "2026-W16"}]}
    made = _install_fake_http(monkeypatch, body=body)
    result = analytics_ops.list_weeks_available(weeks_back=4)
    assert result["ok"] is True
    req = made[0].requests[0]
    assert "weeks_back=4" in req["path"]
    assert req["path"].startswith("/api/v1/analytics/weeks-available?")


def test_list_weeks_available_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    made = _install_fake_http(monkeypatch, body={})
    analytics_ops.list_weeks_available()
    req = made[0].requests[0]
    assert "weeks_back=12" in req["path"]


def test_list_weeks_available_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = analytics_ops.list_weeks_available()
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# Note projection
# ---------------------------------------------------------------------------


def test_weekly_report_note_path_is_deterministic(tmp_path: Path) -> None:
    p1 = analytics_ops.weekly_report_note_path(tmp_path, "2026-W16")
    p2 = analytics_ops.weekly_report_note_path(tmp_path, "2026-W16")
    assert p1 == p2
    assert str(p1).endswith("/Analytics/Weekly/2026/2026-W16.md")


def test_weekly_report_note_path_year_boundary(tmp_path: Path) -> None:
    # Dec 30, 2024 -> ISO 2025-W01 label, year prefix "2025".
    p = analytics_ops.weekly_report_note_path(tmp_path, "2025-W01")
    assert "/Analytics/Weekly/2025/" in str(p)


def test_write_weekly_report_note_round_trip(tmp_path: Path) -> None:
    md = "# Weekly Activity — 2026-W16\n\nBody.\n"
    result = analytics_ops.write_weekly_report_note(
        tmp_path, md, "2026-W16", generated_at="2026-04-15T10:00:00+00:00",
    )
    assert result.written is True
    text = result.path.read_text(encoding="utf-8")
    assert "type: analytics" in text
    assert "week_label: 2026-W16" in text
    assert "generated_at: 2026-04-15T10:00:00+00:00" in text
    assert "# Weekly Activity — 2026-W16" in text
    assert "<!-- service:analytics-user-notes:begin -->" in text
    assert "<!-- service:analytics-user-notes:end -->" in text


def test_write_weekly_report_note_preserves_user_notes_fence(
    tmp_path: Path,
) -> None:
    md = "# Week one\n\nBody.\n"
    # First write.
    r1 = analytics_ops.write_weekly_report_note(
        tmp_path, md, "2026-W16", generated_at="2026-04-15T10:00:00+00:00"
    )
    # Manually edit the fence.
    content = r1.path.read_text(encoding="utf-8")
    mutated = content.replace(
        "<!-- service:analytics-user-notes:begin -->\n"
        "<!-- service:analytics-user-notes:end -->",
        "<!-- service:analytics-user-notes:begin -->\n"
        "My commentary about the week.\n"
        "<!-- service:analytics-user-notes:end -->",
    )
    r1.path.write_text(mutated, encoding="utf-8")

    # Re-project with new body.
    analytics_ops.write_weekly_report_note(
        tmp_path,
        "# Week one updated\n\nDifferent body.\n",
        "2026-W16",
        generated_at="2026-04-16T10:00:00+00:00",
    )
    text = r1.path.read_text(encoding="utf-8")
    assert "My commentary about the week." in text
    assert "# Week one updated" in text
    assert "# Week one\n" not in text  # old body gone


def test_write_weekly_report_note_is_byte_deterministic_for_fixed_input(
    tmp_path: Path,
) -> None:
    md = "# W\n\nX\n"
    r = analytics_ops.write_weekly_report_note(
        tmp_path, md, "2026-W16", generated_at="2026-04-15T10:00:00+00:00"
    )
    body1 = r.path.read_bytes()
    # Re-running with identical args produces the same bytes.
    analytics_ops.write_weekly_report_note(
        tmp_path, md, "2026-W16", generated_at="2026-04-15T10:00:00+00:00"
    )
    body2 = r.path.read_bytes()
    assert body1 == body2


def test_fetch_and_write_weekly_report_note_happy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    # Sequence: first markdown call (text body), then JSON call for the label.
    _install_fake_http_sequence(
        monkeypatch,
        [
            (200, "# Weekly Activity — 2026-W16\n\nBody.\n"),
            (200, {"window": {"week_label": "2026-W16"}}),
        ],
    )
    result = analytics_ops.fetch_and_write_weekly_report_note(
        tmp_path, week_offset=0, generated_at="2026-04-15T10:00:00+00:00"
    )
    assert result["ok"] is True
    assert result["week_label"] == "2026-W16"
    written = Path(result["path"]).read_text(encoding="utf-8")
    assert "week_label: 2026-W16" in written


def test_fetch_and_write_weekly_report_note_markdown_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(monkeypatch, status=500, body={"detail": "nope"})
    result = analytics_ops.fetch_and_write_weekly_report_note(tmp_path)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# Dashboard renderer + generator
# ---------------------------------------------------------------------------


def test_render_analytics_md_without_service() -> None:
    body = _render_analytics_md(
        now_iso="2026-04-15T10:00:00+00:00",
        weeks_items=None,
        this_week_payload=None,
        present_labels=set(),
        service_configured=False,
        service_error=None,
    )
    assert "# Analytics" in body
    assert "service not configured" in body


def test_render_analytics_md_with_data() -> None:
    weeks = [
        {"week_label": "2026-W16", "start_iso": "a", "end_iso": "b"},
        {"week_label": "2026-W15", "start_iso": "c", "end_iso": "d"},
    ]
    this_week = {
        "window": {"week_label": "2026-W16"},
        "captures": {"total": 5},
        "actions_created": {"total": 6},
        "actions_completed": {"total": 2},
        "actions_postponed": {"count": 1},
        "health_snapshot": {"overall_status": "ok"},
    }
    body = _render_analytics_md(
        now_iso="2026-04-15T10:00:00+00:00",
        weeks_items=weeks,
        this_week_payload=this_week,
        present_labels={"2026-W15"},
        service_configured=True,
        service_error=None,
    )
    # 2026-W15 is "present" so it links into the vault; W16 does not.
    assert "Analytics/Weekly/2026/2026-W15.md" in body
    assert "(not written)" in body  # for W16
    assert "**Week**: 2026-W16" in body


def test_generate_analytics_index_dashboard_without_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    res = generate_analytics_index_dashboard(
        tmp_path, now_iso="2026-04-15T10:00:00+00:00"
    )
    body = res.path.read_text(encoding="utf-8")
    assert "service not configured" in body
    assert res.path.name == "Analytics.md"


def test_generate_analytics_index_dashboard_happy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http_sequence(
        monkeypatch,
        [
            (200, {"weeks_back": 2, "items": [
                {"week_label": "2026-W16", "start_iso": "a", "end_iso": "b"},
                {"week_label": "2026-W15", "start_iso": "c", "end_iso": "d"},
            ]}),
            (200, {
                "window": {"week_label": "2026-W16"},
                "captures": {"total": 1},
                "actions_created": {"total": 0},
                "actions_completed": {"total": 0},
                "actions_postponed": {"count": 0},
                "health_snapshot": {"overall_status": "ok"},
            }),
        ],
    )
    res = generate_analytics_index_dashboard(
        tmp_path, now_iso="2026-04-15T10:00:00+00:00", weeks_back=2
    )
    body = res.path.read_text(encoding="utf-8")
    assert "2026-W16" in body
    assert "2026-W15" in body
    # No existing notes -> both labels show "(not written)".
    assert "(not written)" in body


def test_update_all_dashboards_includes_analytics_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from obsidian_connector.commitment_dashboards import update_all_dashboards

    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    (tmp_path / "Commitments").mkdir()
    (tmp_path / "Dashboards").mkdir()
    results = update_all_dashboards(tmp_path, now_iso="2026-04-15T10:00:00+00:00")
    names = [r.path.name for r in results]
    assert "Analytics.md" in names


def test_update_all_dashboards_respects_include_analytics_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from obsidian_connector.commitment_dashboards import update_all_dashboards

    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    (tmp_path / "Commitments").mkdir()
    (tmp_path / "Dashboards").mkdir()
    results = update_all_dashboards(
        tmp_path,
        now_iso="2026-04-15T10:00:00+00:00",
        include_analytics=False,
    )
    names = [r.path.name for r in results]
    assert "Analytics.md" not in names


# ---------------------------------------------------------------------------
# CLI passthrough
# ---------------------------------------------------------------------------


def test_cli_weekly_report_human_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(
        monkeypatch,
        body={
            "window": {
                "week_label": "2026-W16",
                "start_iso": "a",
                "end_iso": "b",
            },
            "captures": {"total": 5},
            "actions_created": {"total": 6},
            "actions_completed": {"total": 2, "median_age_days": 3},
            "actions_postponed": {"count": 1},
            "delivery_stats": {"total_deliveries": 0, "failure_rate": 0.0},
        },
    )
    from obsidian_connector.cli import main

    rc = main(["weekly-report", "--week-offset", "0"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "2026-W16" in out
    assert "captures: 5" in out


def test_cli_weekly_report_markdown_human_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(monkeypatch, body="# Weekly Activity — 2026-W16\n")
    from obsidian_connector.cli import main

    rc = main(["weekly-report-markdown"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "# Weekly Activity — 2026-W16" in out


def test_cli_weeks_available_human_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(
        monkeypatch,
        body={
            "weeks_back": 2,
            "items": [
                {"week_label": "2026-W16", "start_iso": "a", "end_iso": "b"},
                {"week_label": "2026-W15", "start_iso": "c", "end_iso": "d"},
            ],
        },
    )
    from obsidian_connector.cli import main

    rc = main(["weeks-available", "--weeks-back", "2"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "2026-W16" in out
    assert "2026-W15" in out


def test_cli_weekly_report_service_not_configured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    from obsidian_connector.cli import main

    rc = main(["weekly-report"])
    out = capsys.readouterr().out
    # The CLI still exits 0 — envelope-based failure, not a crash.
    assert rc == 0
    assert "failed" in out


def test_cli_write_weekly_report_writes_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    _install_fake_http_sequence(
        monkeypatch,
        [
            (200, "# Weekly Activity — 2026-W16\n\nBody.\n"),
            (200, {"window": {"week_label": "2026-W16"}}),
        ],
    )
    from obsidian_connector.cli import main

    rc = main([
        "write-weekly-report",
        "--vault-root", str(tmp_path),
        "--week-offset", "0",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    target = tmp_path / "Analytics" / "Weekly" / "2026" / "2026-W16.md"
    assert target.exists()
    assert "week_label: 2026-W16" in target.read_text(encoding="utf-8")
