"""Task 42: tests for mobile-devices + forget-mobile-device helpers.

Covers the two new `admin_ops` wrappers, their MCP passthroughs, the two
CLI subcommands (human + JSON + confirmation flow), and the extension
of the admin dashboard with the new "Mobile devices" section. HTTP is
mocked; no real traffic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector import admin_ops
from obsidian_connector.commitment_dashboards import (
    _render_admin_md,
    generate_admin_dashboard,
    _DASHBOARD_ADMIN_PATH,
)


# ---------------------------------------------------------------------------
# Shared HTTP fake (same pattern as test_admin_helpers)
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


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    (tmp_path / "Dashboards").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# admin_ops.list_mobile_devices
# ---------------------------------------------------------------------------


def test_list_mobile_devices_calls_correct_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-42")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "devices": []},
    )
    result = admin_ops.list_mobile_devices()
    assert result["ok"] is True
    assert result["data"] == {"ok": True, "devices": []}
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"] == "/api/v1/mobile/devices"
    assert req["headers"].get("Authorization") == "Bearer tok-42"


def test_list_mobile_devices_no_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    r = admin_ops.list_mobile_devices()
    assert r["ok"] is False
    assert "service not configured" in r["error"]


def test_list_mobile_devices_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=500, body={"error": "boom"})
    r = admin_ops.list_mobile_devices()
    assert r["ok"] is False
    assert r["status_code"] == 500


def test_list_mobile_devices_unpacks_devices_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    devices = [
        {"device_id": "a", "device_label": "Phone", "platform": "ios"},
        {"device_id": "b", "device_label": "Watch", "platform": "watchos"},
    ]
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "devices": devices},
    )
    r = admin_ops.list_mobile_devices()
    assert r["ok"] is True
    assert r["data"]["devices"] == devices


# ---------------------------------------------------------------------------
# admin_ops.forget_mobile_device
# ---------------------------------------------------------------------------


def test_forget_mobile_device_posts_to_correct_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "device_id": "iph-1", "deleted": True, "cancelled_ops": 3},
    )
    r = admin_ops.forget_mobile_device("iph-1")
    assert r["ok"] is True
    assert r["data"]["deleted"] is True
    assert r["data"]["cancelled_ops"] == 3
    req = made[0].requests[0]
    assert req["method"] == "POST"
    assert req["path"] == "/api/v1/mobile/devices/iph-1/forget"


def test_forget_mobile_device_url_encodes_device_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "deleted": True},
    )
    admin_ops.forget_mobile_device("weird id/with/slashes")
    path = made[0].requests[0]["path"]
    assert "/forget" in path
    assert "weird%20id%2Fwith%2Fslashes" in path


def test_forget_mobile_device_blank_id_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"ok": True})
    r = admin_ops.forget_mobile_device("")
    assert r["ok"] is False
    assert "non-empty" in r["error"]
    assert made == []  # no HTTP was issued


def test_forget_mobile_device_no_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    r = admin_ops.forget_mobile_device("iph-1")
    assert r["ok"] is False


def test_forget_mobile_device_missing_id_idempotent_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service returns 200 + deleted=False on a missing id; wrapper passes through."""
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "device_id": "gone", "deleted": False, "cancelled_ops": 0},
    )
    r = admin_ops.forget_mobile_device("gone")
    assert r["ok"] is True
    assert r["data"]["deleted"] is False
    assert r["data"]["cancelled_ops"] == 0


# ---------------------------------------------------------------------------
# MCP passthrough
# ---------------------------------------------------------------------------


def test_mcp_mobile_devices_passes_through_admin_ops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "devices": [{"device_id": "a"}]},
    )
    from obsidian_connector.mcp_server import obsidian_mobile_devices

    out = obsidian_mobile_devices()
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["data"]["devices"][0]["device_id"] == "a"


def test_mcp_forget_mobile_device_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "device_id": "iph-2", "deleted": True, "cancelled_ops": 1},
    )
    from obsidian_connector.mcp_server import obsidian_forget_mobile_device

    out = obsidian_forget_mobile_device("iph-2")
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["data"]["deleted"] is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_mobile_devices_human_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={
            "ok": True,
            "devices": [
                {
                    "device_id": "iph-3",
                    "device_label": "Mario's iPhone",
                    "platform": "ios",
                    "app_version": "1.0",
                    "first_seen_at": "2026-04-01T00:00:00+00:00",
                    "last_sync_at": "2026-04-14T00:00:00+00:00",
                    "pending_ops_count": 2,
                    "last_cursor": "sop_123",
                }
            ],
        },
    )
    from obsidian_connector.cli import main

    rc = main(["mobile-devices"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Mario's iPhone" in out
    assert "ios" in out
    assert "iph-3" in out
    assert "pending ops: 2" in out


def test_cli_mobile_devices_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "devices": []},
    )
    from obsidian_connector.cli import main

    rc = main(["mobile-devices", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed.get("ok") is True


def test_cli_mobile_devices_empty_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "devices": []},
    )
    from obsidian_connector.cli import main

    main(["mobile-devices"])
    out = capsys.readouterr().out
    assert "no devices registered" in out.lower()


