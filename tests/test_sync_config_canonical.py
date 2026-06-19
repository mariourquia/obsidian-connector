"""Tests for the canonical sync_config resolution + group display map.

Covers the Creation registry canonicalization:
- a top-level ``groups`` map in sync_config.json drives display names
- resolution order: OBSIDIAN_SYNC_CONFIG env > vault-root > XDG canonical
- group display names flow through to Project names
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector.creation_projects import get_project, list_projects
from obsidian_connector.project_sync import load_sync_config


def _make_vault(tmp_path: Path, monkeypatch) -> Path:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    return vault


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# groups map -> group_display_names
# ---------------------------------------------------------------------------

class TestGroupsMap:
    def test_groups_map_parsed_into_group_display_names(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        _write(
            vault / "sync_config.json",
            {
                "groups": {"wine": "Wine", "signalforge": "SignalForge"},
                "repos": [
                    {"dir_name": "wine-cellar-app", "group": "wine"},
                ],
            },
        )

        config = load_sync_config(str(vault))

        assert config.group_display_names == {"wine": "Wine", "signalforge": "SignalForge"}

    def test_missing_groups_map_yields_empty_dict(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        _write(vault / "sync_config.json", {"repos": [{"dir_name": "r1", "group": "x"}]})

        config = load_sync_config(str(vault))

        assert config.group_display_names == {}


# ---------------------------------------------------------------------------
# group display names flow into Project.name
# ---------------------------------------------------------------------------

class TestGroupDisplayNamesInProjects:
    def test_config_group_name_used_for_project(self, tmp_path, monkeypatch):
        # "wine" is NOT in the built-in GROUP_DISPLAY map; the config must drive it.
        vault = _make_vault(tmp_path, monkeypatch)
        _write(
            vault / "sync_config.json",
            {
                "groups": {"wine": "Wine"},
                "repos": [
                    {"dir_name": "wine-cellar-app", "group": "wine"},
                    {"dir_name": "wine-api", "group": "wine"},
                ],
            },
        )

        wine = get_project(str(vault), "wine")

        assert wine is not None
        assert wine.name == "Wine"
        assert set(wine.repos) == {"wine-cellar-app", "wine-api"}

    def test_config_overrides_builtin_group_display(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        _write(
            vault / "sync_config.json",
            {
                "groups": {"mcmc": "MCMC Health System"},
                "repos": [{"dir_name": "mcmc-ehr", "group": "mcmc"}],
            },
        )

        projects = list_projects(str(vault))
        mcmc = next(p for p in projects if p.slug == "mcmc")

        assert mcmc.name == "MCMC Health System"

    def test_builtin_used_when_config_silent(self, tmp_path, monkeypatch):
        # No groups map -> built-in GROUP_DISPLAY still applies for known slugs.
        vault = _make_vault(tmp_path, monkeypatch)
        _write(vault / "sync_config.json", {"repos": [{"dir_name": "amos-api", "group": "amos"}]})

        projects = list_projects(str(vault))
        amos = next(p for p in projects if p.slug == "amos")

        assert amos.name == "AMOS"


# ---------------------------------------------------------------------------
# Resolution order: OBSIDIAN_SYNC_CONFIG env > vault-root > XDG canonical
# ---------------------------------------------------------------------------

def _xdg_config(xdg_home: Path) -> Path:
    return xdg_home / "obsidian-connector" / "sync_config.json"


class TestResolution:
    def test_xdg_canonical_used_when_no_vault_config(self, tmp_path, monkeypatch, xdg_config_home):
        vault = _make_vault(tmp_path, monkeypatch)  # resolvable, but no vault-root config
        _write(
            _xdg_config(xdg_config_home),
            {
                "github_root": "/opt/dev",
                "groups": {"mcmc": "MCMC"},
                "repos": [{"dir_name": "mcmc-ehr", "group": "mcmc"}],
            },
        )

        config = load_sync_config(str(vault))

        assert str(config.github_root) == "/opt/dev"
        assert [r.dir_name for r in config.repos] == ["mcmc-ehr"]
        assert config.group_display_names == {"mcmc": "MCMC"}

    def test_vault_root_overrides_xdg(self, tmp_path, monkeypatch, xdg_config_home):
        vault = _make_vault(tmp_path, monkeypatch)
        _write(_xdg_config(xdg_config_home), {"repos": [{"dir_name": "from-xdg", "group": "g"}]})
        _write(vault / "sync_config.json", {"repos": [{"dir_name": "from-vault", "group": "g"}]})

        config = load_sync_config(str(vault))

        assert [r.dir_name for r in config.repos] == ["from-vault"]

    def test_env_override_wins(self, tmp_path, monkeypatch, xdg_config_home):
        vault = _make_vault(tmp_path, monkeypatch)
        _write(vault / "sync_config.json", {"repos": [{"dir_name": "from-vault", "group": "g"}]})
        explicit = tmp_path / "explicit.json"
        _write(explicit, {"repos": [{"dir_name": "from-env", "group": "g"}]})
        monkeypatch.setenv("OBSIDIAN_SYNC_CONFIG", str(explicit))

        config = load_sync_config(str(vault))

        assert [r.dir_name for r in config.repos] == ["from-env"]

    def test_env_override_missing_file_is_ignored(self, tmp_path, monkeypatch, xdg_config_home):
        vault = _make_vault(tmp_path, monkeypatch)
        _write(vault / "sync_config.json", {"repos": [{"dir_name": "from-vault", "group": "g"}]})
        monkeypatch.setenv("OBSIDIAN_SYNC_CONFIG", str(tmp_path / "does-not-exist.json"))

        config = load_sync_config(str(vault))

        assert [r.dir_name for r in config.repos] == ["from-vault"]

    def test_xdg_used_even_when_vault_unresolvable(self, tmp_path, monkeypatch, xdg_config_home):
        # No OBSIDIAN_VAULT_PATH and an unresolvable vault name: XDG must still load.
        monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
        _write(
            _xdg_config(xdg_config_home),
            {"repos": [{"dir_name": "xdg-repo", "group": "g"}]},
        )

        config = load_sync_config("no-such-vault-name")

        assert [r.dir_name for r in config.repos] == ["xdg-repo"]
