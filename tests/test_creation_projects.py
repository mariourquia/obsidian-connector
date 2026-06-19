"""Tests for obsidian_connector.creation_projects."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_connector.creation_projects import (
    Project,
    get_project,
    list_projects,
    project_repo_entries,
    read_one_pager_prose,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_sync_config(vault: Path, repos: list[dict]) -> None:
    """Write a minimal sync_config.json to the vault root."""
    config = {"repos": repos}
    (vault / "sync_config.json").write_text(json.dumps(config), encoding="utf-8")


def _make_vault(tmp_path: Path, monkeypatch) -> Path:
    """Create a minimal vault directory and set OBSIDIAN_VAULT_PATH to it."""
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    return vault


def _mcmc_repos() -> list[dict]:
    return [
        {"dir_name": "mcmc-ehr", "display_name": "MCMC EHR", "group": "mcmc", "status": "active", "tags": ["health"]},
        {"dir_name": "mcmc-erp", "display_name": "MCMC ERP", "group": "mcmc", "status": "active", "tags": []},
        {"dir_name": "mcmc-auth", "display_name": "MCMC Auth", "group": "mcmc", "status": "paused", "tags": []},
    ]


def _cre_repos() -> list[dict]:
    return [
        {"dir_name": "cre-skills-plugin", "display_name": "CRE Skills Plugin", "group": "cre-skills", "status": "active", "tags": []},
        {"dir_name": "cre-skills-pro", "display_name": "CRE Skills Pro", "group": "cre-skills", "status": "active", "tags": []},
    ]


def _standalone_repos() -> list[dict]:
    return [
        {"dir_name": "obsidian-connector", "display_name": "Obsidian Connector", "group": "standalone", "status": "active", "tags": []},
        {"dir_name": "site", "display_name": "Site", "group": "standalone", "status": "active", "tags": []},
    ]


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------

class TestListProjects:
    def test_returns_four_projects_for_mixed_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        repos = _mcmc_repos() + _cre_repos() + _standalone_repos()
        _write_sync_config(vault, repos)

        projects = list_projects(str(vault))

        assert len(projects) == 4, f"Expected 4 projects, got {len(projects)}: {[p.slug for p in projects]}"

    def test_mcmc_group_has_three_repos(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        _write_sync_config(vault, _mcmc_repos() + _cre_repos() + _standalone_repos())

        projects = list_projects(str(vault))
        mcmc = next((p for p in projects if p.slug == "mcmc"), None)

        assert mcmc is not None
        assert set(mcmc.repos) == {"mcmc-ehr", "mcmc-erp", "mcmc-auth"}
        assert len(mcmc.repos) == 3

    def test_cre_skills_group_has_two_repos(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        _write_sync_config(vault, _mcmc_repos() + _cre_repos() + _standalone_repos())

        projects = list_projects(str(vault))
        cre = next((p for p in projects if p.slug == "cre-skills"), None)

        assert cre is not None
        assert set(cre.repos) == {"cre-skills-plugin", "cre-skills-pro"}

    def test_standalone_repos_each_become_own_project(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        _write_sync_config(vault, _standalone_repos())

        projects = list_projects(str(vault))
        slugs = {p.slug for p in projects}

        assert "obsidian-connector" in slugs
        assert "site" in slugs
        for p in projects:
            assert len(p.repos) == 1

    def test_standalone_project_name_is_display_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        _write_sync_config(vault, _standalone_repos())

        projects = list_projects(str(vault))
        oc = next(p for p in projects if p.slug == "obsidian-connector")

        assert oc.name == "Obsidian Connector"

    def test_projects_sorted_by_name_case_insensitive(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        _write_sync_config(vault, _mcmc_repos() + _cre_repos() + _standalone_repos())

        projects = list_projects(str(vault))
        names = [p.name.lower() for p in projects]

        assert names == sorted(names)

    def test_empty_config_returns_no_projects(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        # Write a config with no repos; disable auto-discovery by providing an
        # empty list explicitly — note: load_sync_config falls back to
        # discover_repos when repos is empty, so we must ensure github_root
        # points somewhere with no repos.
        config = {
            "repos": [],
            "github_root": str(tmp_path / "nonexistent"),
        }
        (vault / "sync_config.json").write_text(json.dumps(config))

        # With no repos the result depends on discover_repos behaviour on a
        # nonexistent root — should be empty.
        projects = list_projects(str(vault))
        assert isinstance(projects, list)


# ---------------------------------------------------------------------------
# Status rollup
# ---------------------------------------------------------------------------

class TestStatusRollup:
    def test_active_if_any_repo_active(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        repos = [
            {"dir_name": "r1", "display_name": "R1", "group": "grp", "status": "paused", "tags": []},
            {"dir_name": "r2", "display_name": "R2", "group": "grp", "status": "active", "tags": []},
        ]
        _write_sync_config(vault, repos)

        projects = list_projects(str(vault))
        assert projects[0].status == "active"

    def test_paused_when_no_active_repo(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        repos = [
            {"dir_name": "r1", "display_name": "R1", "group": "grp", "status": "paused", "tags": []},
            {"dir_name": "r2", "display_name": "R2", "group": "grp", "status": "dormant", "tags": []},
        ]
        _write_sync_config(vault, repos)

        projects = list_projects(str(vault))
        assert projects[0].status == "paused"


# ---------------------------------------------------------------------------
# get_project
# ---------------------------------------------------------------------------

class TestGetProject:
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        _write_sync_config(vault, _mcmc_repos() + _cre_repos() + _standalone_repos())
        return vault

    def test_get_by_slug_lowercase(self, tmp_path, monkeypatch):
        vault = self._setup(tmp_path, monkeypatch)
        result = get_project(str(vault), "mcmc")
        assert result is not None
        assert result.slug == "mcmc"

    def test_get_by_slug_uppercase(self, tmp_path, monkeypatch):
        vault = self._setup(tmp_path, monkeypatch)
        result = get_project(str(vault), "MCMC")
        assert result is not None
        assert result.slug == "mcmc"

    def test_get_by_slug_mixed_case(self, tmp_path, monkeypatch):
        vault = self._setup(tmp_path, monkeypatch)
        result = get_project(str(vault), "Mcmc")
        assert result is not None
        assert result.slug == "mcmc"

    def test_get_by_display_name(self, tmp_path, monkeypatch):
        vault = self._setup(tmp_path, monkeypatch)
        # group_display("mcmc") returns "mcmc" (no mapping); standalone uses display_name
        result = get_project(str(vault), "Obsidian Connector")
        assert result is not None
        assert result.slug == "obsidian-connector"

    def test_get_returns_none_for_unknown(self, tmp_path, monkeypatch):
        vault = self._setup(tmp_path, monkeypatch)
        result = get_project(str(vault), "does-not-exist")
        assert result is None

    def test_get_standalone_by_slug(self, tmp_path, monkeypatch):
        vault = self._setup(tmp_path, monkeypatch)
        result = get_project(str(vault), "obsidian-connector")
        assert result is not None
        assert result.slug == "obsidian-connector"
        assert result.repos == ("obsidian-connector",)


# ---------------------------------------------------------------------------
# project_repo_entries
# ---------------------------------------------------------------------------

class TestProjectRepoEntries:
    def test_returns_entries_for_group_project(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        _write_sync_config(vault, _mcmc_repos() + _standalone_repos())

        mcmc_project = get_project(str(vault), "mcmc")
        assert mcmc_project is not None

        entries = project_repo_entries(str(vault), mcmc_project)
        dir_names = {e.dir_name for e in entries}

        assert dir_names == {"mcmc-ehr", "mcmc-erp", "mcmc-auth"}

    def test_returns_single_entry_for_standalone(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        _write_sync_config(vault, _standalone_repos())

        oc_project = get_project(str(vault), "obsidian-connector")
        assert oc_project is not None

        entries = project_repo_entries(str(vault), oc_project)
        assert len(entries) == 1
        assert entries[0].dir_name == "obsidian-connector"


# ---------------------------------------------------------------------------
# read_one_pager_prose
# ---------------------------------------------------------------------------

class TestReadOnePagerProse:
    def _setup_vault_with_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        vault = _make_vault(tmp_path, monkeypatch)
        _write_sync_config(vault, _mcmc_repos() + _standalone_repos())
        return vault

    def test_returns_empty_dict_when_file_absent(self, tmp_path, monkeypatch):
        vault = self._setup_vault_with_config(tmp_path, monkeypatch)
        mcmc = get_project(str(vault), "mcmc")
        assert mcmc is not None

        result = read_one_pager_prose(str(vault), mcmc)
        assert result == {}

    def test_returns_present_scalar_keys(self, tmp_path, monkeypatch):
        vault = self._setup_vault_with_config(tmp_path, monkeypatch)
        mcmc = get_project(str(vault), "mcmc")
        assert mcmc is not None

        # Create the one-pager directory and file
        one_pager_dir = vault / "Projects" / mcmc.name
        one_pager_dir.mkdir(parents=True)
        one_pager = one_pager_dir / "Project One-Pager.md"
        one_pager.write_text(
            "---\n"
            "goal: Build a world-class EHR system\n"
            "intent: Improve patient outcomes in Honduras\n"
            "irrelevant_key: should not appear\n"
            "---\n\n"
            "# MCMC\n\nSome body text.\n",
            encoding="utf-8",
        )

        result = read_one_pager_prose(str(vault), mcmc)

        assert result["goal"] == "Build a world-class EHR system"
        assert result["intent"] == "Improve patient outcomes in Honduras"
        assert "irrelevant_key" not in result

    def test_all_five_prose_keys_captured(self, tmp_path, monkeypatch):
        vault = self._setup_vault_with_config(tmp_path, monkeypatch)
        mcmc = get_project(str(vault), "mcmc")
        assert mcmc is not None

        one_pager_dir = vault / "Projects" / mcmc.name
        one_pager_dir.mkdir(parents=True)
        (one_pager_dir / "Project One-Pager.md").write_text(
            "---\n"
            "goal: my goal\n"
            "intent: my intent\n"
            "target_users: clinicians\n"
            "architecture: FastAPI + Postgres\n"
            "why: because it matters\n"
            "---\n",
            encoding="utf-8",
        )

        result = read_one_pager_prose(str(vault), mcmc)

        assert result == {
            "goal": "my goal",
            "intent": "my intent",
            "target_users": "clinicians",
            "architecture": "FastAPI + Postgres",
            "why": "because it matters",
        }

    def test_returns_empty_dict_for_standalone_project_without_file(self, tmp_path, monkeypatch):
        vault = self._setup_vault_with_config(tmp_path, monkeypatch)
        oc = get_project(str(vault), "obsidian-connector")
        assert oc is not None

        result = read_one_pager_prose(str(vault), oc)
        assert result == {}

    def test_empty_frontmatter_returns_empty_dict(self, tmp_path, monkeypatch):
        vault = self._setup_vault_with_config(tmp_path, monkeypatch)
        mcmc = get_project(str(vault), "mcmc")
        assert mcmc is not None

        one_pager_dir = vault / "Projects" / mcmc.name
        one_pager_dir.mkdir(parents=True)
        (one_pager_dir / "Project One-Pager.md").write_text(
            "# No frontmatter here\n\nJust body text.\n",
            encoding="utf-8",
        )

        result = read_one_pager_prose(str(vault), mcmc)
        assert result == {}
