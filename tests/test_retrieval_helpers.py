"""Tests for Task 28 service-retrieval helpers.

Covers the three thin wrappers in :mod:`obsidian_connector.commitment_ops`,
the MCP tools, and the CLI subcommands. HTTP is always mocked via
``monkeypatch`` — no real network traffic.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout

import pytest

from obsidian_connector import commitment_ops


# ---------------------------------------------------------------------------
# HTTP mock
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body


class _FakeConnection:
    """Records request args and returns a canned response."""

    def __init__(self, netloc: str, *, timeout: float = 10.0, **_: object) -> None:
        self.netloc = netloc
        self.timeout = timeout
        self.requests: list[dict[str, object]] = []
        # Injected by the factory.
        self.response_status = 200
        self.response_body = "{}"

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.requests.append(
            {"method": method, "path": path, "body": body, "headers": dict(headers or {})}
        )

    def getresponse(self) -> _FakeResponse:
        return _FakeResponse(self.response_status, self.response_body)

    def close(self) -> None:  # pragma: no cover - no resource
        pass


def _install_fake_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: int = 200,
    body: dict | None = None,
) -> list[_FakeConnection]:
    """Patch ``http.client.HTTPConnection`` and ``HTTPSConnection``.

    Returns the list that all created connections are appended into so
    tests can assert on the captured request args.
    """
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
# list_service_actions
# ---------------------------------------------------------------------------


def test_list_service_actions_builds_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-123")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "items": [], "next_cursor": None},
    )

    result = commitment_ops.list_service_actions(
        status="open",
        project="Board Deck",
        person="alice",
        urgency="elevated",
        limit=25,
    )

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["data"] == {"ok": True, "items": [], "next_cursor": None}
    assert len(made) == 1
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"].startswith("/api/v1/actions?")
    # Query params present and URL-encoded.
    assert "status=open" in req["path"]
    assert "project=Board+Deck" in req["path"] or "project=Board%20Deck" in req["path"]
    assert "person=alice" in req["path"]
    assert "urgency=elevated" in req["path"]
    assert "limit=25" in req["path"]
    # Auth header
    assert req["headers"].get("Authorization") == "Bearer tok-123"
    assert req["headers"].get("Accept") == "application/json"


def test_list_service_actions_no_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", raising=False)
    made = _install_fake_http(
        monkeypatch, body={"ok": True, "items": []}
    )

    result = commitment_ops.list_service_actions()
    assert result["ok"] is True
    # Only the default limit is emitted.
    assert made[0].requests[0]["path"] == "/api/v1/actions?limit=50"
    # No auth header when no token is configured.
    assert "Authorization" not in made[0].requests[0]["headers"]


def test_list_service_actions_cursor_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"ok": True, "items": []})

    commitment_ops.list_service_actions(cursor="abc-opaque-token", limit=10)
    path = made[0].requests[0]["path"]
    assert "cursor=abc-opaque-token" in path
    assert "limit=10" in path


def test_list_service_actions_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=401, body={"error": "unauth"})

    result = commitment_ops.list_service_actions()
    assert result["ok"] is False
    assert result["status_code"] == 401


def test_list_service_actions_missing_url() -> None:
    import os
    # Clear env just for this test's scope.
    prior = os.environ.pop("OBSIDIAN_CAPTURE_SERVICE_URL", None)
    try:
        result = commitment_ops.list_service_actions()
        assert result["ok"] is False
        assert "service not configured" in result["error"]
    finally:
        if prior is not None:
            os.environ["OBSIDIAN_CAPTURE_SERVICE_URL"] = prior


def test_list_service_actions_bad_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "file:///etc/passwd")
    result = commitment_ops.list_service_actions()
    assert result["ok"] is False
    assert "must use http or https" in result["error"]


def test_list_service_actions_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    # Swap factory to one that returns non-JSON.
    class _BadConn(_FakeConnection):
        pass

    def _factory(netloc, **kw):
        c = _BadConn(netloc, **kw)
        c.response_status = 200
        c.response_body = "<not json>"
        return c

    import http.client as hc
    monkeypatch.setattr(hc, "HTTPConnection", _factory)

    result = commitment_ops.list_service_actions()
    assert result["ok"] is False
    assert "malformed" in result["error"]


def test_list_service_actions_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")

    class _BrokenConn:
        def __init__(self, *a, **kw) -> None:
            pass

        def request(self, *a, **kw) -> None:
            raise OSError("connection refused")

        def getresponse(self):  # pragma: no cover - never reached
            raise AssertionError

        def close(self) -> None:
            pass

    import http.client as hc
    monkeypatch.setattr(hc, "HTTPConnection", _BrokenConn)

    result = commitment_ops.list_service_actions()
    assert result["ok"] is False
    assert "unreachable" in result["error"]


def test_list_service_actions_service_url_arg_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://from-env")
    made = _install_fake_http(monkeypatch, body={})
    commitment_ops.list_service_actions(service_url="http://from-arg")
    assert made[0].netloc == "from-arg"


def test_list_service_actions_token_arg_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "env-tok")
    made = _install_fake_http(monkeypatch, body={})
    commitment_ops.list_service_actions(token="arg-tok")
    assert made[0].requests[0]["headers"]["Authorization"] == "Bearer arg-tok"


# ---------------------------------------------------------------------------
# get_service_action
# ---------------------------------------------------------------------------


def test_get_service_action_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "action": {"action_id": "act_ABC"}},
    )

    result = commitment_ops.get_service_action("act_ABC")
    assert result["ok"] is True
    assert result["data"]["action"]["action_id"] == "act_ABC"
    assert made[0].requests[0]["path"] == "/api/v1/actions/act_ABC"


def test_get_service_action_url_encodes_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    made = _install_fake_http(monkeypatch, body={})
    commitment_ops.get_service_action("weird id/with slash")
    path = made[0].requests[0]["path"]
    assert "/api/v1/actions/weird%20id%2Fwith%20slash" == path


def test_get_service_action_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(monkeypatch, status=404, body={"error": "not found"})
    result = commitment_ops.get_service_action("act_missing")
    assert result["ok"] is False
    assert result["status_code"] == 404


def test_get_service_action_empty_id_rejected() -> None:
    result = commitment_ops.get_service_action("")
    assert result["ok"] is False
    assert "non-empty string" in result["error"]


# ---------------------------------------------------------------------------
# get_service_action_stats
# ---------------------------------------------------------------------------


def test_get_service_action_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "total": 5, "by_status": {"open": 3}},
    )
    result = commitment_ops.get_service_action_stats()
    assert result["ok"] is True
    assert result["data"]["total"] == 5
    assert made[0].requests[0]["path"] == "/api/v1/actions/stats"


# ---------------------------------------------------------------------------
# MCP tool layer — the tools are thin wrappers, but we confirm passthrough.
# ---------------------------------------------------------------------------


def test_mcp_find_commitments_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(
        monkeypatch, body={"ok": True, "items": [{"title": "X"}]}
    )
    from obsidian_connector import mcp_server

    out = mcp_server.obsidian_find_commitments(project="P")
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["data"]["items"][0]["title"] == "X"


def test_mcp_commitment_detail_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "action": {"action_id": "act_XY"}},
    )
    from obsidian_connector import mcp_server

    out = mcp_server.obsidian_commitment_detail("act_XY")
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["data"]["action"]["action_id"] == "act_XY"


def test_mcp_commitment_stats_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(
        monkeypatch, body={"ok": True, "total": 10}
    )
    from obsidian_connector import mcp_server

    out = mcp_server.obsidian_commitment_stats()
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["data"]["total"] == 10


# ---------------------------------------------------------------------------
# CLI dispatcher (in-process via main())
# ---------------------------------------------------------------------------


def _run_cli(argv: list[str]) -> tuple[int, str]:
    from obsidian_connector import cli as _cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = _cli.main(argv)
    return code, buf.getvalue()


def test_cli_find_commitments_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(
        monkeypatch,
        body={
            "ok": True,
            "items": [
                {
                    "action_id": "act_A",
                    "title": "Pay bills",
                    "status": "open",
                    "priority": "high",
                    "urgency": "elevated",
                    "lifecycle_stage": "active",
                    "due_at": "2026-04-20T00:00:00+00:00",
                    "projects": ["Household"],
                    "people": [],
                    "areas": [],
                    "source_app": "wispr_flow",
                    "source_entrypoint": "voice",
                    "created_at": "2026-04-14T00:00:00+00:00",
                    "updated_at": "2026-04-14T00:00:00+00:00",
                }
            ],
            "next_cursor": None,
        },
    )

    code, out = _run_cli(["find-commitments", "--status", "open", "--json"])
    assert code == 0
    data = json.loads(out)
    # success_envelope wraps in data.<command> under "data".
    assert data["ok"] is True


def test_cli_find_commitments_human(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(
        monkeypatch,
        body={
            "ok": True,
            "items": [
                {
                    "action_id": "act_A",
                    "title": "Pay bills",
                    "status": "open",
                    "priority": "high",
                    "urgency": "elevated",
                    "lifecycle_stage": "active",
                    "due_at": "2026-04-20T00:00:00+00:00",
                }
            ],
            "next_cursor": "page-2",
        },
    )

    code, out = _run_cli(["find-commitments"])
    assert code == 0
    assert "Found 1 commitment(s)" in out
    assert "Pay bills" in out
    assert "elevated" in out
    assert "next_cursor: page-2" in out


def test_cli_commitment_detail_human(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(
        monkeypatch,
        body={
            "ok": True,
            "action": {
                "action_id": "act_XY",
                "title": "Do the thing",
                "status": "open",
                "priority": "normal",
                "urgency": "normal",
                "lifecycle_stage": "inbox",
                "projects": ["Proj"],
                "people": ["Alice"],
                "areas": [],
                "deliveries": [
                    {
                        "channel": "vault",
                        "status": "queued",
                        "scheduled_at": "2026-04-15T00:00:00+00:00",
                    }
                ],
            },
        },
    )

    code, out = _run_cli(["commitment-detail", "--action-id", "act_XY"])
    assert code == 0
    assert "Do the thing" in out
    assert "act_XY" in out
    assert "projects:  Proj" in out
    assert "people:    Alice" in out
    assert "vault: queued" in out


def test_cli_commitment_stats_human(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    _install_fake_http(
        monkeypatch,
        body={
            "ok": True,
            "total": 3,
            "by_status": {"open": 2, "done": 1},
            "by_lifecycle_stage": {"inbox": 1, "active": 1, "done": 1},
            "by_priority": {"normal": 3},
            "by_source_app": {"wispr_flow": 3},
        },
    )

    code, out = _run_cli(["commitment-stats"])
    assert code == 0
    assert "Total actions: 3" in out
    assert "open: 2" in out
    assert "wispr_flow: 3" in out


def test_cli_find_commitments_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    code, out = _run_cli(["find-commitments"])
    assert code == 0  # the wrapper returns an envelope, not a raise
    assert "Find failed" in out
    assert "service not configured" in out


def test_cli_commitment_detail_requires_action_id() -> None:
    # Missing required --action-id -> argparse exits with 2.
    from obsidian_connector import cli as _cli

    with pytest.raises(SystemExit) as exc_info:
        _cli.main(["commitment-detail"])
    assert exc_info.value.code == 2


def test_cli_find_commitments_filter_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every CLI filter flag flows through to the HTTP request."""
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host")
    made = _install_fake_http(monkeypatch, body={"ok": True, "items": []})

    code, _ = _run_cli(
        [
            "find-commitments",
            "--status", "open",
            "--lifecycle-stage", "active",
            "--project", "Board",
            "--person", "Alice",
            "--area", "Finance",
            "--urgency", "elevated",
            "--priority", "high",
            "--source-app", "wispr_flow",
            "--due-before", "2026-05-01T00:00:00Z",
            "--due-after", "2026-04-01T00:00:00Z",
            "--limit", "75",
            "--cursor", "opaque-cursor",
        ]
    )
    assert code == 0
    path = made[0].requests[0]["path"]
    for needle in [
        "status=open",
        "lifecycle_stage=active",
        "urgency=elevated",
        "priority=high",
        "source_app=wispr_flow",
        "limit=75",
        "cursor=opaque-cursor",
    ]:
        assert needle in path, f"missing {needle} in {path}"
