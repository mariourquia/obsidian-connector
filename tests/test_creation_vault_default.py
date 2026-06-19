"""`obsx creation` defaults to the creation vault.

Creation commands operate on the Creation Vault, not the user's primary
"Obsidian Vault". Without an explicit ``--vault``, they must resolve to the
vault named ``creation`` (overridable by ``--vault`` and the standard
``OBSIDIAN_VAULT_PATH`` escape hatch).
"""

from __future__ import annotations

import pytest

from obsidian_connector import cli
from obsidian_connector import creation_projects


@pytest.fixture
def _captured_vault(monkeypatch):
    captured = {}

    def _fake_list_projects(vault=None):
        captured["vault"] = vault
        return []

    monkeypatch.setattr(creation_projects, "list_projects", _fake_list_projects)
    return captured


def test_creation_projects_defaults_to_creation_vault(_captured_vault, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    cli.main(["creation", "projects", "--json"])

    assert _captured_vault["vault"] == "creation"


def test_explicit_vault_flag_overrides_default(_captured_vault, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    other = tmp_path / "other-vault"
    (other / ".obsidian").mkdir(parents=True)

    cli.main(["--vault", str(other), "creation", "projects", "--json"])

    assert _captured_vault["vault"] == str(other)


def test_creation_vault_name_constant_exists():
    assert cli.CREATION_VAULT_NAME == "creation"


def test_mcp_creation_projects_defaults_to_creation_vault(monkeypatch, tmp_path):
    """MCP parity: the creation tools default to the creation vault too."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)

    captured = {}
    import obsidian_connector.config as _config

    def _fake_resolve(vault=None):
        captured["vault"] = vault
        return tmp_path

    monkeypatch.setattr(_config, "resolve_vault_path", _fake_resolve)
    monkeypatch.setattr(creation_projects, "list_projects", lambda v=None: [])

    from obsidian_connector.mcp_server import obsidian_creation_projects

    obsidian_creation_projects()

    assert captured["vault"] == "creation"
