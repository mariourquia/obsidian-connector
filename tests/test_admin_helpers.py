"""Tests for Task 44 admin-ops helpers, MCP passthrough, CLI, and dashboard.

Covers the five HTTP wrappers in :mod:`obsidian_connector.admin_ops`,
the CLI subcommands that use them, and the admin dashboard renderer
including the "service not configured" fallback. HTTP is mocked; no
real traffic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector import admin_ops
from obsidian_connector.commitment_dashboards import (
    _DASHBOARD_ADMIN_PATH,
    _render_admin_md,
    generate_admin_dashboard,
)


# ---------------------------------------------------------------------------
# Shared HTTP fake
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
# get_queue_health
# ---------------------------------------------------------------------------


def test_queue_health_builds_query_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-qh")
    body = {"enabled": True, "reachable": True, "counts": {"pending": 3}}
    made = _install_fake_http(monkeypatch, body=body)

    result = admin_ops.get_queue_health(since_hours=12)
    assert result["ok"] is True
    assert result["data"] == body
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"].startswith("/api/v1/admin/queue-health?")
    assert "since_hours=12" in req["path"]
    assert req["headers"].get("Authorization") == "Bearer tok-qh"


def test_queue_health_default_since_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"enabled": False})
    admin_ops.get_queue_health()
    assert "since_hours=24" in made[0].requests[0]["path"]


def test_queue_health_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = admin_ops.get_queue_health()
    assert result["ok"] is False
    assert "service not configured" in result["error"]


# ---------------------------------------------------------------------------
# list_delivery_failures
# ---------------------------------------------------------------------------


def test_delivery_failures_builds_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {"since_hours": 24, "limit": 50, "items": [{"delivery_id": "d1"}]}
    made = _install_fake_http(monkeypatch, body=body)
    result = admin_ops.list_delivery_failures(since_hours=48, limit=50)
    assert result["ok"] is True
    path = made[0].requests[0]["path"]
    assert path.startswith("/api/v1/admin/delivery-failures?")
    assert "since_hours=48" in path
    assert "limit=50" in path


def test_delivery_failures_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"items": []})
    admin_ops.list_delivery_failures()
    path = made[0].requests[0]["path"]
    assert "since_hours=24" in path
    assert "limit=100" in path


def test_delivery_failures_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=500, body={"error": "boom"})
    r = admin_ops.list_delivery_failures()
    assert r["ok"] is False
    assert r["status_code"] == 500


# ---------------------------------------------------------------------------
# list_pending_approvals
# ---------------------------------------------------------------------------


def test_pending_approvals_builds_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"items": []})
    admin_ops.list_pending_approvals(limit=25)
    path = made[0].requests[0]["path"]
    assert path.startswith("/api/v1/admin/pending-approvals?")
    assert "limit=25" in path


def test_pending_approvals_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    r = admin_ops.list_pending_approvals()
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# list_stale_sync_devices
# ---------------------------------------------------------------------------


def test_stale_sync_devices_builds_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"items": []})
    admin_ops.list_stale_sync_devices(threshold_hours=72)
    path = made[0].requests[0]["path"]
    assert path.startswith("/api/v1/admin/stale-sync-devices?")
    assert "threshold_hours=72" in path


def test_stale_sync_devices_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"items": []})
    admin_ops.list_stale_sync_devices()
    assert "threshold_hours=24" in made[0].requests[0]["path"]


# ---------------------------------------------------------------------------
# get_system_health
# ---------------------------------------------------------------------------


def test_system_health_calls_composite_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "overall_status": "ok",
        "generated_at": "2026-04-14T12:00:00+00:00",
        "doctor": {"counts": {"ok": 3, "warn": 0, "fail": 0, "skip": 1}, "checks": []},
        "queue": {"enabled": False, "reachable": False, "counts": {},
                  "error_rate": 0.0, "since_hours": 24},
        "deliveries": {"failure_count": 0, "since_hours": 24},
        "approvals": {"pending_count": 0},
        "devices": {"stale_count": 0, "threshold_hours": 24},
    }
    made = _install_fake_http(monkeypatch, body=body)
    result = admin_ops.get_system_health()
    assert result["ok"] is True
    assert result["data"]["overall_status"] == "ok"
    assert made[0].requests[0]["path"] == "/api/v1/admin/system-health"


def test_system_health_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    r = admin_ops.get_system_health()
    assert r["ok"] is False


def test_system_health_tolerates_missing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older service might not return every subsection. Caller should cope."""
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    partial = {"overall_status": "warn"}
    _install_fake_http(monkeypatch, body=partial)
    r = admin_ops.get_system_health()
    assert r["ok"] is True
    assert r["data"].get("overall_status") == "warn"


