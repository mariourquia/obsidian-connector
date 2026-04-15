"""Tests for Task 36 approval UX wrappers, MCP, CLI, and dashboard.

Covers:

- HTTP wrappers in :mod:`obsidian_connector.approval_ops` (detail +
  bulk + digest), including no-raise envelope shape.
- MCP tool passthrough to the wrappers.
- CLI subcommands human + JSON output.
- Approval dashboard rendering with/without service URL plus the
  real ``generate_approval_dashboard`` path against a sequence of
  mocked HTTP responses.

HTTP is mocked; no real traffic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector import approval_ops
from obsidian_connector.commitment_dashboards import (
    _DASHBOARD_APPROVALS_PATH,
    _render_approvals_md,
    generate_approval_dashboard,
)


# ---------------------------------------------------------------------------
# Shared HTTP fake (same pattern as tests/test_admin_helpers.py)
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
# get_delivery_detail
# ---------------------------------------------------------------------------


def test_detail_builds_path_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-d")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "delivery": {"delivery_id": "dlv_1"}},
    )
    r = approval_ops.get_delivery_detail("dlv_1")
    assert r["ok"] is True
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"] == "/api/v1/deliveries/dlv_1"
    assert req["headers"].get("Authorization") == "Bearer tok-d"


def test_detail_empty_id_does_not_hit_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = approval_ops.get_delivery_detail("")
    assert r["ok"] is False
    assert made == []


def test_detail_404_surfaces_status_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=404, body={"detail": "missing"})
    r = approval_ops.get_delivery_detail("dlv_missing")
    assert r["ok"] is False
    assert r["status_code"] == 404


def test_detail_missing_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    r = approval_ops.get_delivery_detail("dlv_1")
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# bulk_approve_deliveries + bulk_reject_deliveries
# ---------------------------------------------------------------------------


def test_bulk_approve_posts_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "approved",
              "requested": 2, "approved": [], "rejected": [], "skipped": []},
    )
    r = approval_ops.bulk_approve_deliveries(
        ["dlv_a", "dlv_b"], note="batch note",
    )
    assert r["ok"] is True
    req = made[0].requests[0]
    assert req["method"] == "POST"
    assert req["path"] == "/api/v1/deliveries/bulk-approve"
    body = json.loads(req["body"].decode("utf-8"))
    assert body["delivery_ids"] == ["dlv_a", "dlv_b"]
    assert body["note"] == "batch note"


def test_bulk_reject_posts_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "rejected",
              "requested": 1, "approved": [], "rejected": [], "skipped": []},
    )
    r = approval_ops.bulk_reject_deliveries(["dlv_z"])
    assert r["ok"] is True
    req = made[0].requests[0]
    assert req["path"] == "/api/v1/deliveries/bulk-reject"


def test_bulk_requires_nonempty_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = approval_ops.bulk_approve_deliveries([])
    assert r["ok"] is False
    assert made == []


def test_bulk_rejects_list_of_blank_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = approval_ops.bulk_approve_deliveries(["", ""])
    assert r["ok"] is False
    assert made == []


def test_bulk_surfaces_http_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch, status=400, body={"detail": "too many"},
    )
    r = approval_ops.bulk_approve_deliveries(["dlv_a"])
    assert r["ok"] is False
    assert r["status_code"] == 400


# ---------------------------------------------------------------------------
# get_approval_digest
# ---------------------------------------------------------------------------


def test_digest_builds_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"pending_total": 0, "counts_by_channel": {},
              "counts_by_urgency": {}, "top_pending": [],
              "since_hours": 12, "generated_at": "2026-04-14T00:00:00+00:00",
              "oldest_pending_age_seconds": None,
              "recent_decisions_count": 0},
    )
    r = approval_ops.get_approval_digest(since_hours=12)
    assert r["ok"] is True
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"].startswith("/api/v1/deliveries/approval-digest?")
    assert "since_hours=12" in req["path"]


def test_digest_default_since_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"pending_total": 0})
    approval_ops.get_approval_digest()
    assert "since_hours=24" in made[0].requests[0]["path"]


def test_digest_missing_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    r = approval_ops.get_approval_digest()
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# Approvals dashboard renderer (pure)
# ---------------------------------------------------------------------------


def test_render_approvals_md_not_configured() -> None:
    out = _render_approvals_md(
        now_iso="2026-04-14T00:00:00+00:00",
        digest_payload=None, detail_rows=None,
        recent_history_rows=None,
        service_configured=False, service_error=None,
    )
    assert "Capture service not configured" in out
    assert "# Approvals" in out
    assert "## Approval digest" in out
    assert "## Pending approvals with risk factors" in out
    assert "## Recent decisions" in out


def test_render_approvals_md_service_error_banner() -> None:
    out = _render_approvals_md(
        now_iso="2026-04-14T00:00:00+00:00",
        digest_payload=None, detail_rows=None,
        recent_history_rows=None,
        service_configured=True, service_error="connection refused",
    )
    assert "Capture service unreachable" in out
    assert "connection refused" in out


def test_render_approvals_md_digest_counts_render() -> None:
    out = _render_approvals_md(
        now_iso="2026-04-14T00:00:00+00:00",
        digest_payload={
            "pending_total": 5, "since_hours": 24,
            "counts_by_channel": {"email": 3, "sms": 2},
            "counts_by_urgency": {"elevated": 2, "normal": 3},
            "oldest_pending_age_seconds": 360,
            "recent_decisions_count": 7,
        },
        detail_rows=[],
        recent_history_rows=[],
        service_configured=True, service_error=None,
    )
    assert "Pending total" in out
    assert "5" in out
    assert "email=3" in out
    assert "elevated=2" in out
    assert "Recent decisions" in out
    assert "7" in out


def test_render_approvals_md_orders_rows_by_urgency_then_age() -> None:
    rows = [
        {  # normal / late
            "delivery": {"delivery_id": "dlv_n",
                         "scheduled_at": "2026-04-14T09:00:00+00:00",
                         "channel": "email"},
            "action": {"title": "Normal One", "urgency": "normal"},
            "risk_factors": [],
        },
        {  # critical / newer
            "delivery": {"delivery_id": "dlv_c",
                         "scheduled_at": "2026-04-14T11:00:00+00:00",
                         "channel": "email"},
            "action": {"title": "Critical One", "urgency": "critical"},
            "risk_factors": ["external_recipient"],
        },
    ]
    out = _render_approvals_md(
        now_iso="2026-04-14T00:00:00+00:00",
        digest_payload={"pending_total": 2, "since_hours": 24,
                        "counts_by_channel": {},
                        "counts_by_urgency": {},
                        "oldest_pending_age_seconds": None,
                        "recent_decisions_count": 0},
        detail_rows=rows,
        recent_history_rows=[],
        service_configured=True, service_error=None,
    )
    idx_critical = out.index("Critical One")
    idx_normal = out.index("Normal One")
    assert idx_critical < idx_normal


def test_render_approvals_md_with_recent_history() -> None:
    rows = [
        {
            "delivery": {"delivery_id": "dlv_x", "channel": "email"},
            "action": {"title": "Ping Alice"},
            "risk_factors": [],
        }
    ]
    history = [
        {
            "delivery_id": "dlv_x",
            "action_title": "Ping Alice",
            "decided_at": "2026-04-14T10:00:00+00:00",
            "decision": "approved",
            "channel": "email",
        }
    ]
    out = _render_approvals_md(
        now_iso="2026-04-14T11:00:00+00:00",
        digest_payload={"pending_total": 1, "since_hours": 24,
                        "counts_by_channel": {"email": 1},
                        "counts_by_urgency": {"normal": 1},
                        "oldest_pending_age_seconds": 60,
                        "recent_decisions_count": 1},
        detail_rows=rows, recent_history_rows=history,
        service_configured=True, service_error=None,
    )
    assert "Ping Alice" in out
    assert "approved" in out


# ---------------------------------------------------------------------------
# generate_approval_dashboard (integration)
# ---------------------------------------------------------------------------


def test_generate_approval_dashboard_without_service_url(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    res = generate_approval_dashboard(
        tmp_vault, now_iso="2026-04-14T00:00:00+00:00",
    )
    path = tmp_vault / _DASHBOARD_APPROVALS_PATH
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Capture service not configured" in text
    assert res.written == 0


def test_generate_approval_dashboard_happy_path(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    # Responses in order:
    #   1. approval-digest
    #   2. admin/pending-approvals
    #   3. deliveries/{dlv_a}
    responses = [
        (200, {
            "pending_total": 1, "since_hours": 24,
            "counts_by_channel": {"email": 1},
            "counts_by_urgency": {"elevated": 1},
            "oldest_pending_age_seconds": 60,
            "top_pending": [],
            "recent_decisions_count": 0,
            "generated_at": "2026-04-14T00:00:00+00:00",
        }),
        (200, {
            "limit": 100,
            "items": [{"delivery_id": "dlv_a", "action_id": "act_a",
                        "channel": "email",
                        "action_title": "Ping Alice"}],
        }),
        (200, {
            "delivery": {"delivery_id": "dlv_a", "action_id": "act_a",
                          "channel": "email",
                          "status": "pending_approval",
                          "target": "alice@example.com",
                          "scheduled_at": "2026-04-14T09:00:00+00:00",
                          "attempt": 0,
                          "created_at": "2026-04-14T08:00:00+00:00",
                          "updated_at": "2026-04-14T08:00:00+00:00"},
            "action": {"action_id": "act_a",
                        "title": "Ping Alice",
                        "status": "open",
                        "priority": "urgent",
                        "urgency": "elevated",
                        "lifecycle_stage": "triaged"},
            "risk_factors": ["external_recipient",
                              "first_delivery_to_channel"],
            "approval_history": [],
        }),
    ]
    _install_fake_http_sequence(monkeypatch, responses)

    res = generate_approval_dashboard(
        tmp_vault, now_iso="2026-04-14T00:00:00+00:00",
    )
    path = tmp_vault / _DASHBOARD_APPROVALS_PATH
    text = path.read_text(encoding="utf-8")
    assert "Ping Alice" in text
    assert "external_recipient" in text
    assert res.written == 1


def test_generate_approval_dashboard_partial_service_error(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the digest call fails we still render a dashboard with the error banner."""
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=500, body={"detail": "boom"})
    res = generate_approval_dashboard(
        tmp_vault, now_iso="2026-04-14T00:00:00+00:00",
    )
    path = tmp_vault / _DASHBOARD_APPROVALS_PATH
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "# Approvals" in text
    assert res.written == 0


