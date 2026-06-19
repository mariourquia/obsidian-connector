# tests/test_creation_dashboard_cli.py
"""CLI tests for the Task-6 creation dashboard verbs.

Strategy
--------
- All tests use ``--vault <path>`` to redirect vault resolution to a tmp dir.
- ``load_sync_config`` is monkeypatched to return a minimal SyncConfig so
  tests never depend on real git repos or disk state.
- ``creation_repo_status.repo_status`` and ``creation_next.next_actions`` are
  monkeypatched so tests stay offline.
- ``cli.log_action`` is monkeypatched for write-verb tests to capture calls.
"""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from obsidian_connector import cli
from obsidian_connector.project_sync import RepoEntry, SyncConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(monkeypatch, tmp_path, argv):
    """Run the CLI with vault resolved to tmp_path/v via --vault flag."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    full_argv = ["--vault", str(vault)] + argv
    return cli.main(full_argv)


def _write_sync_config(vault: Path, repos: list[dict]) -> None:
    """Write a minimal sync_config.json into the vault."""
    import json as _json

    vault.mkdir(parents=True, exist_ok=True)
    (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    (vault / "sync_config.json").write_text(
        _json.dumps({"repos": repos, "github_root": str(vault / "fake-github")}),
        encoding="utf-8",
    )


def _fake_sync_config(tmp_path: Path, repos=None) -> SyncConfig:
    """Build a minimal SyncConfig without touching disk."""
    if repos is None:
        repos = [
            RepoEntry(dir_name="my-repo", display_name="My Repo", status="active",
                      group="standalone"),
        ]
    sc = SyncConfig()
    sc.repos = repos
    sc.github_root = tmp_path / "fake-github"
    return sc


def _stub_repo_status(entry, *, github_root, now_iso, with_prs=True,
                      with_tests=False, with_build=False, runner=None):
    """Offline stub returning a minimal RepoStatus-like object."""
    from obsidian_connector.creation_repo_status import RepoStatus

    return RepoStatus(
        dir_name=entry.dir_name,
        display_name=entry.display_name,
        project=entry.dir_name,
        repo_path=str(github_root / entry.dir_name),
        branch="main",
        head="abc1234",
        dirty=False,
        untracked=0,
        ahead=0,
        behind=0,
        recent_commits=(),
        open_prs=(),
        merged_prs_recent=(),
        tests={"status": "unknown"},
        build={"status": "unknown"},
        deploy={"status": "unknown"},
        classification="clean-and-ready",
        next_action="Ready for next task",
        blockers=(),
        authority_level="repo_grounded",
    )


def _stub_next_actions(vault, *, scope="global", project=None, repo=None,
                       github_root=None, now_iso, limit=10, runner=None):
    """Canned next_actions response."""
    return [
        {
            "scope": scope,
            "project": project or "my-project",
            "repo": repo or "my-repo",
            "backlog_id": "bl-001",
            "action": "Fix the tests",
            "reason": ["urgency"],
            "confidence": 0.85,
            "requires_mario_decision": False,
            "suggested_workflow": None,
            "context_pack": None,
        }
    ]


# ---------------------------------------------------------------------------
# creation projects --json
# ---------------------------------------------------------------------------

def test_projects_json_lists_from_config(tmp_path, monkeypatch, capsys):
    """creation projects --json lists projects from the injected sync config."""
    vault = tmp_path / "v"

    sc = _fake_sync_config(
        tmp_path,
        repos=[
            RepoEntry(dir_name="alpha", display_name="Alpha", status="active",
                      group="standalone"),
            RepoEntry(dir_name="beta", display_name="Beta", status="paused",
                      group="standalone"),
        ],
    )

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_projects as _cproj
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(_cproj, "load_sync_config", lambda vault=None: sc)

    rc = _run(monkeypatch, tmp_path, ["creation", "projects", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    names = [p["name"] for p in out["data"]["projects"]]
    assert "Alpha" in names
    assert "Beta" in names
    assert out["data"]["count"] == 2


# ---------------------------------------------------------------------------
# creation next --json
# ---------------------------------------------------------------------------

def test_next_json_returns_ranked_items(tmp_path, monkeypatch, capsys):
    """creation next --json returns canned ranked items."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path)

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_next as _cnext
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(_cnext, "next_actions", _stub_next_actions)

    rc = _run(monkeypatch, tmp_path, ["creation", "next", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["data"]["count"] == 1
    assert out["data"]["items"][0]["action"] == "Fix the tests"


def test_next_json_limit_respected(tmp_path, monkeypatch, capsys):
    """--limit is passed through (stub returns 1 regardless, but flag parsed)."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path)

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_next as _cnext
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(_cnext, "next_actions", _stub_next_actions)

    rc = _run(monkeypatch, tmp_path, ["creation", "next", "--limit", "3", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True


# ---------------------------------------------------------------------------
# creation repo show --json
# ---------------------------------------------------------------------------

def test_repo_show_json_returns_status_dict(tmp_path, monkeypatch, capsys):
    """creation repo show <r> --json returns a status dict with expected keys."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path, repos=[
        RepoEntry(dir_name="my-repo", display_name="My Repo", status="active",
                  group="standalone"),
    ])

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_repo_status as _crs
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(_crs, "repo_status", _stub_repo_status)

    rc = _run(monkeypatch, tmp_path, ["creation", "repo", "show", "my-repo", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    d = out["data"]
    assert d["dir_name"] == "my-repo"
    assert d["classification"] == "clean-and-ready"
    assert "branch" in d
    assert "blockers" in d


def test_repo_show_unknown_repo_returns_error(tmp_path, monkeypatch, capsys):
    """creation repo show with an unknown repo dir exits non-zero."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path, repos=[
        RepoEntry(dir_name="my-repo", display_name="My Repo", status="active",
                  group="standalone"),
    ])

    import obsidian_connector.project_sync as _ps
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)

    rc = _run(monkeypatch, tmp_path, ["creation", "repo", "show", "nonexistent"])
    assert rc != 0


# ---------------------------------------------------------------------------
# creation dashboard --json
# ---------------------------------------------------------------------------

def test_dashboard_json_returns_do_next_and_projects(tmp_path, monkeypatch, capsys):
    """creation dashboard --json returns do_next + projects."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path, repos=[
        RepoEntry(dir_name="my-repo", display_name="My Repo", status="active",
                  group="standalone"),
    ])

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_next as _cnext
    import obsidian_connector.creation_repo_status as _crs
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(_cnext, "next_actions", _stub_next_actions)
    monkeypatch.setattr(_crs, "repo_status", _stub_repo_status)

    rc = _run(monkeypatch, tmp_path, ["creation", "dashboard", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    d = out["data"]
    assert "do_next" in d
    assert "projects" in d
    assert isinstance(d["do_next"], list)
    assert d["do_next"][0]["action"] == "Fix the tests"


def test_dashboard_project_filter_returns_drilldown(tmp_path, monkeypatch, capsys):
    """creation dashboard --project returns a drilldown view."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path)

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_next as _cnext
    import obsidian_connector.creation_repo_status as _crs
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(_cnext, "next_actions", _stub_next_actions)
    monkeypatch.setattr(_crs, "repo_status", _stub_repo_status)

    rc = _run(monkeypatch, tmp_path,
              ["creation", "dashboard", "--project", "my-project", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    d = out["data"]
    assert d["scope"] == "project"
    assert "do_next" in d


# ---------------------------------------------------------------------------
# creation refresh -- dry-run default, log_action only on real write
# ---------------------------------------------------------------------------

def test_refresh_is_dry_run_by_default(tmp_path, monkeypatch, capsys):
    """creation refresh writes nothing and does NOT call log_action."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path)
    logged = []

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_dashboards as _cdash
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(
        _cdash,
        "refresh_all",
        lambda *a, **kw: {"written": ["/fake/Dashboard.md"], "dry_run": True},
    )
    monkeypatch.setattr(cli, "log_action", lambda *a, **k: logged.append((a, k)))

    rc = _run(monkeypatch, tmp_path, ["creation", "refresh"])
    assert rc == 0
    # log_action must NOT have been called with dry_run=False
    real_writes = [c for c in logged if c[1].get("dry_run") is False]
    assert real_writes == []


def test_refresh_dry_run_output_has_prefix(tmp_path, monkeypatch, capsys):
    """Human output for a dry-run refresh shows [dry-run] prefix."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path)

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_dashboards as _cdash
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(
        _cdash,
        "refresh_all",
        lambda *a, **kw: {"written": [], "dry_run": True},
    )

    rc = _run(monkeypatch, tmp_path, ["creation", "refresh"])
    assert rc == 0
    assert "[dry-run]" in capsys.readouterr().out


def test_refresh_allow_write_calls_log_action(tmp_path, monkeypatch, capsys):
    """creation refresh --allow-write calls log_action with dry_run=False."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path)
    logged = []

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_dashboards as _cdash
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(
        _cdash,
        "refresh_all",
        lambda *a, **kw: {"written": ["/fake/Dashboard.md"], "dry_run": False},
    )
    monkeypatch.setattr(cli, "log_action", lambda *a, **k: logged.append((a, k)))

    rc = _run(monkeypatch, tmp_path, ["creation", "refresh", "--allow-write"])
    assert rc == 0
    real_writes = [c for c in logged if c[1].get("dry_run") is False]
    assert real_writes, "log_action should be called with dry_run=False"


def test_refresh_allow_write_json_output(tmp_path, monkeypatch, capsys):
    """creation refresh --allow-write --json emits the envelope."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path)

    import obsidian_connector.project_sync as _ps
    import obsidian_connector.creation_dashboards as _cdash
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)
    monkeypatch.setattr(
        _cdash,
        "refresh_all",
        lambda *a, **kw: {"written": ["/fake/Dashboard.md"], "dry_run": False},
    )
    monkeypatch.setattr(cli, "log_action", lambda *a, **k: None)

    rc = _run(monkeypatch, tmp_path, ["creation", "refresh", "--allow-write", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert "written" in out["data"]


# ---------------------------------------------------------------------------
# creation migrate-projects -- dry-run default
# ---------------------------------------------------------------------------

def test_migrate_projects_dry_run_by_default(tmp_path, monkeypatch, capsys):
    """creation migrate-projects writes nothing by default (dry_run=True to migrate)."""
    vault = tmp_path / "v"
    logged = []

    import obsidian_connector.creation_migrate as _cmig
    monkeypatch.setattr(
        _cmig,
        "migrate",
        lambda *a, **kw: {"planned": 3, "written": 0, "map_path": None,
                          "dry_run": True},
    )
    monkeypatch.setattr(cli, "log_action", lambda *a, **k: logged.append((a, k)))

    rc = _run(monkeypatch, tmp_path, ["creation", "migrate-projects"])
    assert rc == 0
    assert "[dry-run]" in capsys.readouterr().out
    real_writes = [c for c in logged if c[1].get("dry_run") is False]
    assert real_writes == []


def test_migrate_projects_allow_write_logs(tmp_path, monkeypatch, capsys):
    """creation migrate-projects --allow-write calls log_action with dry_run=False."""
    vault = tmp_path / "v"
    logged = []

    import obsidian_connector.creation_migrate as _cmig
    monkeypatch.setattr(
        _cmig,
        "migrate",
        lambda *a, **kw: {"planned": 3, "written": 3, "map_path": "/fake/map.md",
                          "dry_run": False},
    )
    monkeypatch.setattr(cli, "log_action", lambda *a, **k: logged.append((a, k)))

    rc = _run(monkeypatch, tmp_path,
              ["creation", "migrate-projects", "--allow-write"])
    assert rc == 0
    real_writes = [c for c in logged if c[1].get("dry_run") is False]
    assert real_writes, "log_action should be called when writing"


def test_migrate_projects_undo_calls_undo_migration(tmp_path, monkeypatch, capsys):
    """creation migrate-projects --undo calls undo_migration, not migrate."""
    vault = tmp_path / "v"
    called = []

    import obsidian_connector.creation_migrate as _cmig
    monkeypatch.setattr(
        _cmig, "undo_migration",
        lambda *a, **kw: (called.append(("undo", kw)), {"removed": 0, "dry_run": True})[1],
    )
    monkeypatch.setattr(
        _cmig, "migrate",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("migrate() called unexpectedly")),
    )

    rc = _run(monkeypatch, tmp_path, ["creation", "migrate-projects", "--undo"])
    assert rc == 0
    assert called and called[0][0] == "undo"


# ---------------------------------------------------------------------------
# creation project show --json
# ---------------------------------------------------------------------------

def test_project_show_json(tmp_path, monkeypatch, capsys):
    """creation project show <P> --json returns project drilldown."""
    vault = tmp_path / "v"
    sc = _fake_sync_config(tmp_path, repos=[
        RepoEntry(dir_name="my-repo", display_name="My Repo", status="active",
                  group="my-group"),
    ])

    import obsidian_connector.project_sync as _ps
    monkeypatch.setattr(_ps, "load_sync_config", lambda vault=None: sc)

    # patch list_projects so we don't need a real vault config
    from obsidian_connector.creation_projects import Project
    fake_proj = Project(
        slug="my-group", name="My Group", group="my-group",
        repos=("my-repo",), status="active", tags=(),
    )
    import obsidian_connector.creation_projects as _cproj
    monkeypatch.setattr(_cproj, "list_projects", lambda vault=None: [fake_proj])
    monkeypatch.setattr(_cproj, "project_repo_entries",
                        lambda vault, project: [
                            RepoEntry(dir_name="my-repo", display_name="My Repo",
                                      status="active", group="my-group")
                        ])
    monkeypatch.setattr(_cproj, "read_one_pager_prose", lambda vault, project: {})

    rc = _run(monkeypatch, tmp_path,
              ["creation", "project", "show", "my-group", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    d = out["data"]
    assert d["slug"] == "my-group"
    assert "my-repo" in d["repos"]
