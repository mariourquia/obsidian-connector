"""Tests for Task 41 bulk action wrappers, MCP, and CLI.

Covers:

- HTTP wrappers in :mod:`obsidian_connector.commitment_ops`
  (``bulk_ack_commitments``, ``bulk_done_commitments``,
  ``bulk_postpone_commitments``, ``bulk_cancel_commitments``,
  ``list_postpone_presets``) — path, body, auth, envelope error
  surfaces, preset/postponed-until exclusivity, no-empty-ids.
- MCP tool passthrough for every new tool.
- CLI subcommands (human + ``--json``) for each verb.

HTTP is mocked via the same ``_install_fake_http`` pattern used in
:mod:`tests.test_approval_ux`; no real traffic.
"""
from __future__ import annotations

import json

import pytest

from obsidian_connector import commitment_ops


# ---------------------------------------------------------------------------
# Shared HTTP fake (cloned from tests/test_approval_ux.py)
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
# bulk_ack_commitments
# ---------------------------------------------------------------------------


def test_bulk_ack_posts_body_and_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-a")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "ack", "requested": 2,
              "processed": [], "skipped": []},
    )
    r = commitment_ops.bulk_ack_commitments(
        ["act_a", "act_b"], note="reminder batch",
    )
    assert r["ok"] is True
    req = made[0].requests[0]
    assert req["method"] == "POST"
    assert req["path"] == "/api/v1/actions/bulk-ack"
    assert req["headers"].get("Authorization") == "Bearer tok-a"
    body = json.loads(req["body"].decode("utf-8"))
    assert body["action_ids"] == ["act_a", "act_b"]
    assert body["note"] == "reminder batch"


def test_bulk_ack_without_note_omits_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "ack", "requested": 1,
              "processed": [], "skipped": []},
    )
    commitment_ops.bulk_ack_commitments(["act_a"])
    body = json.loads(made[0].requests[0]["body"].decode("utf-8"))
    assert body == {"action_ids": ["act_a"]}


def test_bulk_ack_requires_nonempty_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.bulk_ack_commitments([])
    assert r["ok"] is False
    assert made == []


def test_bulk_ack_rejects_list_of_blank_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.bulk_ack_commitments(["", ""])
    assert r["ok"] is False
    assert made == []


def test_bulk_ack_surfaces_http_400_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch, status=400, body={"detail": "too many"},
    )
    r = commitment_ops.bulk_ack_commitments(["act_a"])
    assert r["ok"] is False
    assert r["status_code"] == 400


def test_bulk_ack_missing_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    r = commitment_ops.bulk_ack_commitments(["act_a"])
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# bulk_done_commitments
# ---------------------------------------------------------------------------


def test_bulk_done_hits_done_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "done", "requested": 1,
              "processed": [], "skipped": []},
    )
    commitment_ops.bulk_done_commitments(["act_a"])
    assert made[0].requests[0]["path"] == "/api/v1/actions/bulk-done"


def test_bulk_done_passes_note(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "done", "requested": 1,
              "processed": [], "skipped": []},
    )
    commitment_ops.bulk_done_commitments(["act_a"], note="closed in review")
    body = json.loads(made[0].requests[0]["body"].decode("utf-8"))
    assert body["note"] == "closed in review"


# ---------------------------------------------------------------------------
# bulk_postpone_commitments
# ---------------------------------------------------------------------------


def test_bulk_postpone_with_preset_sends_preset_in_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "postpone", "requested": 1,
              "processed": [], "skipped": [],
              "resolved_postponed_until": "2026-04-20T09:00:00+00:00"},
    )
    r = commitment_ops.bulk_postpone_commitments(
        ["act_a"], preset="next_monday_9am",
    )
    assert r["ok"] is True
    body = json.loads(made[0].requests[0]["body"].decode("utf-8"))
    assert body["action_ids"] == ["act_a"]
    assert body["preset"] == "next_monday_9am"
    assert "postponed_until" not in body


def test_bulk_postpone_with_explicit_sends_datetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "postpone", "requested": 1,
              "processed": [], "skipped": [],
              "resolved_postponed_until": "2026-05-01T12:00:00+00:00"},
    )
    commitment_ops.bulk_postpone_commitments(
        ["act_a"], postponed_until="2026-05-01T12:00:00Z",
    )
    body = json.loads(made[0].requests[0]["body"].decode("utf-8"))
    assert body["postponed_until"] == "2026-05-01T12:00:00Z"
    assert "preset" not in body