def test_cli_forget_mobile_device_with_yes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--yes skips the interactive prompt and issues the POST."""
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "device_id": "iph-4", "deleted": True, "cancelled_ops": 5},
    )
    from obsidian_connector.cli import main

    rc = main(["forget-mobile-device", "--device-id", "iph-4", "--yes"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "iph-4" in out
    assert "5 pending op(s) cancelled" in out
    assert made[0].requests[0]["method"] == "POST"


def test_cli_forget_mobile_device_user_cancels(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without --yes and without --json, the user is prompted; N aborts.

    On cancellation the command prints ``Cancelled.`` and issues no
    HTTP. The envelope's ``ok`` key is False (it carries the
    cancellation error), so ``main()`` may still return 0 -- the
    important invariants are that the fake HTTP was never called and
    the user saw the cancellation message.
    """
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "deleted": True},
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    from obsidian_connector.cli import main

    main(["forget-mobile-device", "--device-id", "iph-5"])
    out = capsys.readouterr().out
    assert "Cancelled" in out
    assert made == []  # no HTTP issued


def test_cli_forget_mobile_device_json_skips_prompt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--json mode must not prompt interactively even without --yes."""
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "device_id": "iph-6", "deleted": True, "cancelled_ops": 0},
    )
    # If input() is called, fail the test loudly
    monkeypatch.setattr("builtins.input", lambda _prompt: pytest.fail("should not prompt"))

    from obsidian_connector.cli import main

    rc = main(["forget-mobile-device", "--device-id", "iph-6", "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed.get("ok") is True
    assert made[0].requests[0]["method"] == "POST"


# ---------------------------------------------------------------------------
# Dashboard extension
# ---------------------------------------------------------------------------


def test_render_admin_md_includes_mobile_devices_section() -> None:
    out = _render_admin_md(
        now_iso="2026-04-14T00:00:00+00:00",
        system_health_payload=None,
        queue_health_payload=None,
        delivery_failures_items=None,
        pending_approvals_items=None,
        stale_devices_items=None,
        mobile_devices_items=[
            {
                "device_id": "iph-wk",
                "device_label": "Mario's iPhone",
                "platform": "ios",
                "app_version": "1.0",
                "first_seen_at": "2026-04-01T00:00:00+00:00",
                "last_sync_at": "2026-04-14T00:00:00+00:00",
                "pending_ops_count": 0,
            }
        ],
        service_configured=True,
        service_error=None,
    )
    assert "## Mobile devices" in out
    assert "Mario's iPhone" in out
    assert "iph-wk" in out


def test_render_admin_md_mobile_section_placeholder_no_items() -> None:
    out = _render_admin_md(
        now_iso="2026-04-14T00:00:00+00:00",
        system_health_payload=None,
        queue_health_payload=None,
        delivery_failures_items=None,
        pending_approvals_items=None,
        stale_devices_items=None,
        mobile_devices_items=[],
        service_configured=True,
        service_error=None,
    )
    assert "## Mobile devices" in out
    assert "No mobile devices registered" in out


def test_render_admin_md_mobile_section_unconfigured() -> None:
    out = _render_admin_md(
        now_iso="2026-04-14T00:00:00+00:00",
        system_health_payload=None,
        queue_health_payload=None,
        delivery_failures_items=None,
        pending_approvals_items=None,
        stale_devices_items=None,
        mobile_devices_items=None,
        service_configured=False,
        service_error=None,
    )
    assert "## Mobile devices" in out
    assert "service not configured" in out.lower()


def test_generate_admin_dashboard_surfaces_mobile_devices(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    # Every admin fetch returns an empty payload except the new one.
    # The fake http returns the same body to every request, which is fine
    # because each wrapper pulls only what it expects from the shape.
    _install_fake_http(
        monkeypatch,
        body={
            "ok": True,
            "items": [],
            "devices": [
                {
                    "device_id": "iph-all",
                    "device_label": "Mario Phone",
                    "platform": "ios",
                    "app_version": "1.0",
                    "first_seen_at": "2026-04-01T00:00:00+00:00",
                    "last_sync_at": "2026-04-14T00:00:00+00:00",
                    "pending_ops_count": 0,
                }
            ],
            "threshold_hours": 24,
            "since_hours": 24,
            "limit": 100,
            "enabled": False,
            "counts": {},
        },
    )
    res = generate_admin_dashboard(tmp_vault, now_iso="2026-04-14T00:00:00+00:00")
    path = tmp_vault / _DASHBOARD_ADMIN_PATH
    text = path.read_text(encoding="utf-8")
    assert "## Mobile devices" in text
    assert "iph-all" in text
    assert res.written >= 1


def test_generate_admin_dashboard_mobile_section_banner_when_unconfigured(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    res = generate_admin_dashboard(tmp_vault, now_iso="2026-04-14T00:00:00+00:00")
    path = tmp_vault / _DASHBOARD_ADMIN_PATH
    text = path.read_text(encoding="utf-8")
    assert "## Mobile devices" in text
    assert res.written == 0
