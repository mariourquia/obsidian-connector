"""Tests for Task 31 pattern-intelligence helpers.

Covers the three HTTP wrappers in :mod:`obsidian_connector.commitment_ops`
(``list_repeated_postponements``, ``list_blocker_clusters``,
``list_recurring_unfinished``), plus the Patterns dashboard renderer.
HTTP is mocked; no real traffic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector import commitment_ops
from obsidian_connector.commitment_dashboards import (
    _DASHBOARD_PATTERNS_PATH,
    _render_patterns_md,
    generate_patterns_dashboard,
)


# ---------------------------------------------------------------------------
# Shared HTTP fake (mirrors test_dedup_helpers.py / test_retrieval_helpers.py)
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
# list_repeated_postponements
# ---------------------------------------------------------------------------


def test_postponements_builds_query_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-pp")
    body = {"ok": True, "since_days": 14, "items": [{"action_id": "a1"}]}
    made = _install_fake_http(monkeypatch, body=body)

    result = commitment_ops.list_repeated_postponements(
        since_days=14, limit=25,
    )
    assert result["ok"] is True
    assert result["data"] == body

    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"].startswith(
        "/api/v1/patterns/repeated-postponements?"
    )
    assert "since_days=14" in req["path"]
    assert "limit=25" in req["path"]
    assert req["headers"].get("Authorization") == "Bearer tok-pp"


def test_postponements_defaults_window_and_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"ok": True, "items": []})

    commitment_ops.list_repeated_postponements()
    path = made[0].requests[0]["path"]
    assert "since_days=30" in path
    assert "limit=50" in path


def test_postponements_missing_service_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = commitment_ops.list_repeated_postponements()
    assert result["ok"] is False
    assert "service not configured" in result["error"]


def test_postponements_http_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=500, body={"error": "boom"})
    result = commitment_ops.list_repeated_postponements()
    assert result["ok"] is False
    assert result["status_code"] == 500


# ---------------------------------------------------------------------------
# list_blocker_clusters
# ---------------------------------------------------------------------------


def test_blocker_clusters_builds_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {
        "ok": True,
        "since_days": 45,
        "items": [{"blocker_action_id": "b1", "blocks_count": 3}],
    }
    made = _install_fake_http(monkeypatch, body=body)

    result = commitment_ops.list_blocker_clusters(since_days=45, limit=10)
    assert result["ok"] is True
    assert result["data"] == body

    path = made[0].requests[0]["path"]
    assert path.startswith("/api/v1/patterns/blocker-clusters?")
    assert "since_days=45" in path
    assert "limit=10" in path


def test_blocker_clusters_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"ok": True, "items": []})
    commitment_ops.list_blocker_clusters()
    path = made[0].requests[0]["path"]
    assert "since_days=60" in path
    assert "limit=50" in path


def test_blocker_clusters_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = commitment_ops.list_blocker_clusters()
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# list_recurring_unfinished
# ---------------------------------------------------------------------------


def test_recurring_builds_query_with_by(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    body = {"ok": True, "by": "person", "since_days": 14, "items": []}
    made = _install_fake_http(monkeypatch, body=body)

    result = commitment_ops.list_recurring_unfinished(
        by="person", since_days=14, limit=25,
    )
    assert result["ok"] is True
    path = made[0].requests[0]["path"]
    assert path.startswith("/api/v1/patterns/recurring-unfinished?")
    assert "by=person" in path
    assert "since_days=14" in path
    assert "limit=25" in path


def test_recurring_rejects_invalid_by() -> None:
    result = commitment_ops.list_recurring_unfinished(by="topic")
    assert result["ok"] is False
    assert "project" in result["error"]


def test_recurring_defaults_to_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"ok": True, "items": []})
    commitment_ops.list_recurring_unfinished()
    path = made[0].requests[0]["path"]
    assert "by=project" in path
    assert "since_days=90" in path
    assert "limit=50" in path


def test_recurring_missing_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = commitment_ops.list_recurring_unfinished()
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# Patterns dashboard renderer
# ---------------------------------------------------------------------------


def test_render_patterns_md_service_error_banner() -> None:
    body = _render_patterns_md(
        now_iso="2026-04-14T12:00:00+00:00",
        postponements=None,
        blockers=None,
        recurring_by_kind=None,
        service_error="service unreachable: connection refused",
    )
    assert "type: dashboard" in body
    assert "dashboard: patterns" in body
    assert "service unreachable" in body
    # Empty sections still render headers.
    assert "# Patterns" in body
    assert "## Postponement loops" in body
    assert "## Blocker clusters" in body
    assert "## Recurring unfinished" in body


def test_render_patterns_md_with_data() -> None:
    body = _render_patterns_md(
        now_iso="2026-04-14T12:00:00+00:00",
        postponements=[
            {
                "action_id": "a1",
                "title": "Slipping deck",
                "count": 3,
                "cumulative_days_slipped": 14,
                "last_reason": "need data",
                "last_postponed_at": "2026-04-10T10:00:00+00:00",
            }
        ],
        blockers=[
            {
                "blocker_action_id": "b1",
                "title": "Pending approval",
                "blocks_count": 2,
                "downstream_action_ids": ["d1", "d2"],
                "oldest_edge_at": "2026-03-01T09:00:00+00:00",
            }
        ],
        recurring_by_kind={
            "project": [
                {
                    "canonical_name": "Board Deck Q2",
                    "open_count": 5,
                    "median_age_days": 12,
                }
            ],
            "person": [],
            "area": [],
        },
        service_error=None,
    )
    assert "Slipping deck" in body
    assert "14" in body  # slippage
    assert "Pending approval" in body
    assert "blocks 2" in body
    assert "Board Deck Q2" in body
    assert "5 open" in body
    # Empty person/area still render fallback lines.
    assert "No recurring unfinished persons in the window." in body
    assert "No recurring unfinished areas in the window." in body


def test_render_patterns_md_empty_sections_render_placeholders() -> None:
    body = _render_patterns_md(
        now_iso="2026-04-14T12:00:00+00:00",
        postponements=[],
        blockers=[],
        recurring_by_kind={"project": [], "person": [], "area": []},
        service_error=None,
    )
    assert "No repeated postponements detected" in body
    assert "No open blockers in the window." in body


def test_render_patterns_md_deterministic_same_inputs() -> None:
    """Same inputs produce byte-identical output."""
    a = _render_patterns_md(
        now_iso="2026-04-14T12:00:00+00:00",
        postponements=[],
        blockers=[],
        recurring_by_kind={"project": [], "person": [], "area": []},
        service_error=None,
    )
    b = _render_patterns_md(
        now_iso="2026-04-14T12:00:00+00:00",
        postponements=[],
        blockers=[],
        recurring_by_kind={"project": [], "person": [], "area": []},
        service_error=None,
    )
    assert a == b


# ---------------------------------------------------------------------------
# generate_patterns_dashboard — integrates HTTP fake + atomic write
# ---------------------------------------------------------------------------


def test_generate_patterns_dashboard_writes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = tmp_path / "vault"
    (vault / "Dashboards" / "Review").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    # All three lenses return payloads.
    _install_fake_http_sequence(
        monkeypatch,
        [
            (200, {
                "ok": True, "since_days": 30,
                "items": [
                    {"action_id": "a1", "title": "A", "count": 3,
                     "cumulative_days_slipped": 5,
                     "last_reason": "waiting", "last_postponed_at":
                     "2026-04-14T10:00:00+00:00"}
                ],
            }),
            (200, {
                "ok": True, "since_days": 60,
                "items": [
                    {"blocker_action_id": "b1", "title": "B",
                     "blocks_count": 2,
                     "downstream_action_ids": ["x", "y"],
                     "oldest_edge_at": "2026-04-01T09:00:00+00:00"}
                ],
            }),
            (200, {
                "ok": True, "by": "project", "since_days": 90,
                "items": [
                    {"canonical_name": "Proj", "open_count": 4,
                     "median_age_days": 10}
                ],
            }),
            (200, {"ok": True, "by": "person", "items": []}),
            (200, {"ok": True, "by": "area", "items": []}),
        ],
    )
    result = generate_patterns_dashboard(
        vault,
        now_iso="2026-04-14T12:00:00+00:00",
    )
    assert result.path == vault / _DASHBOARD_PATTERNS_PATH
    assert result.path.is_file()
    body = result.path.read_text(encoding="utf-8")
    assert "A" in body
    assert "B" in body
    assert "Proj" in body
    assert result.written == 3  # 1 postponement + 1 blocker + 1 project bucket


def test_generate_patterns_dashboard_service_unreachable_banner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = tmp_path / "vault"
    (vault / "Dashboards" / "Review").mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)

    result = generate_patterns_dashboard(
        vault, now_iso="2026-04-14T12:00:00+00:00",
    )
    assert result.path.is_file()
    body = result.path.read_text(encoding="utf-8")
    assert "Capture service unreachable" in body
    assert result.written == 0
