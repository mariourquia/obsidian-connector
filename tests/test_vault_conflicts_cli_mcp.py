"""CLI + MCP wiring tests for vault_conflicts (Task 37 phase 2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "Note.md").write_text("x", encoding="utf-8")
    (tmp_path / "Note (Mario's iPhone).md").write_text("x", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------


def test_mcp_tool_returns_json_envelope(vault: Path):
    from obsidian_connector.mcp_server import obsidian_vault_conflicts

    raw = obsidian_vault_conflicts(str(vault))
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["vault_root"] == str(vault.resolve())
    assert len(payload["items"]) == 1
    assert payload["items"][0]["provider"] == "iCloud Drive"


def test_mcp_tool_falls_back_to_env(vault: Path, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_ROOT", str(vault))
    from obsidian_connector.mcp_server import obsidian_vault_conflicts

    raw = obsidian_vault_conflicts(None)
    payload = json.loads(raw)
    assert payload["ok"] is True


def test_mcp_tool_errors_cleanly_when_no_vault(monkeypatch):
    monkeypatch.delenv("OBSIDIAN_VAULT_ROOT", raising=False)
    from obsidian_connector.mcp_server import obsidian_vault_conflicts

    raw = obsidian_vault_conflicts(None)
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert "OBSIDIAN_VAULT_ROOT" in payload["error"] or "vault_root" in payload["error"]


def test_mcp_tool_never_raises_on_internal_error(monkeypatch):
    """Even if the scanner blows up, the tool returns an envelope."""
    import obsidian_connector.mcp_server as mcp_mod

    def boom(*a, **kw):
        raise RuntimeError("scanner crashed")

    # Patch at import location inside the function (re-imported each call).
    monkeypatch.setattr(
        "obsidian_connector.vault_conflicts.detect_vault_conflicts",
        boom,
    )
    raw = mcp_mod.obsidian_vault_conflicts("/tmp")
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# CLI subcommand
# ---------------------------------------------------------------------------


def test_cli_parser_registers_subcommand():
    from obsidian_connector.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["vault-conflicts", "--vault-root", "/tmp"])
    assert args.command == "vault-conflicts"
    assert args.vault_root == "/tmp"


def test_cli_prints_json_when_flag_set(vault: Path, capsys):
    from obsidian_connector.cli import main

    rc = main(["--json", "vault-conflicts", "--vault-root", str(vault)])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    # The detect_vault_conflicts envelope is nested under `data` by the CLI framework.
    assert payload["data"]["ok"] is True
    assert len(payload["data"]["items"]) == 1


def test_cli_prints_human_when_flag_unset(vault: Path, capsys):
    from obsidian_connector.cli import main

    rc = main(["vault-conflicts", "--vault-root", str(vault)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "iCloud Drive" in captured.out
    assert "Note (Mario's iPhone).md" in captured.out


def test_cli_errors_on_missing_vault_root(monkeypatch, capsys):
    from obsidian_connector.cli import main

    monkeypatch.delenv("OBSIDIAN_VAULT_ROOT", raising=False)
    rc = main(["--json", "vault-conflicts"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    # Top-level envelope is ok; the detect_vault_conflicts payload carries the failure.
    assert payload["data"]["ok"] is False
    assert rc == 0


def test_cli_reads_env_when_flag_absent(vault: Path, capsys, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_ROOT", str(vault))
    from obsidian_connector.cli import main

    rc = main(["--json", "vault-conflicts"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["data"]["ok"] is True
    assert len(payload["data"]["items"]) == 1


def test_cli_human_formatter_handles_no_conflicts(tmp_path: Path, capsys):
    """Clean vault prints a one-line "no conflicts" summary."""
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "OnlyNote.md").write_text("ok", encoding="utf-8")
    from obsidian_connector.cli import main

    rc = main(["vault-conflicts", "--vault-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No conflict files detected" in out