# ---------------------------------------------------------------------------
# CLI human + JSON output
# ---------------------------------------------------------------------------


def test_cli_delivery_detail_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "delivery": {"delivery_id": "dlv_1", "channel": "email",
                     "status": "pending_approval",
                     "target": "alice@example.com",
                     "scheduled_at": "2026-04-14T09:00:00+00:00"},
        "action": {"title": "Ping Alice", "priority": "urgent",
                    "urgency": "elevated", "lifecycle_stage": "triaged"},
        "risk_factors": ["external_recipient"],
        "approval_history": [],
    })
    from obsidian_connector.cli import main

    rc = main(["delivery-detail", "--delivery-id", "dlv_1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Delivery dlv_1" in out
    assert "Ping Alice" in out
    assert "external_recipient" in out


def test_cli_delivery_detail_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"delivery": {"delivery_id": "d"}})
    from obsidian_connector.cli import main

    rc = main(["delivery-detail", "--delivery-id", "dlv_1", "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed.get("command") == "delivery-detail"


def test_cli_bulk_approve_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True, "decision": "approved", "requested": 2,
        "approved": [
            {"delivery_id": "a", "status": "queued"},
            {"delivery_id": "b", "status": "queued"},
        ],
        "rejected": [],
        "skipped": [],
    })
    from obsidian_connector.cli import main

    rc = main(["bulk-approve", "--delivery-ids", "a,b", "--note", "ok"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Bulk approve" in out
    assert "requested=2" in out
    assert "approved=2" in out


def test_cli_bulk_reject_skips_rendered(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True, "decision": "rejected", "requested": 2,
        "approved": [],
        "rejected": [{"delivery_id": "a", "status": "skipped"}],
        "skipped": [{"delivery_id": "missing",
                     "reason": "missing", "detail": "not found"}],
    })
    from obsidian_connector.cli import main

    rc = main(["bulk-reject", "--delivery-ids", "a,missing"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Bulk reject" in out
    assert "skip: missing" in out


def test_cli_approval_digest_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "pending_total": 3, "since_hours": 24,
        "counts_by_channel": {"email": 2, "sms": 1},
        "counts_by_urgency": {"normal": 3},
        "oldest_pending_age_seconds": 200,
        "top_pending": [
            {"delivery_id": "d1", "channel": "email",
             "action_title": "Ping", "urgency": "normal",
             "risk_factors": ["external_recipient"]},
        ],
        "recent_decisions_count": 1,
        "generated_at": "2026-04-14T00:00:00+00:00",
    })
    from obsidian_connector.cli import main

    rc = main(["approval-digest", "--since-hours", "24"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Approval digest" in out
    assert "email=2" in out
    assert "Ping" in out


def test_cli_approval_digest_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"pending_total": 0,
                                           "since_hours": 24})
    from obsidian_connector.cli import main

    rc = main(["approval-digest", "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed.get("command") == "approval-digest"


# ---------------------------------------------------------------------------
# MCP passthrough smoke
# ---------------------------------------------------------------------------


def test_mcp_delivery_detail_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"delivery": {"delivery_id": "d1"}})
    from obsidian_connector.mcp_server import obsidian_delivery_detail

    raw = obsidian_delivery_detail("d1")
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_bulk_approve_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True, "decision": "approved", "requested": 1,
        "approved": [{"delivery_id": "a", "status": "queued"}],
        "rejected": [], "skipped": [],
    })
    from obsidian_connector.mcp_server import obsidian_bulk_approve

    raw = obsidian_bulk_approve(["a"])
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_approval_digest_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"pending_total": 0, "since_hours": 24})
    from obsidian_connector.mcp_server import obsidian_approval_digest

    raw = obsidian_approval_digest(since_hours=24)
    parsed = json.loads(raw)
    assert parsed.get("ok") is True