# ---------------------------------------------------------------------------
# Admin dashboard renderer (pure)
# ---------------------------------------------------------------------------


def test_render_admin_md_not_configured() -> None:
    out = _render_admin_md(
        now_iso="2026-04-14T00:00:00+00:00",
        system_health_payload=None,
        queue_health_payload=None,
        delivery_failures_items=None,
        pending_approvals_items=None,
        stale_devices_items=None,
        service_configured=False,
        service_error=None,
    )
    assert "Capture service not configured" in out
    assert "## System health summary" in out
    assert "## Queue health" in out
    assert "## Recent delivery failures" in out
    assert "## Pending approvals" in out
    assert "## Stale sync devices" in out


def test_render_admin_md_with_data() -> None:
    out = _render_admin_md(
        now_iso="2026-04-14T00:00:00+00:00",
        system_health_payload={
            "overall_status": "warn",
            "doctor": {
                "counts": {"ok": 2, "warn": 1, "fail": 0, "skip": 0},
                "checks": [{"name": "env", "status": "ok", "summary": "fine"}],
            },
            "queue": {"enabled": True, "reachable": True, "error_rate": 0.05},
        },
        queue_health_payload={
            "enabled": True,
            "reachable": True,
            "counts": {"pending": 2, "done": 40},
            "oldest_pending_age_seconds": 120,
            "error_rate": 0.05,
            "since_hours": 24,
        },
        delivery_failures_items=[
            {
                "delivery_id": "dlv_a",
                "action_id": "act_1",
                "channel": "email",
                "attempt": 2,
                "status": "failed",
                "last_error": "SMTP timeout",
                "scheduled_at": "2026-04-14T10:00:00+00:00",
                "dispatched_at": None,
                "action_title": "Ping the broker",
            },
        ],
        pending_approvals_items=[
            {
                "delivery_id": "dlv_b",
                "action_id": "act_2",
                "channel": "sms",
                "action_title": "Send reminder",
                "action_priority": "urgent",
                "scheduled_at": "2026-04-14T11:00:00+00:00",
            }
        ],
        stale_devices_items=[
            {
                "device_id": "iphone-15",
                "platform": "ios",
                "last_synced_at": "2026-04-10T00:00:00+00:00",
                "hours_since_last_sync": 96.0,
                "pending_ops_count": 3,
            }
        ],
        service_configured=True,
        service_error=None,
    )
    assert "WARN" in out.upper()
    assert "Ping the broker" in out
    assert "Send reminder" in out
    assert "iphone-15" in out
    assert "pending=2" in out
    assert "done=40" in out


def test_render_admin_md_service_error_banner() -> None:
    out = _render_admin_md(
        now_iso="2026-04-14T00:00:00+00:00",
        system_health_payload=None,
        queue_health_payload=None,
        delivery_failures_items=None,
        pending_approvals_items=None,
        stale_devices_items=None,
        service_configured=True,
        service_error="connection refused",
    )
    assert "Capture service unreachable" in out
    assert "connection refused" in out


# ---------------------------------------------------------------------------
# generate_admin_dashboard (integration)
# ---------------------------------------------------------------------------


