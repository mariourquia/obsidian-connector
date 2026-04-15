"""Tests for Task 38 delegation wrappers, MCP passthrough, CLI, and dashboard.

Covers:

- ``ActionInput`` accepts the three delegation kwargs and frontmatter
  renders the new slot in stable order; body row only emits when
  ``delegated_to`` is set.
- HTTP wrappers in :mod:`obsidian_connector.commitment_ops`
  (``delegate_commitment``, ``reclaim_commitment``,
  ``list_delegated_to``, ``list_stale_delegations``).
- MCP tool passthrough to the wrappers.
- CLI subcommands human + JSON output.
- Delegation dashboard rendering (pure) + the real
  ``generate_delegation_dashboard`` path against a sequence of mocked
  HTTP responses.
- ``update_all_review_dashboards(include_delegations=...)`` opt-out.

HTTP is mocked; no real traffic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector import commitment_ops
from obsidian_connector.commitment_dashboards import (
    _DASHBOARD_DELEGATIONS_PATH,
    _render_delegations_md,
    generate_delegation_dashboard,
    update_all_review_dashboards,
)
from obsidian_connector.commitment_notes import (
    ActionInput,
    render_commitment_note,
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
# ActionInput + commitment-note rendering
# ---------------------------------------------------------------------------


def _base_action(**overrides: object) -> ActionInput:
    kwargs: dict[str, object] = {
        "action_id": "act_01TESTACT0000000001",
        "capture_id": "cap_01TESTCAP0000000001",
        "title": "Follow up with Alice",
        "created_at": "2026-04-14T10:00:00+00:00",
    }
    kwargs.update(overrides)
    return ActionInput(**kwargs)  # type: ignore[arg-type]


def test_action_input_accepts_delegation_kwargs() -> None:
    action = _base_action(
        delegated_to="Alice Smith",
        delegated_at="2026-04-14T11:30:00+00:00",
        delegation_note="Alice will chase the lender on this.",
    )
    assert action.delegated_to == "Alice Smith"
    assert action.delegated_at == "2026-04-14T11:30:00+00:00"
    assert action.delegation_note == "Alice will chase the lender on this."


def test_action_input_defaults_delegation_to_none() -> None:
    action = _base_action()
    assert action.delegated_to is None
    assert action.delegated_at is None
    assert action.delegation_note is None


def test_frontmatter_renders_delegation_slot_in_stable_order() -> None:
    action = _base_action(
        delegated_to="Alice Smith",
        delegated_at="2026-04-14T11:30:00+00:00",
        delegation_note="Will re-check Monday.",
    )
    rendered = render_commitment_note(
        action, now_iso="2026-04-14T12:00:00+00:00",
    )
    # All three delegation keys must appear, in order, between
    # postponed_until and requires_ack.
    idx_postponed = rendered.index("postponed_until:")
    idx_dto = rendered.index("delegated_to:")
    idx_dat = rendered.index("delegated_at:")
    idx_note = rendered.index("delegation_note:")
    idx_ack = rendered.index("requires_ack:")
    assert idx_postponed < idx_dto < idx_dat < idx_note < idx_ack
    assert "delegated_to: Alice Smith" in rendered
    # delegated_at contains a colon so it's quoted by the serializer.
    assert 'delegated_at: "2026-04-14T11:30:00+00:00"' in rendered
    # delegation_note contains a period and is quoted.
    assert 'delegation_note: "Will re-check Monday."' in rendered


def test_frontmatter_renders_null_delegation_when_absent() -> None:
    action = _base_action()
    rendered = render_commitment_note(
        action, now_iso="2026-04-14T12:00:00+00:00",
    )
    assert "delegated_to: null" in rendered
    assert "delegated_at: null" in rendered
    assert "delegation_note: null" in rendered


def test_body_row_renders_only_when_delegated() -> None:
    delegated = render_commitment_note(
        _base_action(
            delegated_to="Alice Smith",
            delegated_at="2026-04-14T11:30:00+00:00",
            delegation_note="Short note.",
        ),
        now_iso="2026-04-14T12:00:00+00:00",
    )
    assert "- Delegated to: Alice Smith (2026-04-14)" in delegated
    assert "- Delegation note: Short note." in delegated

    plain = render_commitment_note(
        _base_action(), now_iso="2026-04-14T12:00:00+00:00",
    )
    assert "Delegated to" not in plain
    assert "Delegation note" not in plain


def test_body_row_falls_back_to_raw_timestamp_when_unparseable() -> None:
    rendered = render_commitment_note(
        _base_action(
            delegated_to="Alice Smith",
            delegated_at="not-an-iso-date",
        ),
        now_iso="2026-04-14T12:00:00+00:00",
    )
    # Should still render the row, but with the raw value instead of
    # a date-only form.
    assert "Delegated to: Alice Smith" in rendered
    assert "not-an-iso-date" in rendered


# ---------------------------------------------------------------------------
# delegate_commitment
# ---------------------------------------------------------------------------


def test_delegate_posts_body_and_quotes_action_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", "tok-d")
    made = _install_fake_http(
        monkeypatch,
        body={
            "action_id": "act_01", "status": "open",
            "lifecycle_stage": "waiting",
            "delegated_to": "Alice",
            "delegated_at": "2026-04-14T12:00:00+00:00",
            "delegation_note": "Will follow up.",
        },
    )
    r = commitment_ops.delegate_commitment(
        "act_01",
        to_person="Alice",
        note="Will follow up.",
    )
    assert r["ok"] is True
    req = made[0].requests[0]
    assert req["method"] == "POST"
    assert req["path"] == "/api/v1/actions/act_01/delegate"
    assert req["headers"].get("Authorization") == "Bearer tok-d"
    body = json.loads(req["body"].decode("utf-8"))
    assert body["to_person"] == "Alice"
    assert body["note"] == "Will follow up."


def test_delegate_strips_to_person_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"delegated_to": "Alice"})
    commitment_ops.delegate_commitment(
        "act_01", to_person="  Alice  ",
    )
    body = json.loads(made[0].requests[0]["body"].decode("utf-8"))
    assert body["to_person"] == "Alice"


def test_delegate_empty_action_id_does_not_hit_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.delegate_commitment("", to_person="Alice")
    assert r["ok"] is False
    assert made == []


def test_delegate_empty_person_does_not_hit_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.delegate_commitment("act_01", to_person="  ")
    assert r["ok"] is False
    assert made == []


def test_delegate_surfaces_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=409, body={"detail": "terminal"})
    r = commitment_ops.delegate_commitment("act_x", to_person="Alice")
    assert r["ok"] is False
    assert r["status_code"] == 409


# ---------------------------------------------------------------------------
# reclaim_commitment
# ---------------------------------------------------------------------------


def test_reclaim_posts_empty_body_when_no_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"delegated_to": None})
    r = commitment_ops.reclaim_commitment("act_01")
    assert r["ok"] is True
    req = made[0].requests[0]
    assert req["method"] == "POST"
    assert req["path"] == "/api/v1/actions/act_01/reclaim"
    body = json.loads(req["body"].decode("utf-8"))
    assert body == {}


def test_reclaim_includes_note_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"delegated_to": None})
    commitment_ops.reclaim_commitment("act_01", note="Taking this back.")
    body = json.loads(made[0].requests[0]["body"].decode("utf-8"))
    assert body == {"note": "Taking this back."}


def test_reclaim_empty_action_id_does_not_hit_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.reclaim_commitment("")
    assert r["ok"] is False
    assert made == []


# ---------------------------------------------------------------------------
# list_delegated_to
# ---------------------------------------------------------------------------


def test_delegated_to_builds_query_and_quotes_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"items": []})
    commitment_ops.list_delegated_to(
        "Alice Smith", limit=25, cursor="abc==", include_terminal=True,
    )
    req = made[0].requests[0]
    assert req["method"] == "GET"
    # Space URL-encodes to %20 (alias-safe).
    assert req["path"].startswith(
        "/api/v1/actions/delegated-to/Alice%20Smith?"
    )
    assert "limit=25" in req["path"]
    assert "cursor=abc%3D%3D" in req["path"]
    assert "include_terminal=true" in req["path"]


def test_delegated_to_default_does_not_emit_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"items": []})
    commitment_ops.list_delegated_to("Alice")
    req = made[0].requests[0]
    assert "cursor=" not in req["path"]
    # include_terminal is False by default and must not surface.
    assert "include_terminal=" not in req["path"]
    assert "limit=50" in req["path"]


def test_delegated_to_empty_person_does_not_hit_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={})
    r = commitment_ops.list_delegated_to("")
    assert r["ok"] is False
    assert made == []


# ---------------------------------------------------------------------------
# list_stale_delegations
# ---------------------------------------------------------------------------


def test_stale_delegations_builds_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"items": []})
    commitment_ops.list_stale_delegations(threshold_days=30, limit=10)
    req = made[0].requests[0]
    assert req["method"] == "GET"
    assert req["path"].startswith("/api/v1/patterns/stale-delegations?")
    assert "threshold_days=30" in req["path"]
    assert "limit=10" in req["path"]


def test_stale_delegations_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    made = _install_fake_http(monkeypatch, body={"items": []})
    commitment_ops.list_stale_delegations()
    req = made[0].requests[0]
    assert "threshold_days=14" in req["path"]
    assert "limit=50" in req["path"]


def test_stale_delegations_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    r = commitment_ops.list_stale_delegations()
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# MCP tool passthrough
# ---------------------------------------------------------------------------


def test_mcp_delegate_commitment_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"action_id": "act_1", "delegated_to": "Alice"},
    )
    from obsidian_connector.mcp_server import obsidian_delegate_commitment

    raw = obsidian_delegate_commitment("act_1", "Alice")
    parsed = json.loads(raw)
    assert parsed.get("ok") is True
    assert parsed.get("data", {}).get("delegated_to") == "Alice"


def test_mcp_reclaim_commitment_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"action_id": "act_1", "delegated_to": None},
    )
    from obsidian_connector.mcp_server import obsidian_reclaim_commitment

    raw = obsidian_reclaim_commitment("act_1")
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_delegated_to_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"items": []})
    from obsidian_connector.mcp_server import obsidian_delegated_to

    raw = obsidian_delegated_to("Alice")
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


def test_mcp_stale_delegations_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"items": []})
    from obsidian_connector.mcp_server import obsidian_stale_delegations

    raw = obsidian_stale_delegations(threshold_days=7, limit=20)
    parsed = json.loads(raw)
    assert parsed.get("ok") is True


# ---------------------------------------------------------------------------
# CLI human + JSON output
# ---------------------------------------------------------------------------


def test_cli_delegate_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={
            "action_id": "act_1", "status": "open",
            "lifecycle_stage": "waiting",
            "delegated_to": "Alice",
            "delegated_at": "2026-04-14T12:00:00+00:00",
            "delegation_note": None,
        },
    )
    from obsidian_connector.cli import main

    rc = main([
        "delegate-commitment",
        "--action-id", "act_1",
        "--to-person", "Alice",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Delegate ok" in out
    assert "Alice" in out


def test_cli_delegate_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={"action_id": "act_1", "delegated_to": "Alice"},
    )
    from obsidian_connector.cli import main

    rc = main([
        "delegate-commitment",
        "--action-id", "act_1",
        "--to-person", "Alice",
        "--json",
    ])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed.get("ok") is True
    assert parsed.get("command") == "delegate-commitment"


def test_cli_reclaim_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={
            "action_id": "act_1", "status": "open",
            "lifecycle_stage": "active",
            "delegated_to": None,
        },
    )
    from obsidian_connector.cli import main

    rc = main(["reclaim-commitment", "--action-id", "act_1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Reclaim ok" in out
    assert "(cleared)" in out


def test_cli_delegated_to_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={
            "items": [
                {
                    "action_id": "act_1",
                    "title": "Follow up with the lender",
                    "lifecycle_stage": "waiting",
                    "delegated_at": "2026-04-10T12:00:00+00:00",
                    "delegation_note": "Chase weekly.",
                }
            ],
            "next_cursor": None,
        },
    )
    from obsidian_connector.cli import main

    rc = main(["delegated-to", "--person", "Alice"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Actions delegated to person" in out
    assert "Follow up with the lender" in out
    assert "Chase weekly." in out


def test_cli_stale_delegations_human(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(
        monkeypatch,
        body={
            "threshold_days": 14,
            "items": [
                {
                    "entity_id": "ent_alice",
                    "canonical_name": "Alice Smith",
                    "count": 3,
                    "oldest_delegated_at": "2026-03-01T12:00:00+00:00",
                    "newest_delegated_at": "2026-04-01T12:00:00+00:00",
                    "items": [
                        {
                            "action_id": "act_1",
                            "title": "Confirm loan doc",
                            "delegated_at": "2026-03-01T12:00:00+00:00",
                            "delegation_note": None,
                        }
                    ],
                }
            ],
        },
    )
    from obsidian_connector.cli import main

    rc = main(["stale-delegations", "--threshold-days", "14"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Stale delegations" in out
    assert "Alice Smith" in out
    assert "3 stale" in out
    assert "Confirm loan doc" in out


def test_cli_stale_delegations_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, body={"items": []})
    from obsidian_connector.cli import main

    rc = main(["stale-delegations", "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed.get("command") == "stale-delegations"


# ---------------------------------------------------------------------------
# Delegation dashboard renderer (pure)
# ---------------------------------------------------------------------------


def test_render_delegations_md_not_configured() -> None:
    out = _render_delegations_md(
        now_iso="2026-04-14T00:00:00+00:00",
        threshold_days=14,
        stale_items=None,
        open_counts=None,
        service_configured=False,
        service_error=None,
    )
    assert "Capture service not configured" in out
    assert "# Delegations" in out
    assert "## Stale delegations" in out
    assert "## Open delegations" in out


def test_render_delegations_md_service_error_banner() -> None:
    out = _render_delegations_md(
        now_iso="2026-04-14T00:00:00+00:00",
        threshold_days=14,
        stale_items=None,
        open_counts=None,
        service_configured=True,
        service_error="connection refused",
    )
    assert "Capture service unreachable" in out
    assert "connection refused" in out


def test_render_delegations_md_renders_stale_rows() -> None:
    out = _render_delegations_md(
        now_iso="2026-04-14T00:00:00+00:00",
        threshold_days=14,
        stale_items=[
            {
                "entity_id": "ent_alice",
                "canonical_name": "Alice Smith",
                "count": 3,
                "oldest_delegated_at": "2026-03-01T12:00:00+00:00",
                "items": [
                    {"title": "Confirm docs",
                     "delegated_at": "2026-03-01T12:00:00+00:00"},
                    {"title": "Ping lender",
                     "delegated_at": "2026-03-02T12:00:00+00:00"},
                ],
            }
        ],
        open_counts=[("Alice Smith", 4), ("Bob Jones", 1)],
        service_configured=True,
        service_error=None,
    )
    # Stale rows
    assert "Alice Smith" in out
    assert "Confirm docs" in out
    assert "Ping lender" in out
    assert "2026-03-01" in out
    # Open-counts table
    assert "| Alice Smith | 4 |" in out
    assert "| Bob Jones | 1 |" in out


def test_render_delegations_md_empty_sections() -> None:
    out = _render_delegations_md(
        now_iso="2026-04-14T00:00:00+00:00",
        threshold_days=14,
        stale_items=[],
        open_counts=[],
        service_configured=True,
        service_error=None,
    )
    assert "No stale delegations in the window." in out
    assert "No open delegations." in out


# ---------------------------------------------------------------------------
# generate_delegation_dashboard (integration)
# ---------------------------------------------------------------------------


def test_generate_delegation_dashboard_without_service_url(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no service URL is configured, still write the dashboard."""
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    res = generate_delegation_dashboard(
        tmp_vault, now_iso="2026-04-14T00:00:00+00:00",
    )
    path = tmp_vault / _DASHBOARD_DELEGATIONS_PATH
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Capture service not configured" in text
    assert res.written == 0


