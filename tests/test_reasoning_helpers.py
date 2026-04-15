"""Tests for Task 32 why-still-open helpers + commitment-note projection.

Covers:

- ``explain_commitment`` HTTP wrapper (auth, errors, 404, 409, path shape)
- ``_fmt_explain_commitment`` CLI formatter
- Commitment-note rendering of ``why_open_summary`` (fence markers,
  bounded size, idempotency, preservation across re-syncs when not
  supplied)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector import commitment_ops
from obsidian_connector.cli import _fmt_explain_commitment
from obsidian_connector.commitment_notes import (
    ActionInput,
    USER_NOTES_BEGIN,
    USER_NOTES_END,
    WHY_OPEN_BEGIN,
    WHY_OPEN_END,
    render_commitment_note,
)


# ---------------------------------------------------------------------------
# HTTP fake
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
# explain_commitment — Python helper
# ---------------------------------------------------------------------------


def test_explain_commitment_builds_path_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-why")
    body = {
        "ok": True,
        "action_id": "act_abc",
        "status": "open",
        "lifecycle_stage": "inbox",
        "urgency": "normal",
        "reasons": [
            {"code": "NO_OWNER_OR_PROJECT", "label": "No linked owner", "data": {}},
        ],
        "inputs": {"priority": "normal"},
    }
    made = _install_fake_http(monkeypatch, body=body)

    result = commitment_ops.explain_commitment("act_abc")
    assert result["ok"] is True
    assert result["data"] == body
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"] == "/api/v1/actions/act_abc/why-still-open"
    assert req["headers"].get("Authorization") == "Bearer tok-why"


def test_explain_commitment_handles_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=404, body={"detail": "nope"})
    result = commitment_ops.explain_commitment("act_missing")
    assert result["ok"] is False
    assert result["status_code"] == 404


def test_explain_commitment_handles_409_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=409, body={"detail": "terminal"})
    result = commitment_ops.explain_commitment("act_done")
    assert result["ok"] is False
    assert result["status_code"] == 409


def test_explain_commitment_rejects_empty_action_id() -> None:
    assert commitment_ops.explain_commitment("")["ok"] is False
    assert commitment_ops.explain_commitment(None)["ok"] is False  # type: ignore[arg-type]


def test_explain_commitment_missing_service_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    result = commitment_ops.explain_commitment("act_x")
    assert result["ok"] is False
    assert "service not configured" in result["error"]


def test_explain_commitment_service_url_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://env-host:8787")
    made = _install_fake_http(monkeypatch, body={"ok": True})
    commitment_ops.explain_commitment(
        "act_x", service_url="http://override:9999",
    )
    assert made[0].netloc == "override:9999"


# ---------------------------------------------------------------------------
# CLI formatter
# ---------------------------------------------------------------------------


def test_fmt_explain_commitment_success() -> None:
    out = _fmt_explain_commitment({
        "ok": True,
        "data": {
            "action_id": "act_1",
            "status": "open",
            "lifecycle_stage": "inbox",
            "urgency": "normal",
            "reasons": [
                {"code": "OVERDUE_NO_MOVEMENT", "label": "Overdue by 5d"},
                {"code": "HAS_DUPLICATES", "label": "Linked to 1"},
            ],
        },
    })
    assert "act_1" in out
    assert "OVERDUE_NO_MOVEMENT" in out
    assert "HAS_DUPLICATES" in out


def test_fmt_explain_commitment_failure() -> None:
    out = _fmt_explain_commitment({
        "ok": False, "status_code": 404, "error": "not found",
    })
    assert "HTTP 404" in out


def test_fmt_explain_commitment_no_reasons() -> None:
    out = _fmt_explain_commitment({
        "ok": True,
        "data": {
            "action_id": "act_1",
            "status": "open",
            "lifecycle_stage": "inbox",
            "urgency": "normal",
            "reasons": [],
        },
    })
    assert "no reasons returned" in out.lower()


# ---------------------------------------------------------------------------
# Commitment-note projection of why_open_summary
# ---------------------------------------------------------------------------


def _base_input(**overrides) -> ActionInput:
    fields: dict = {
        "action_id": "act_1",
        "capture_id": "cap_1",
        "title": "Thing to do",
        "created_at": "2026-04-14T10:00:00+00:00",
    }
    fields.update(overrides)
    return ActionInput(**fields)


def test_why_open_summary_renders_fence_when_supplied() -> None:
    action = _base_input(why_open_summary="- OVERDUE_NO_MOVEMENT: 5d")
    body = render_commitment_note(action)
    assert WHY_OPEN_BEGIN in body
    assert WHY_OPEN_END in body
    assert "## Why still open" in body
    assert "- OVERDUE_NO_MOVEMENT: 5d" in body


def test_why_open_summary_absent_renders_no_section() -> None:
    action = _base_input(why_open_summary=None)
    body = render_commitment_note(action)
    assert WHY_OPEN_BEGIN not in body
    assert "## Why still open" not in body


def test_why_open_summary_preserved_across_resync_when_none() -> None:
    first = _base_input(
        why_open_summary="- STALE_INBOX: 6d in inbox (> 3d)",
    )
    body_one = render_commitment_note(first)

    # Re-sync without the summary -> the fence block is preserved.
    second = _base_input(why_open_summary=None)
    body_two = render_commitment_note(second, existing_content=body_one)
    assert WHY_OPEN_BEGIN in body_two
    assert "STALE_INBOX" in body_two


def test_why_open_summary_overwrites_existing_when_supplied() -> None:
    first = _base_input(why_open_summary="- OLD")
    body_one = render_commitment_note(first)
    assert "OLD" in body_one

    second = _base_input(why_open_summary="- NEW")
    body_two = render_commitment_note(second, existing_content=body_one)
    assert "NEW" in body_two
    assert "OLD" not in body_two


def test_why_open_summary_truncated_if_too_long() -> None:
    huge = "x" * 5000
    action = _base_input(why_open_summary=huge)
    body = render_commitment_note(action)
    # Content is truncated to 1500 chars + "…" ellipsis.
    assert "x" * 1500 in body
    assert "x" * 2000 not in body


def test_why_open_summary_empty_string_renders_placeholder() -> None:
    action = _base_input(why_open_summary="   ")
    body = render_commitment_note(action)
    assert "_No reasons returned._" in body


def test_why_open_summary_idempotent_rendering() -> None:
    action = _base_input(why_open_summary="- REASON")
    first = render_commitment_note(
        action, now_iso="2026-04-14T12:00:00+00:00",
    )
    second = render_commitment_note(
        action, now_iso="2026-04-14T12:00:00+00:00",
    )
    assert first == second


def test_why_open_summary_does_not_clobber_user_notes() -> None:
    """User-editable section between USER_NOTES_BEGIN/END is preserved."""
    action = _base_input(why_open_summary="- REASON")
    body_one = render_commitment_note(action)
    # Manually inject user-editable content into the preserved fence.
    body_with_user_edits = body_one.replace(
        "_User-editable area below. Content here is preserved across syncs._",
        "my custom notes\nwith multiple lines",
    )
    action2 = _base_input(why_open_summary="- REASON")
    body_two = render_commitment_note(
        action2, existing_content=body_with_user_edits,
    )
    assert "my custom notes" in body_two
    assert "with multiple lines" in body_two
