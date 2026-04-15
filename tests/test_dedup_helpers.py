"""Tests for Task 21.B dedup helpers.

Covers the two thin wrappers in :mod:`obsidian_connector.commitment_ops`
(``list_duplicate_candidates``, ``merge_commitments``), the MCP tool
surfaces, and the ``duplicate-candidates`` + ``merge-commitment`` CLI
subcommands. HTTP is mocked via ``monkeypatch`` — no real traffic.

The HTTP fake mirrors the one in ``tests/test_retrieval_helpers.py``;
duplicating it locally keeps the tests independent.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout

import pytest

from obsidian_connector import commitment_ops


# ---------------------------------------------------------------------------
# HTTP mock (matches test_retrieval_helpers.py shape)
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
        self.requests.append(
            {
                "method": method,
                "path": path,
                "body": body,
                "headers": dict(headers or {}),
            }
        )

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
# list_duplicate_candidates — Python helper
# ---------------------------------------------------------------------------


def test_duplicate_candidates_builds_query_and_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-abc")
    body = {
        "ok": True, "action_id": "act_x", "candidates": [],
        "thresholds": {"candidate": 0.55, "strong": 0.80},
    }
    made = _install_fake_http(monkeypatch, body=body)

    result = commitment_ops.list_duplicate_candidates(
        "act_x", limit=5, within_days=14, min_score=0.6,
    )

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["data"] == body
    assert len(made) == 1
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"].startswith(
        "/api/v1/actions/act_x/duplicate-candidates?"
    )
    assert "limit=5" in req["path"]
    assert "within_days=14" in req["path"]
    assert "min_score=0.6" in req["path"]


def test_duplicate_candidates_passes_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-zzz")
    made = _install_fake_http(monkeypatch, body={"ok": True, "candidates": []})

    commitment_ops.list_duplicate_candidates("act_a")

    headers = made[0].requests[0]["headers"]
    assert headers.get("Authorization") == "Bearer tok-zzz"


def test_duplicate_candidates_default_query_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"ok": True, "candidates": []})

    commitment_ops.list_duplicate_candidates("act_a")
    path = made[0].requests[0]["path"]
    assert "limit=10" in path
    assert "within_days=30" in path
    # min_score omitted when caller doesn't override.
    assert "min_score=" not in path


def test_duplicate_candidates_handles_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=404, body={"detail": "not found"})

    result = commitment_ops.list_duplicate_candidates("act_missing")
    assert result["ok"] is False
    assert result["status_code"] == 404


def test_duplicate_candidates_requires_action_id() -> None:
    result = commitment_ops.list_duplicate_candidates("")
    assert result["ok"] is False
    assert "action_id" in result["error"]


def test_duplicate_candidates_missing_service_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = commitment_ops.list_duplicate_candidates("act_x")
    assert result["ok"] is False
    assert "service not configured" in result["error"]


def test_duplicate_candidates_url_override_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Env says host A, override says host B.
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host-env:8787")
    made = _install_fake_http(monkeypatch, body={"ok": True, "candidates": []})
    commitment_ops.list_duplicate_candidates(
        "act_x", service_url="http://host-override:8787",
    )
    assert made[0].netloc == "host-override:8787"


# ---------------------------------------------------------------------------
# merge_commitments — Python helper
# ---------------------------------------------------------------------------


def test_merge_commitments_posts_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-merge")
    body = {
        "ok": True, "loser_id": "act_l", "winner_id": "act_w",
        "edge_id": "edg_1", "already_merged": False,
    }
    made = _install_fake_http(monkeypatch, body=body)

    result = commitment_ops.merge_commitments("act_l", "act_w")
    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["data"] == body
    req = made[0].requests[0]
    assert req["method"] == "POST"
    assert req["path"] == "/api/v1/actions/act_l/merge"
    sent = json.loads(req["body"].decode("utf-8"))
    assert sent == {"winner_id": "act_w"}
    headers = req["headers"]
    assert headers.get("Content-Type") == "application/json"
    assert headers.get("Authorization") == "Bearer tok-merge"


def test_merge_commitments_409_surfaces_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=409, body={"detail": "terminal"})

    result = commitment_ops.merge_commitments("act_l", "act_w")
    assert result["ok"] is False
    assert result["status_code"] == 409


def test_merge_commitments_rejects_empty_ids() -> None:
    assert commitment_ops.merge_commitments("", "act_w")["ok"] is False
    assert commitment_ops.merge_commitments("act_l", "")["ok"] is False


def test_merge_commitments_missing_service_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = commitment_ops.merge_commitments("act_l", "act_w")
    assert result["ok"] is False
    assert "service not configured" in result["error"]


def test_merge_commitments_already_merged_flag_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "loser_id": "act_l", "winner_id": "act_w",
        "edge_id": "edg_a", "already_merged": True,
    }
    _install_fake_http(monkeypatch, body=body)
    result = commitment_ops.merge_commitments("act_l", "act_w")
    assert result["data"]["already_merged"] is True


# ---------------------------------------------------------------------------
# MCP tool wrappers
# ---------------------------------------------------------------------------


def test_mcp_duplicate_candidates_returns_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={
            "ok": True, "action_id": "act_x", "candidates": [],
            "thresholds": {"candidate": 0.55, "strong": 0.8},
        },
    )
    from obsidian_connector import mcp_server

    out = mcp_server.obsidian_duplicate_candidates("act_x", limit=3)
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["data"]["thresholds"]["candidate"] == 0.55


def test_mcp_merge_commitment_returns_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={
            "ok": True, "loser_id": "act_l", "winner_id": "act_w",
            "edge_id": "edg_1", "already_merged": False,
        },
    )
    from obsidian_connector import mcp_server

    out = mcp_server.obsidian_merge_commitment("act_l", "act_w")
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert parsed["data"]["winner_id"] == "act_w"


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def _run_cli(argv: list[str]) -> tuple[int, str]:
    from obsidian_connector import cli

    buf = io.StringIO()
    rc = 0
    with redirect_stdout(buf):
        try:
            cli.main(argv)
        except SystemExit as exc:
            rc = int(exc.code or 0)
    return rc, buf.getvalue()


def test_cli_duplicate_candidates_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "action_id": "act_x", "candidates": [
            {
                "action_id": "act_peer", "title": "Peer", "status": "open",
                "lifecycle_stage": "inbox", "project": None,
                "source_app": "wispr_flow", "due_at": None,
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "score": 0.77, "tier": "candidate",
                "reasons": {
                    "title_jaccard": 0.5, "same_project": False,
                    "shared_people": [], "shared_areas": [],
                    "days_apart": 1.0, "due_close": False,
                },
            }
        ],
        "thresholds": {"candidate": 0.55, "strong": 0.80},
    }
    _install_fake_http(monkeypatch, body=body)

    rc, out = _run_cli([
        "duplicate-candidates", "--action-id", "act_x", "--json",
    ])
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["ok"] is True


def test_cli_duplicate_candidates_human(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "action_id": "act_x", "candidates": [],
        "thresholds": {"candidate": 0.55, "strong": 0.80},
    }
    _install_fake_http(monkeypatch, body=body)
    rc, out = _run_cli([
        "duplicate-candidates", "--action-id", "act_x",
    ])
    assert rc == 0
    assert "Duplicate candidates for act_x" in out
    assert "no candidates above min_score" in out


def test_cli_merge_commitment_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "loser_id": "act_l", "winner_id": "act_w",
        "edge_id": "edg_1", "already_merged": False,
    }
    _install_fake_http(monkeypatch, body=body)
    rc, out = _run_cli([
        "merge-commitment", "--loser", "act_l", "--winner", "act_w",
    ])
    assert rc == 0
    assert "Merge applied" in out
    assert "edg_1" in out


def test_cli_merge_commitment_already_merged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True, "loser_id": "act_l", "winner_id": "act_w",
        "edge_id": "edg_a", "already_merged": True,
    }
    _install_fake_http(monkeypatch, body=body)
    rc, out = _run_cli([
        "merge-commitment", "--loser", "act_l", "--winner", "act_w",
    ])
    assert rc == 0
    assert "Merge already applied" in out


def test_cli_merge_commitment_409_surfaces_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=409, body={"detail": "terminal"})
    rc, out = _run_cli([
        "merge-commitment", "--loser", "act_l", "--winner", "act_w",
    ])
    assert rc == 0  # CLI surfaces the failure in the text output, no raise
    assert "Merge failed" in out


def test_cli_duplicate_candidates_service_url_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    made = _install_fake_http(
        monkeypatch,
        body={
            "ok": True, "action_id": "act_x", "candidates": [],
            "thresholds": {"candidate": 0.55, "strong": 0.80},
        },
    )
    rc, _ = _run_cli([
        "duplicate-candidates", "--action-id", "act_x",
        "--service-url", "http://explicit:9999",
    ])
    assert rc == 0
    assert made[0].netloc == "explicit:9999"