def test_generate_delegation_dashboard_happy_path(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service returns two responses: one for stale bucket, one for all-open."""
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    responses = [
        (200, {
            "threshold_days": 14,
            "items": [
                {
                    "entity_id": "ent_alice",
                    "canonical_name": "Alice Smith",
                    "count": 2,
                    "oldest_delegated_at": "2026-03-01T12:00:00+00:00",
                    "newest_delegated_at": "2026-03-15T12:00:00+00:00",
                    "items": [
                        {"title": "Confirm loan doc",
                         "delegated_at": "2026-03-01T12:00:00+00:00"}
                    ],
                }
            ],
        }),
        (200, {
            "threshold_days": 1,
            "items": [
                {
                    "canonical_name": "Alice Smith",
                    "count": 3,
                },
                {
                    "canonical_name": "Bob Jones",
                    "count": 1,
                },
            ],
        }),
    ]
    _install_fake_http_sequence(monkeypatch, responses)

    res = generate_delegation_dashboard(
        tmp_vault, now_iso="2026-04-14T00:00:00+00:00",
    )
    path = tmp_vault / _DASHBOARD_DELEGATIONS_PATH
    text = path.read_text(encoding="utf-8")
    assert "Alice Smith" in text
    assert "Bob Jones" in text
    assert "Confirm loan doc" in text
    # One stale bucket rendered.
    assert res.written == 1


def test_generate_delegation_dashboard_service_error(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://host:8787")
    _install_fake_http(monkeypatch, status=500, body={"error": "boom"})
    res = generate_delegation_dashboard(
        tmp_vault, now_iso="2026-04-14T00:00:00+00:00",
    )
    path = tmp_vault / _DASHBOARD_DELEGATIONS_PATH
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "# Delegations" in text
    # When the service fails the banner surfaces and both sections
    # render "no data" notes.
    assert (
        "Capture service unreachable" in text
        or "No stale delegations" in text
    )
    assert res.written == 0


# ---------------------------------------------------------------------------
# update_all_review_dashboards(include_delegations=...)
# ---------------------------------------------------------------------------


def test_update_all_review_includes_delegations_by_default(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    results = update_all_review_dashboards(
        tmp_vault, now_iso="2026-04-14T00:00:00+00:00",
    )
    paths = [str(r.path) for r in results]
    assert any(p.endswith("Delegations.md") for p in paths)


def test_update_all_review_skips_delegations_when_opted_out(
    tmp_vault: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_URL", raising=False)
    results = update_all_review_dashboards(
        tmp_vault,
        now_iso="2026-04-14T00:00:00+00:00",
        include_delegations=False,
    )
    paths = [str(r.path) for r in results]
    assert not any(p.endswith("Delegations.md") for p in paths)