def test_bulk_postpone_rejects_both_preset_and_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.bulk_postpone_commitments(
        ["act_a"], preset="today_6pm",
        postponed_until="2026-05-01T12:00:00Z",
    )
    assert r["ok"] is False
    assert made == []  # never hit network


def test_bulk_postpone_rejects_neither_preset_nor_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.bulk_postpone_commitments(["act_a"])
    assert r["ok"] is False
    assert made == []


def test_bulk_postpone_rejects_blank_preset_and_blank_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.bulk_postpone_commitments(
        ["act_a"], preset="   ", postponed_until="  ",
    )
    assert r["ok"] is False
    assert made == []


def test_bulk_postpone_requires_nonempty_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.bulk_postpone_commitments(
        [], preset="today_6pm",
    )
    assert r["ok"] is False
    assert made == []


def test_bulk_postpone_forwards_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "postpone", "requested": 1,
              "processed": [], "skipped": [],
              "resolved_postponed_until": "2026-04-20T09:00:00+00:00"},
    )
    commitment_ops.bulk_postpone_commitments(
        ["act_a"], preset="next_monday_9am", note="waiting on vendor",
    )
    body = json.loads(made[0].requests[0]["body"].decode("utf-8"))
    assert body["note"] == "waiting on vendor"


# ---------------------------------------------------------------------------
# bulk_cancel_commitments
# ---------------------------------------------------------------------------


def test_bulk_cancel_hits_cancel_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "cancel", "requested": 1,
              "processed": [], "skipped": []},
    )
    commitment_ops.bulk_cancel_commitments(["act_a"])
    assert made[0].requests[0]["path"] == "/api/v1/actions/bulk-cancel"


def test_bulk_cancel_forwards_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "cancel", "requested": 1,
              "processed": [], "skipped": []},
    )
    commitment_ops.bulk_cancel_commitments(
        ["act_a"], reason="no longer relevant",
    )
    body = json.loads(made[0].requests[0]["body"].decode("utf-8"))
    assert body["reason"] == "no longer relevant"


def test_bulk_cancel_requires_nonempty_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.bulk_cancel_commitments([])
    assert r["ok"] is False
    assert made == []


# ---------------------------------------------------------------------------
# list_postpone_presets
# ---------------------------------------------------------------------------


def test_list_postpone_presets_hits_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(
        monkeypatch,
        body={"ok": True, "presets": [
            {"name": "today_6pm", "label": "Today 6pm",
             "description": "Today at 18:00 UTC."},
        ]},
    )
    r = commitment_ops.list_postpone_presets()
    assert r["ok"] is True
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"] == "/api/v1/actions/postpone-presets"


def test_list_postpone_presets_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    r = commitment_ops.list_postpone_presets()
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# MCP passthrough smoke
# ---------------------------------------------------------------------------


