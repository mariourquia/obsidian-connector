#!/usr/bin/env python3
"""Tests for project_sync and vault_init modules."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_PASS = 0
_FAIL = 0


def _check(label: str, ok: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        msg = f"  FAIL  {label}"
        if detail:
            msg += f" -- {detail}"
        print(msg)


def assert_eq(label: str, got, expected) -> None:
    _check(label, got == expected, f"got {got!r}, expected {expected!r}")


def assert_in(label: str, needle, haystack) -> None:
    _check(label, needle in haystack, f"{needle!r} not in output")


def assert_type(label: str, obj, expected_type) -> None:
    _check(label, isinstance(obj, expected_type), f"got {type(obj).__name__}, expected {expected_type.__name__}")


# ---------------------------------------------------------------------------
# Test imports
# ---------------------------------------------------------------------------

print("\n=== Import tests ===")

try:
    from obsidian_connector.project_sync import (
        RepoEntry,
        RepoState,
        SessionEntry,
        SyncConfig,
        TodoItem,
        _extract_repo_state,
        _render_project_file,
        _render_dashboard,
        _render_active_threads,
        _render_running_todo,
        render_session_entry,
        get_project_status,
        get_active_threads,
        get_running_todo,
        load_sync_config,
    )
    _check("import project_sync", True)
except ImportError as e:
    _check("import project_sync", False, str(e))

try:
    from obsidian_connector.vault_init import (
        discover_repos,
        init_vault,
        _render_group_file,
        _render_initial_dashboard,
        _render_initial_todo,
    )
    _check("import vault_init", True)
except ImportError as e:
    _check("import vault_init", False, str(e))

try:
    from obsidian_connector import (
        SessionEntry as SE,
        SyncConfig as SC,
        sync_projects,
        get_active_threads as gat,
        get_project_status as gps,
        get_running_todo as grt,
        log_session,
        init_vault as iv,
        discover_repos as dr,
    )
    _check("import from __init__", True)
except ImportError as e:
    _check("import from __init__", False, str(e))

# ---------------------------------------------------------------------------
# Test data classes
# ---------------------------------------------------------------------------

print("\n=== Data class tests ===")

entry = RepoEntry("test-repo", "Test Repo", "CLAUDE.md", "active", "standalone", ["python"])
assert_eq("RepoEntry.dir_name", entry.dir_name, "test-repo")
assert_eq("RepoEntry.tags", entry.tags, ["python"])

state = RepoState(
    dir_name="test-repo",
    display_name="Test Repo",
    group="standalone",
    status="active",
    branch="feature/test",
    uncommitted_count=3,
)
assert_eq("RepoState.branch", state.branch, "feature/test")
assert_eq("RepoState.uncommitted_count", state.uncommitted_count, 3)
assert_eq("RepoState.is_git default", state.is_git, True)

session = SessionEntry(
    project="test-repo",
    work_types=["feature-dev", "docs"],
    completed=["Built the thing"],
    next_steps=["Write tests"],
    files_changed=5,
)
assert_eq("SessionEntry.project", session.project, "test-repo")
assert_eq("SessionEntry.work_types", session.work_types, ["feature-dev", "docs"])

todo = TodoItem(text="Fix the bug", source="daily/2026-03-23.md")
assert_eq("TodoItem.text", todo.text, "Fix the bug")
assert_eq("TodoItem.completed default", todo.completed, False)

config = SyncConfig()
assert_type("SyncConfig.github_root", config.github_root, Path)
assert_type("SyncConfig.repos", config.repos, list)

# ---------------------------------------------------------------------------
# Test rendering
# ---------------------------------------------------------------------------

print("\n=== Rendering tests ===")

# Project file for missing dir
missing_state = RepoState(
    dir_name="gone", display_name="Gone", group="standalone", status="active",
    exists=False, is_git=False, activity_label="missing",
    tags=["project", "standalone"],
)
md = _render_project_file(missing_state)
assert_in("missing project has warning", "warning", md)
assert_in("missing project has title", "Gone", md)

# Project file for valid repo
valid_state = RepoState(
    dir_name="valid", display_name="Valid Repo", group="amos", status="active",
    branch="feature/test", last_commit_msg="Add tests", uncommitted_count=2,
    recent_commits=["abc123 Add tests", "def456 Fix bug"],
    modified_files=["src/main.py"],
    tags=["project", "amos", "python"],
)
md = _render_project_file(valid_state)
assert_in("valid project has branch", "feature/test", md)
assert_in("valid project has commit", "Add tests", md)
assert_in("valid project has group link", "[[AMOS]]", md)

# Dashboard
states = [valid_state, missing_state]
dash = _render_dashboard(states)
assert_in("dashboard has title", "Creation Dashboard", dash)
assert_in("dashboard has project table", "valid", dash)
assert_in("dashboard has Running TODO link", "Running TODO", dash)

# Active threads
threads = _render_active_threads([valid_state, missing_state])
assert_in("threads has active project", "Valid Repo", threads)

# Running TODO (empty vault)
with tempfile.TemporaryDirectory() as tmpdir:
    tmp_path = Path(tmpdir)
    todo_md = _render_running_todo(tmp_path)
    assert_in("empty todo has header", "Running TODO", todo_md)
    assert_in("empty todo has no items msg", "No open TODO items", todo_md)

    # Running TODO with items
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    (daily_dir / "2026-03-23.md").write_text(
        "# Today\n\n- [ ] Fix the bug\n- [ ] Write docs\n- [x] Deploy v1\n"
    )
    todo_md = _render_running_todo(tmp_path)
    assert_in("todo has open items", "Fix the bug", todo_md)
    assert_in("todo has open count", "total_open: 2", todo_md)

# Session entry
entry_list = [
    SessionEntry(
        project="obsidian-connector",
        work_types=["feature-dev"],
        completed=["Built sync module"],
        next_steps=["Write tests"],
        decisions=["Used Python over bash"],
        files_changed=8,
    ),
]
session_md = render_session_entry(entry_list, "Working on vault sync integration.")
assert_in("session has frontmatter", "projects_touched:", session_md)
assert_in("session has work type tag", "feature-dev", session_md)
assert_in("session has project", "obsidian-connector", session_md)
assert_in("session has completed", "Built sync module", session_md)
assert_in("session has context", "vault sync integration", session_md)

# ---------------------------------------------------------------------------
# Test vault_init
# ---------------------------------------------------------------------------

print("\n=== Vault init tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault_path = Path(tmpdir) / "test-vault"

    result = init_vault(
        vault_path=vault_path,
        github_root=str(Path.home() / "Documents" / "GitHub"),
        use_defaults=True,
    )

    assert_type("init result is dict", result, dict)
    assert_eq("init vault_path exists", vault_path.is_dir(), True)
    assert_in("init has repos_tracked", "repos_tracked", result)
    assert_eq("init has 16 default repos", result["repos_tracked"], 16)

    # Check scaffold
    assert_eq("projects/ exists", (vault_path / "projects").is_dir(), True)
    assert_eq("sessions/ exists", (vault_path / "sessions").is_dir(), True)
    assert_eq("context/ exists", (vault_path / "context").is_dir(), True)
    assert_eq("groups/ exists", (vault_path / "groups").is_dir(), True)
    assert_eq("Dashboard.md exists", (vault_path / "Dashboard.md").is_file(), True)
    assert_eq("Running TODO.md exists", (vault_path / "Running TODO.md").is_file(), True)
    assert_eq("sync_config.json exists", (vault_path / "sync_config.json").is_file(), True)

    # Check config is valid JSON
    config_data = json.loads((vault_path / "sync_config.json").read_text())
    assert_type("config repos is list", config_data["repos"], list)
    assert_eq("config has 16 repos", len(config_data["repos"]), 16)

    # Check group files
    assert_eq("AMOS group exists", (vault_path / "groups" / "AMOS.md").is_file(), True)
    assert_eq("Keiki group exists", (vault_path / "groups" / "Keiki.md").is_file(), True)

    # Check idempotency (init again should not overwrite)
    dashboard_content = (vault_path / "Dashboard.md").read_text()
    result2 = init_vault(vault_path=vault_path, use_defaults=True)
    dashboard_content2 = (vault_path / "Dashboard.md").read_text()
    assert_eq("init is idempotent (dashboard unchanged)", dashboard_content, dashboard_content2)

# ---------------------------------------------------------------------------
# Test discover_repos
# ---------------------------------------------------------------------------

print("\n=== Discover repos tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    gh = Path(tmpdir)

    # Create a fake git repo
    fake_repo = gh / "my-project"
    fake_repo.mkdir()
    (fake_repo / ".git").mkdir()
    (fake_repo / "CLAUDE.md").write_text("# Instructions")

    # Create a non-git directory
    (gh / "not-a-repo").mkdir()

    discovered = discover_repos(gh)
    assert_eq("discovered 1 repo", len(discovered), 1)
    assert_eq("discovered dir_name", discovered[0].dir_name, "my-project")
    assert_eq("discovered guidance", discovered[0].guidance_file, "CLAUDE.md")

# ---------------------------------------------------------------------------
# Test get_project_status (on this repo)
# ---------------------------------------------------------------------------

print("\n=== Project status tests ===")

# This runs against the actual obsidian-connector repo
try:
    status = get_project_status(
        "obsidian-connector",
        github_root=str(Path(__file__).resolve().parent.parent.parent),
    )
    assert_type("status is dict", status, dict)
    assert_eq("status exists", status.get("exists"), True)
    assert_eq("status is_git", status.get("is_git"), True)
    assert_in("status has branch", "branch", status)
    _check("status branch is non-empty", bool(status.get("branch")))
except Exception as e:
    _check("get_project_status", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'=' * 50}")
print(f"  {_PASS} passed, {_FAIL} failed")
print(f"{'=' * 50}")

sys.exit(1 if _FAIL > 0 else 0)
