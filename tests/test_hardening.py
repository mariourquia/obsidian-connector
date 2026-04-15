"""Task 35 connector hardening tests.

Covers:

- `SERVICE_REQUEST_TIMEOUT_SECONDS` env knob (default, override, bad
  value fallback).
- `commitment_notes`, `entity_notes`, `commitment_dashboards` only
  write through ``atomic_write`` (AST audit).
- End-to-end: each module's public writer entry point is exercised so
  a future drift to a raw ``Path.write_text`` cannot slip through.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CONNECTOR = REPO_ROOT / "obsidian_connector"


# ---------------------------------------------------------------------------
# Timeout helper (SERVICE_REQUEST_TIMEOUT_SECONDS)
# ---------------------------------------------------------------------------


def test_service_timeout_defaults_to_10_seconds(monkeypatch):
    monkeypatch.delenv("SERVICE_REQUEST_TIMEOUT_SECONDS", raising=False)
    from obsidian_connector.commitment_ops import _service_timeout

    assert _service_timeout() == 10.0


def test_service_timeout_honors_env_override(monkeypatch):
    monkeypatch.setenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "25")
    from obsidian_connector.commitment_ops import _service_timeout

    assert _service_timeout() == 25.0


def test_service_timeout_falls_back_on_bad_value(monkeypatch):
    """Non-numeric env values must not disable the ceiling."""
    monkeypatch.setenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "not-a-number")
    from obsidian_connector.commitment_ops import _service_timeout

    assert _service_timeout() == 10.0


def test_service_timeout_ignores_zero_or_negative(monkeypatch):
    monkeypatch.setenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "0")
    from obsidian_connector.commitment_ops import _service_timeout

    assert _service_timeout() == 10.0

    monkeypatch.setenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "-4")
    assert _service_timeout() == 10.0


def test_service_get_json_uses_env_timeout_when_none_passed(monkeypatch):
    """Patch HTTPConnection to capture the timeout used by the client."""
    captured: dict[str, object] = {}

    class _FakeResp:
        status = 200

        def read(self):
            return b"{}"

    class _FakeConn:
        def __init__(self, host, timeout=None, **kw):
            captured["timeout"] = timeout
            captured["host"] = host

        def request(self, *a, **kw):  # noqa: ARG002
            pass

        def getresponse(self):
            return _FakeResp()

        def close(self):
            pass

    monkeypatch.setenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "17")
    monkeypatch.setenv("OBSIDIAN_CAPTURE_SERVICE_URL", "http://svc.example")
    monkeypatch.delenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN", raising=False)

    import http.client as http_client

    monkeypatch.setattr(http_client, "HTTPConnection", _FakeConn)

    from obsidian_connector import commitment_ops

    result = commitment_ops._service_get_json("/health")
    assert result["ok"] is True
    assert captured["timeout"] == 17.0


# ---------------------------------------------------------------------------
# Atomic-write audit
# ---------------------------------------------------------------------------


_AUDITED_MODULES = (
    "commitment_notes.py",
    "entity_notes.py",
    "commitment_dashboards.py",
)


@pytest.mark.parametrize("fname", _AUDITED_MODULES)
def test_audited_modules_have_no_raw_write_text_calls(fname: str) -> None:
    """No ``.write_text(...)`` calls should live in these modules.

    Every write must route through ``atomic_write`` (imported from
    ``write_manager``). This test parses each file's AST and scans
    every ``Call`` node's function name; a direct ``write_text`` call
    on any receiver fails the audit.
    """
    source = (CONNECTOR / fname).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        attr: str | None = None
        if isinstance(func, ast.Attribute):
            attr = func.attr
        elif isinstance(func, ast.Name):
            attr = func.id
        if attr in {"write_text", "write_bytes"}:
            offenders.append(f"line {node.lineno}: {attr}")
    assert not offenders, (
        f"{fname} contains raw write calls outside atomic_write: {offenders}"
    )


@pytest.mark.parametrize("fname", _AUDITED_MODULES)
def test_audited_modules_import_atomic_write(fname: str) -> None:
    """Each audited module imports atomic_write from write_manager."""
    source = (CONNECTOR / fname).read_text(encoding="utf-8")
    assert "from obsidian_connector.write_manager import atomic_write" in source


# ---------------------------------------------------------------------------
# Runtime smoke: each writer uses atomic_write via mock
# ---------------------------------------------------------------------------


def test_commitment_note_writer_delegates_to_atomic_write(monkeypatch, tmp_path):
    """``write_commitment_note`` must route through ``atomic_write``.

    Stubs the write_manager export so a regression that switches to a
    plain ``Path.write_text`` would immediately break the assertion.
    """
    calls: list[tuple[str, str]] = []

    def _fake_atomic(path, content, *, vault_root=None, **kw):  # noqa: ARG001
        calls.append((str(path), content[:20]))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")

    from obsidian_connector import commitment_notes

    monkeypatch.setattr(commitment_notes, "atomic_write", _fake_atomic)

    vault = tmp_path / "vault"
    vault.mkdir()
    from obsidian_connector.commitment_notes import ActionInput, write_commitment_note

    action = ActionInput(
        action_id="act_test_01",
        capture_id="cap_test_01",
        title="test commitment",
        created_at="2026-04-14T00:00:00+00:00",
        status="open",
        priority="normal",
    )
    write_commitment_note(vault, action)
    assert calls, "write_commitment_note should call atomic_write"


def test_entity_note_writer_delegates_to_atomic_write(monkeypatch, tmp_path):
    calls: list[tuple[str, str]] = []

    def _fake_atomic(path, content, *, vault_root=None, **kw):  # noqa: ARG001
        calls.append((str(path), content[:20]))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")

    from obsidian_connector import entity_notes

    monkeypatch.setattr(entity_notes, "atomic_write", _fake_atomic)

    vault = tmp_path / "vault"
    vault.mkdir()
    from obsidian_connector.entity_notes import EntityInput, write_entity_note

    entity = EntityInput(
        entity_id="ent_01",
        kind="project",
        canonical_name="Demo",
        slug="demo",
    )
    write_entity_note(vault, entity)
    assert calls, "write_entity_note should call atomic_write"