def test_mcp_bulk_ack_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "ack", "requested": 1,
              "processed": [{"action_id": "a", "status": "in_progress",
                             "ack_id": "ack_1"}],
              "skipped": []},
    )
    from obsidian_connector.mcp_server import obsidian_bulk_ack

    raw = obsidian_bulk_ack(["a"])
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_bulk_done_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "done", "requested": 1,
              "processed": [], "skipped": []},
    )
    from obsidian_connector.mcp_server import obsidian_bulk_done

    raw = obsidian_bulk_done(["a"])
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_bulk_postpone_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "postpone", "requested": 1,
              "processed": [], "skipped": [],
              "resolved_postponed_until": "2026-04-20T09:00:00+00:00"},
    )
    from obsidian_connector.mcp_server import obsidian_bulk_postpone

    raw = obsidian_bulk_postpone(["a"], preset="next_monday_9am")
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_bulk_postpone_rejects_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client-side exclusivity is enforced before the network call."""
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    from obsidian_connector.mcp_server import obsidian_bulk_postpone

    raw = obsidian_bulk_postpone(
        ["a"], preset="today_6pm",
        postponed_until="2026-04-20T09:00:00Z",
    )
    parsed = json.loads(raw)
    assert parsed.get("ok") is False
    assert made == []  # never hit network


def test_mcp_bulk_cancel_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "decision": "cancel", "requested": 1,
              "processed": [], "skipped": []},
    )
    from obsidian_connector.mcp_server import obsidian_bulk_cancel

    raw = obsidian_bulk_cancel(["a"], reason="dupe")
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_postpone_presets_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"ok": True, "presets": [
            {"name": "today_6pm", "label": "Today 6pm",
             "description": "..."},
        ]},
    )
    from obsidian_connector.mcp_server import obsidian_postpone_presets

    raw = obsidian_postpone_presets()
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


# ---------------------------------------------------------------------------
# CLI smoke (human + --json)
# ---------------------------------------------------------------------------


def test_cli_bulk_ack_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True, "decision": "ack", "requested": 2,
        "processed": [
            {"action_id": "a", "status": "in_progress", "ack_id": "ack_1"},
            {"action_id": "b", "status": "in_progress", "ack_id": "ack_2"},
        ],
        "skipped": [],
    })
    from obsidian_connector.cli import main

    rc = main(["bulk-ack", "--action-ids", "a,b"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Bulk ack" in out
    assert "ok: a" in out
    assert "ok: b" in out


def test_cli_bulk_ack_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True, "decision": "ack", "requested": 1,
        "processed": [], "skipped": [],
    })
    from obsidian_connector.cli import main

    rc = main(["bulk-ack", "--action-ids", "a", "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed.get("command") == "bulk-ack"


def test_cli_bulk_done_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True, "decision": "done", "requested": 1,
        "processed": [{"action_id": "a", "status": "done", "ack_id": "ack_1"}],
        "skipped": [],
    })
    from obsidian_connector.cli import main

    rc = main(["bulk-done", "--action-ids", "a", "--note", "cleaned up"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Bulk done" in out


def test_cli_bulk_postpone_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True, "decision": "postpone", "requested": 1,
        "processed": [{"action_id": "a", "status": "postponed",
                       "ack_id": "ack_1"}],
        "skipped": [],
        "resolved_postponed_until": "2026-04-20T09:00:00+00:00",
    })
    from obsidian_connector.cli import main

    rc = main([
        "bulk-postpone", "--action-ids", "a", "--preset", "next_monday_9am",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Bulk postpone" in out
    assert "resolved until: 2026-04-20T09:00:00+00:00" in out


def test_cli_bulk_postpone_mutual_exclusion(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    from obsidian_connector.cli import main

    main([
        "bulk-postpone", "--action-ids", "a",
        "--preset", "today_6pm",
        "--postponed-until", "2026-05-01T12:00:00Z",
    ])
    out = capsys.readouterr().out
    assert "failed" in out.lower()
    assert "exactly one" in out.lower()
    assert made == []  # never hit network


def test_cli_bulk_cancel_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True, "decision": "cancel", "requested": 1,
        "processed": [{"action_id": "a", "status": "cancelled",
                       "ack_id": "ack_1"}],
        "skipped": [],
    })
    from obsidian_connector.cli import main

    rc = main([
        "bulk-cancel", "--action-ids", "a", "--reason", "dupe of CRE-42",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Bulk cancel" in out


def test_cli_postpone_presets_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True,
        "presets": [
            {"name": "today_6pm", "label": "Today 6pm",
             "description": "Today at 18:00 UTC."},
            {"name": "tomorrow_9am", "label": "Tomorrow 9am",
             "description": "Tomorrow at 09:00 UTC."},
        ],
    })
    from obsidian_connector.cli import main

    rc = main(["postpone-presets"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Postpone presets (2)" in out
    assert "today_6pm" in out
    assert "tomorrow_9am" in out


def test_cli_postpone_presets_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"ok": True, "presets": []})
    from obsidian_connector.cli import main

    rc = main(["postpone-presets", "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed.get("command") == "postpone-presets"


def test_cli_bulk_cancel_reports_skips_on_wrong_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={
        "ok": True, "decision": "cancel", "requested": 2,
        "processed": [{"action_id": "a", "status": "cancelled",
                       "ack_id": "ack_1"}],
        "skipped": [{"action_id": "b", "reason": "wrong_status",
                     "detail": "status is 'done', expected non-terminal"}],
    })
    from obsidian_connector.cli import main

    rc = main(["bulk-cancel", "--action-ids", "a,b"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "skip: b" in out
    assert "wrong_status" in out


def test_cli_bulk_ack_http_400_surfaces_as_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch, status=400,
        body={"detail": "too many action_ids in request"},
    )
    from obsidian_connector.cli import main

    main(["bulk-ack", "--action-ids", "a"])
    out = capsys.readouterr().out
    assert "failed" in out.lower()
    assert "HTTP 400" in out