def test_generate_admin_dashboard_without_service_url(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no service URL is configured, still write the dashboard."""
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    res = generate_admin_dashboard(tmp_vault, now_iso="2026-04-14T00:00:00+00:00")
    path = tmp_vault / _DASHBOARD_ADMIN_PATH
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Capture service not configured" in text
    assert res.written == 0


def test_generate_admin_dashboard_happy_path(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    # Service returns six responses in this order: system-health, queue-health,
    # delivery-failures, pending-approvals, stale-sync-devices, mobile-devices (Task 42).
    responses = [
        (200, {
            "overall_status": "warn",
            "doctor": {"counts": {"ok": 5, "warn": 1, "fail": 0, "skip": 0}, "checks": []},
            "queue": {"enabled": True, "reachable": True, "error_rate": 0.1, "since_hours": 24},
            "deliveries": {"failure_count": 2, "since_hours": 24},
            "approvals": {"pending_count": 1},
            "devices": {"stale_count": 1, "threshold_hours": 24},
        }),
        (200, {
            "enabled": True, "reachable": True,
            "counts": {"pending": 2, "done": 20, "failed": 1},
            "oldest_pending_age_seconds": 30,
            "error_rate": 0.1,
            "since_hours": 24,
        }),
        (200, {
            "since_hours": 24,
            "limit": 100,
            "items": [
                {
                    "delivery_id": "dlv_x",
                    "action_id": "act_x",
                    "channel": "email",
                    "attempt": 1,
                    "status": "failed",
                    "last_error": "timeout",
                    "scheduled_at": "2026-04-14T09:00:00+00:00",
                    "action_title": "Email Dan",
                }
            ],
        }),
        (200, {
            "limit": 100,
            "items": [
                {
                    "delivery_id": "dlv_y",
                    "action_id": "act_y",
                    "channel": "sms",
                    "action_title": "SMS Sally",
                    "action_priority": "high",
                    "scheduled_at": "2026-04-14T10:00:00+00:00",
                }
            ],
        }),
        (200, {
            "threshold_hours": 24,
            "items": [
                {
                    "device_id": "iphone-15",
                    "platform": "ios",
                    "last_synced_at": "2026-04-10T00:00:00+00:00",
                    "hours_since_last_sync": 96.0,
                    "pending_ops_count": 2,
                }
            ],
        }),
        (200, {
            "ok": True,
            "devices": [
                {
                    "device_id": "iphone-15",
                    "device_label": "Mario's iPhone",
                    "platform": "ios",
                    "app_version": "1.0",
                    "first_seen_at": "2026-04-01T00:00:00+00:00",
                    "last_sync_at": "2026-04-10T00:00:00+00:00",
                    "pending_ops_count": 2,
                    "last_cursor": None,
                }
            ],
        }),
    ]
    _install_fake_http_sequence(monkeypatch, responses)

    res = generate_admin_dashboard(tmp_vault, now_iso="2026-04-14T00:00:00+00:00")
    path = tmp_vault / _DASHBOARD_ADMIN_PATH
    text = path.read_text(encoding="utf-8")
    assert "WARN" in text.upper()
    assert "Email Dan" in text
    assert "SMS Sally" in text
    assert "iphone-15" in text
    assert "Mario's iPhone" in text
    # 1 failure + 1 approval + 1 stale-device + 1 mobile-device
    assert res.written == 4


def test_generate_admin_dashboard_service_error(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=500, body={"error": "boom"})

    res = generate_admin_dashboard(tmp_vault, now_iso="2026-04-14T00:00:00+00:00")
    path = tmp_vault / _DASHBOARD_ADMIN_PATH
    text = path.read_text(encoding="utf-8")
    # Either error banner or empty sections is fine; ensure the file exists
    # and we wrote *something*.
    assert path.exists()
    assert "# Admin" in text
    assert res.written == 0


# ---------------------------------------------------------------------------
# CLI human + JSON output
# ---------------------------------------------------------------------------


def test_cli_queue_health_human_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"enabled": True, "reachable": True,
              "counts": {"pending": 1}, "oldest_pending_age_seconds": 5,
              "error_rate": 0.0, "since_hours": 24},
    )
    from obsidian_connector.cli import main

    rc = main(["queue-health"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Queue health" in out


def test_cli_queue_health_json_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"enabled": False, "since_hours": 24},
    )
    from obsidian_connector.cli import main

    rc = main(["queue-health", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed.get("ok") is True
    assert parsed.get("command") == "queue-health"


def test_cli_delivery_failures_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"since_hours": 24, "limit": 100, "items": []},
    )
    from obsidian_connector.cli import main

    rc = main(["delivery-failures"])
    assert rc == 0
    assert "Delivery failures" in capsys.readouterr().out


def test_cli_pending_approvals_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"limit": 100, "items": []},
    )
    from obsidian_connector.cli import main

    rc = main(["pending-approvals"])
    assert rc == 0
    assert "Pending approvals" in capsys.readouterr().out


def test_cli_stale_sync_devices_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"threshold_hours": 24, "items": []},
    )
    from obsidian_connector.cli import main

    rc = main(["stale-sync-devices"])
    assert rc == 0
    assert "Stale sync devices" in capsys.readouterr().out


def test_cli_system_health_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={
            "overall_status": "ok",
            "generated_at": "2026-04-14T00:00:00+00:00",
            "doctor": {"counts": {"ok": 3, "warn": 0, "fail": 0, "skip": 1}, "checks": []},
            "queue": {"enabled": False, "reachable": False, "error_rate": 0.0},
            "deliveries": {"failure_count": 0, "since_hours": 24},
            "approvals": {"pending_count": 0},
            "devices": {"stale_count": 0, "threshold_hours": 24},
        },
    )
    from obsidian_connector.cli import main

    rc = main(["system-health"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "System health" in out
    assert "OK" in out.upper()


def test_cli_system_health_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"overall_status": "fail", "generated_at": "x",
              "doctor": {}, "queue": {}, "deliveries": {},
              "approvals": {}, "devices": {}},
    )
    from obsidian_connector.cli import main

    rc = main(["system-health", "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed.get("command") == "system-health"


# ---------------------------------------------------------------------------
# MCP tool passthrough
# ---------------------------------------------------------------------------


def test_mcp_queue_health_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"enabled": True, "reachable": True, "counts": {}},
    )
    from obsidian_connector.mcp_server import obsidian_queue_health

    raw = obsidian_queue_health()
    parsed = json.loads(raw)
    assert parsed.get("ok") is True
    assert parsed.get("data", {}).get("enabled") is True


def test_mcp_delivery_failures_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"items": []})
    from obsidian_connector.mcp_server import obsidian_delivery_failures

    raw = obsidian_delivery_failures(since_hours=12, limit=25)
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_pending_approvals_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"items": []})
    from obsidian_connector.mcp_server import obsidian_pending_approvals

    raw = obsidian_pending_approvals(limit=30)
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_stale_sync_devices_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"items": []})
    from obsidian_connector.mcp_server import obsidian_stale_sync_devices

    raw = obsidian_stale_sync_devices(threshold_hours=48)
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_system_health_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"overall_status": "ok"},
    )
    from obsidian_connector.mcp_server import obsidian_system_health

    raw = obsidian_system_health()
    parsed = json.loads(raw)
    assert parsed.get("ok") is True
    assert parsed.get("data", {}).get("overall_status") == "ok"


# ---------------------------------------------------------------------------
# update_all_dashboards integration (include_admin kwarg)
# ---------------------------------------------------------------------------


def test_update_all_dashboards_includes_admin_by_default(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin dashboard should be produced even when the service URL is missing."""
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    from obsidian_connector.commitment_dashboards import update_all_dashboards

    results = update_all_dashboards(tmp_vault, now_iso="2026-04-14T00:00:00+00:00")
    paths = [str(r.path) for r in results]
    assert any(p.endswith("Admin.md") for p in paths)


def test_update_all_dashboards_skips_admin_when_opted_out(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    from obsidian_connector.commitment_dashboards import update_all_dashboards

    results = update_all_dashboards(
        tmp_vault,
        now_iso="2026-04-14T00:00:00+00:00",
        include_admin=False,
    )
    paths = [str(r.path) for r in results]
    assert not any(p.endswith("Admin.md") for p in paths)
