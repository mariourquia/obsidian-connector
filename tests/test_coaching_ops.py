"""Tests for Task 40 coaching-ops helpers, MCP passthrough, CLI, and dashboard.

Covers the two HTTP wrappers in
:mod:`obsidian_connector.coaching_ops`, the matching CLI subcommands,
and the Task 40 review coaching dashboard renderer including the
"service not configured" fallback. HTTP is mocked via a fake
`http.client` connection pair; no real traffic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector import coaching_ops
from obsidian_connector.commitment_dashboards import (
    _DASHBOARD_COACHING_PATH,
    _render_coaching_md,
    generate_coaching_dashboard,
)


# ---------------------------------------------------------------------------
# Shared HTTP fake (mirrors the pattern in test_admin_helpers.py)
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


# ---------------------------------------------------------------------------
# get_action_recommendations
# ---------------------------------------------------------------------------


def test_action_recommendations_builds_path_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-coach")
    body = {
        "ok": True,
        "action_id": "act_123",
        "recommendations": [
            {
                "code": "CONSIDER_UNBLOCK",
                "label": "Blocked",
                "action_verb": "unblock",
                "confidence": 0.7,
                "rationale": {"source": "reasoning"},
                "suggested_inputs": {"blocker_action_ids": ["act_9"]},
            },
        ],
    }
    made = _install_fake_http(monkeypatch, body=body)
    result = coaching_ops.get_action_recommendations("act_123")
    assert result["ok"] is True
    assert result["data"] == body
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"] == "/api/v1/coaching/action/act_123"
    assert req["headers"].get("Authorization") == "Bearer tok-coach"


def test_action_recommendations_encodes_action_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    coaching_ops.get_action_recommendations("act with/slash")
    path = made[0].requests[0]["path"]
    # Slashes must be URL-encoded so they don't break the path split.
    assert "act%20with%2Fslash" in path


def test_action_recommendations_rejects_empty_id() -> None:
    result = coaching_ops.get_action_recommendations("")
    assert result["ok"] is False
    assert "non-empty" in result["error"]


def test_action_recommendations_rejects_non_string() -> None:
    result = coaching_ops.get_action_recommendations(None)  # type: ignore[arg-type]
    assert result["ok"] is False
    assert "non-empty" in result["error"]


def test_action_recommendations_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = coaching_ops.get_action_recommendations("act_1")
    assert result["ok"] is False
    assert "service not configured" in result["error"]


def test_action_recommendations_404_status_code_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch, status=404, body={"detail": "Action not found"},
    )
    result = coaching_ops.get_action_recommendations("act_missing")
    assert result["ok"] is False
    assert result["status_code"] == 404


def test_action_recommendations_409_status_code_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch, status=409, body={"detail": "terminal"},
    )
    result = coaching_ops.get_action_recommendations("act_done")
    assert result["ok"] is False
    assert result["status_code"] == 409


def test_action_recommendations_override_args_preferred_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://env:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "env-tok")
    made = _install_fake_http(monkeypatch, body={})
    coaching_ops.get_action_recommendations(
        "act_1", service_url="http://override:9000", token="override-tok",
    )
    assert made[0].netloc == "override:9000"
    assert made[0].requests[0]["headers"].get("Authorization") == "Bearer override-tok"


# ---------------------------------------------------------------------------
# list_review_recommendations
# ---------------------------------------------------------------------------


def test_review_recommendations_builds_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "since_days": 7, "limit": 50, "items": [],
    }
    made = _install_fake_http(monkeypatch, body=body)
    result = coaching_ops.list_review_recommendations(
        since_days=14, limit=25,
    )
    assert result["ok"] is True
    assert result["data"] == body
    path = made[0].requests[0]["path"]
    assert path.startswith("/api/v1/coaching/review?")
    assert "since_days=14" in path
    assert "limit=25" in path


def test_review_recommendations_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"items": []})
    coaching_ops.list_review_recommendations()
    path = made[0].requests[0]["path"]
    assert "since_days=7" in path
    assert "limit=50" in path


def test_review_recommendations_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = coaching_ops.list_review_recommendations()
    assert result["ok"] is False
    assert "service not configured" in result["error"]


def test_review_recommendations_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=500, body={"error": "boom"})
    result = coaching_ops.list_review_recommendations()
    assert result["ok"] is False
    assert result["status_code"] == 500


def test_review_recommendations_never_raises_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")

    class _BadConn:
        netloc = "host:8787"
        timeout = 10.0
        requests: list = []

        def __init__(self, *_a: object, **_kw: object) -> None:
            pass

        def request(self, *_a: object, **_kw: object) -> None:
            pass

        def getresponse(self) -> _FakeResponse:
            return _FakeResponse(200, "not json {{{")

        def close(self) -> None:
            pass

    import http.client as hc
    monkeypatch.setattr(hc, "HTTPConnection", _BadConn)
    result = coaching_ops.list_review_recommendations()
    assert result["ok"] is False
    assert "malformed" in result["error"]


# ---------------------------------------------------------------------------
# MCP passthrough
# ---------------------------------------------------------------------------


def _resolve_mcp_fn(tool):
    """Unwrap an MCP-decorated function to its underlying callable."""
    return getattr(tool, "fn", tool)


def test_mcp_action_recommendations_returns_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "action_id": "act_1",
        "recommendations": [
            {
                "code": "CONSIDER_MERGE",
                "label": "dup", "action_verb": "merge",
                "confidence": 0.9, "rationale": {}, "suggested_inputs": {},
            },
        ],
    }
    _install_fake_http(monkeypatch, body=body)
    from obsidian_connector import mcp_server

    fn = _resolve_mcp_fn(mcp_server.obsidian_action_recommendations)
    raw = fn("act_1")
    out = json.loads(raw)
    assert out["ok"] is True
    assert out["data"] == body


def test_mcp_review_recommendations_returns_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch, body={"ok": True, "since_days": 7, "limit": 50, "items": []},
    )
    from obsidian_connector import mcp_server

    fn = _resolve_mcp_fn(mcp_server.obsidian_review_recommendations)
    raw = fn(since_days=7, limit=50)
    out = json.loads(raw)
    assert out["ok"] is True


# ---------------------------------------------------------------------------
# Dashboard render (pure)
# ---------------------------------------------------------------------------


def test_render_coaching_md_service_not_configured() -> None:
    content = _render_coaching_md(
        now_iso="2026-04-15T10:00:00+00:00",
        since_days=7,
        items=None,
        service_configured=False,
        service_error=None,
    )
    assert "service not configured" in content.lower()
    assert "# Review coaching" in content
    # Every section header present with zero counts.
    for label in (
        "Consider cancel", "Consider delegate", "Consider merge",
        "Consider reclaim", "Consider reschedule", "Consider unblock",
    ):
        assert f"## {label} (0)" in content


def test_render_coaching_md_service_error_banner() -> None:
    content = _render_coaching_md(
        now_iso="2026-04-15T10:00:00+00:00",
        since_days=7,
        items=None,
        service_configured=True,
        service_error="timeout",
    )
    assert "unreachable" in content.lower()
    assert "timeout" in content


def test_render_coaching_md_groups_items_by_code() -> None:
    items = [
        {
            "action_id": "act_blocked",
            "title": "Blocked thing",
            "urgency": "elevated",
            "impact_score": 6,
            "recommendations": [
                {
                    "code": "CONSIDER_UNBLOCK",
                    "label": "Blocked by 1 open action",
                    "action_verb": "unblock",
                    "confidence": 0.7,
                    "rationale": {},
                    "suggested_inputs": {},
                },
            ],
        },
        {
            "action_id": "act_dup",
            "title": "Duplicate",
            "urgency": "normal",
            "impact_score": 2,
            "recommendations": [
                {
                    "code": "CONSIDER_MERGE",
                    "label": "Likely dup",
                    "action_verb": "merge",
                    "confidence": 0.9,
                    "rationale": {},
                    "suggested_inputs": {"winner_id": "act_other"},
                },
            ],
        },
    ]
    content = _render_coaching_md(
        now_iso="2026-04-15T10:00:00+00:00",
        since_days=7,
        items=items,
        service_configured=True,
        service_error=None,
    )
    assert "## Consider unblock (1)" in content
    assert "## Consider merge (1)" in content
    assert "Blocked thing" in content
    assert "Duplicate" in content
    # Sections are in alphabetical code order (so `Consider cancel` precedes `Consider merge`).
    cancel_idx = content.index("## Consider cancel")
    merge_idx = content.index("## Consider merge")
    unblock_idx = content.index("## Consider unblock")
    assert cancel_idx < merge_idx < unblock_idx


def test_render_coaching_md_no_recommendations_note() -> None:
    content = _render_coaching_md(
        now_iso="2026-04-15T10:00:00+00:00",
        since_days=7,
        items=[],
        service_configured=True,
        service_error=None,
    )
    assert "No review recommendations" in content


def test_render_coaching_md_mentions_window() -> None:
    content = _render_coaching_md(
        now_iso="2026-04-15T10:00:00+00:00",
        since_days=14,
        items=None,
        service_configured=False,
        service_error=None,
    )
    assert "last 14" in content


def test_render_coaching_md_is_deterministic() -> None:
    items = [
        {
            "action_id": "act_a", "title": "A", "urgency": "normal",
            "impact_score": 2,
            "recommendations": [
                {
                    "code": "CONSIDER_UNBLOCK", "label": "x", "action_verb": "unblock",
                    "confidence": 0.7, "rationale": {}, "suggested_inputs": {},
                },
            ],
        },
    ]
    a = _render_coaching_md(
        now_iso="2026-04-15T10:00:00+00:00",
        since_days=7,
        items=items,
        service_configured=True,
        service_error=None,
    )
    b = _render_coaching_md(
        now_iso="2026-04-15T10:00:00+00:00",
        since_days=7,
        items=items,
        service_configured=True,
        service_error=None,
    )
    assert a == b


# ---------------------------------------------------------------------------
# generate_coaching_dashboard (integration with fake service)
# ---------------------------------------------------------------------------


def test_generate_coaching_dashboard_writes_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = generate_coaching_dashboard(tmp_path)
    assert result.path.exists()
    content = result.path.read_text(encoding="utf-8")
    assert "service not configured" in content.lower()
    assert result.written == 0


def test_generate_coaching_dashboard_writes_items_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "since_days": 7, "limit": 50,
        "items": [
            {
                "action_id": "act_1", "title": "One",
                "urgency": "critical", "impact_score": 11,
                "recommendations": [
                    {
                        "code": "CONSIDER_RESCHEDULE",
                        "label": "Overdue",
                        "action_verb": "postpone",
                        "confidence": 0.8,
                        "rationale": {"source": "reasoning"},
                        "suggested_inputs": {"postponed_until": "2026-04-18T10:00:00+00:00"},
                    },
                ],
            },
        ],
    }
    _install_fake_http(monkeypatch, body=body)
    result = generate_coaching_dashboard(tmp_path, since_days=7)
    assert result.path.exists()
    content = result.path.read_text(encoding="utf-8")
    assert "One" in content
    assert "CONSIDER_RESCHEDULE" not in content  # we show the label, not the code directly
    assert "Consider reschedule" in content
    assert result.written == 1


def test_generate_coaching_dashboard_banner_on_service_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=503, body={"error": "down"})
    result = generate_coaching_dashboard(tmp_path)
    content = result.path.read_text(encoding="utf-8")
    assert "unreachable" in content.lower()
    assert result.written == 0


def test_generate_coaching_dashboard_honours_now_iso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    ts = "2026-04-15T12:34:56+00:00"
    result = generate_coaching_dashboard(tmp_path, now_iso=ts)
    content = result.path.read_text(encoding="utf-8")
    assert f"generated_at: {ts}" in content


def test_generate_coaching_dashboard_path_lives_under_review_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = generate_coaching_dashboard(tmp_path)
    rel = result.path.relative_to(tmp_path)
    assert str(rel) == _DASHBOARD_COACHING_PATH


# ---------------------------------------------------------------------------
# update_all_review_dashboards wiring
# ---------------------------------------------------------------------------


def test_update_all_review_includes_coaching_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    from obsidian_connector.commitment_dashboards import (
        update_all_review_dashboards,
    )
    results = update_all_review_dashboards(
        tmp_path, now_iso="2026-04-15T10:00:00+00:00",
    )
    names = [r.path.name for r in results]
    assert "Coaching.md" in names


def test_update_all_review_skips_coaching_when_opted_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    from obsidian_connector.commitment_dashboards import (
        update_all_review_dashboards,
    )
    results = update_all_review_dashboards(
        tmp_path,
        now_iso="2026-04-15T10:00:00+00:00",
        include_coaching=False,
    )
    names = [r.path.name for r in results]
    assert "Coaching.md" not in names


def test_update_all_review_coaching_failure_non_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from obsidian_connector import commitment_dashboards as cd

    def _boom(*_a: object, **_kw: object) -> object:
        raise RuntimeError("coaching crashed")

    monkeypatch.setattr(cd, "generate_coaching_dashboard", _boom)
    # Should not raise even though the coaching generator errors.
    results = cd.update_all_review_dashboards(
        tmp_path, now_iso="2026-04-15T10:00:00+00:00",
        include_delegations=False,
    )
    names = [r.path.name for r in results]
    # Historical four still land; Coaching.md never lands.
    assert "Daily.md" in names
    assert "Coaching.md" not in names


# ---------------------------------------------------------------------------
# CLI integration smoke
# ---------------------------------------------------------------------------


def test_cli_action_recommendations_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "action_id": "act_1",
        "recommendations": [
            {
                "code": "CONSIDER_UNBLOCK", "label": "Blocked by 1",
                "action_verb": "unblock", "confidence": 0.7,
                "rationale": {}, "suggested_inputs": {"blocker_action_ids": ["act_9"]},
            },
        ],
    }
    _install_fake_http(monkeypatch, body=body)
    from obsidian_connector.cli import main

    rc = main([
        "action-recommendations",
        "--action-id", "act_1",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Review recommendations for act_1" in out
    assert "CONSIDER_UNBLOCK" in out


def test_cli_action_recommendations_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "action_id": "act_1",
        "recommendations": [],
    }
    _install_fake_http(monkeypatch, body=body)
    from obsidian_connector.cli import main

    rc = main([
        "--json",
        "action-recommendations",
        "--action-id", "act_1",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True


def test_cli_review_recommendations_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "since_days": 7, "limit": 50, "items": [],
    }
    _install_fake_http(monkeypatch, body=body)
    from obsidian_connector.cli import main

    rc = main(["review-recommendations"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Top-" in out
    assert "window" in out


def test_cli_review_recommendations_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "since_days": 14, "limit": 10, "items": [],
    }
    _install_fake_http(monkeypatch, body=body)
    from obsidian_connector.cli import main

    rc = main([
        "--json",
        "review-recommendations",
        "--since-days", "14",
        "--limit", "10",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True


def test_cli_action_recommendations_handles_404(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch, status=404, body={"detail": "Action not found"},
    )
    from obsidian_connector.cli import main

    rc = main([
        "action-recommendations",
        "--action-id", "act_missing",
    ])
    # The CLI always returns 0 for these failure envelopes (printed to stdout).
    assert rc == 0
    out = capsys.readouterr().out
    assert "not found" in out.lower()
