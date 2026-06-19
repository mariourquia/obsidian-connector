# tests/test_creation_dashboards.py
"""Tests for obsidian_connector.creation_dashboards (Task 5).

All tests are offline: subprocess / git / gh calls are monkeypatched or
repo_status / next_actions are replaced with canned return values.

Test groups:
  A. _table + _fence unit tests (pure helpers)
  B. generate_global_dashboard (section order, table columns, byte-stable, dry-run)
  C. generate_repo_view (section order, fence preservation)
  D. generate_project_one_pager (no-overwrite guarantee)
  E. refresh_all (dry-run writes nothing; real run writes expected set)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obsidian_connector.creation_dashboards import (
    _table,
    _fence,
    _fm,
    _state_badge,
    generate_global_dashboard,
    generate_repo_view,
    generate_project_one_pager,
    generate_project_dashboard,
    generate_projects_index,
    generate_next_actions,
    generate_stale_context,
    generate_pending_decisions,
    generate_active_sessions,
    refresh_all,
)

NOW = "2026-06-19T10:00:00Z"


# ---------------------------------------------------------------------------
# Vault helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal vault with a sync_config and a few backlog items."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    v = tmp_path / "vault"
    (v / ".obsidian").mkdir(parents=True)
    # OBSIDIAN_VAULT_PATH must be set for load_sync_config to find the vault
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(v))

    # Write a sync_config.json with two groups + one standalone repo
    # Note: group_display("mcmc") -> "MCMC"; group_display("amos") -> "AMOS"
    sync_config = {
        "github_root": str(tmp_path / "repos"),
        "repos": [
            {
                "dir_name": "mcmc-erp",
                "display_name": "MCMC ERP",
                "group": "mcmc",
                "status": "active",
                "tags": [],
            },
            {
                "dir_name": "mcmc-ehr",
                "display_name": "MCMC EHR",
                "group": "mcmc",
                "status": "active",
                "tags": [],
            },
            {
                "dir_name": "amos-web",
                "display_name": "AMOS Web",
                "group": "amos",
                "status": "active",
                "tags": [],
            },
            {
                "dir_name": "obsidian-connector",
                "display_name": "obsidian-connector",
                "group": "standalone",
                "status": "active",
                "tags": [],
            },
        ],
    }
    (v / "sync_config.json").write_text(json.dumps(sync_config), encoding="utf-8")
    return v


def _make_repo_status(
    dir_name: str = "mcmc-erp",
    classification: str = "clean-and-ready",
    next_action: str = "Ready for next task",
    dirty: bool = False,
    branch: str = "main",
    head: str = "abc1234",
    ahead: int = 0,
    behind: int = 0,
    open_prs: tuple = (),
    merged_prs_recent: tuple = (),
    blockers: tuple = (),
    recent_commits: tuple = (),
):
    from obsidian_connector.creation_repo_status import RepoStatus
    return RepoStatus(
        dir_name=dir_name,
        display_name=dir_name,
        project=dir_name,
        repo_path=f"/dev/{dir_name}",
        branch=branch,
        head=head,
        dirty=dirty,
        untracked=0,
        ahead=ahead,
        behind=behind,
        recent_commits=recent_commits,
        open_prs=open_prs,
        merged_prs_recent=merged_prs_recent,
        tests={"status": "unknown"},
        build={"status": "unknown"},
        deploy={"status": "unknown"},
        classification=classification,
        next_action=next_action,
        blockers=blockers,
        authority_level="repo_grounded",
    )


def _canned_next_actions(*args, **kwargs) -> list[dict]:
    return [
        {
            "scope": "global",
            "project": "mcmc",
            "repo": "mcmc-erp",
            "backlog_id": "bkl_test01",
            "action": "Fix the failing ERP tests",
            "reason": ["P1 priority", "impact"],
            "confidence": 0.95,
            "requires_mario_decision": False,
            "suggested_workflow": None,
            "context_pack": None,
        },
        {
            "scope": "global",
            "project": "amos",
            "repo": "amos-web",
            "backlog_id": None,
            "action": "Review open PR #42",
            "reason": ["waiting-on-pr-review"],
            "confidence": 0.7,
            "requires_mario_decision": False,
            "suggested_workflow": None,
            "context_pack": None,
        },
    ]


def _canned_repo_status(entry, *, github_root, now_iso, **kwargs):
    return _make_repo_status(dir_name=entry.dir_name)


# ===========================================================================
# A. Pure helper unit tests
# ===========================================================================

class TestTable:
    def test_basic_table(self):
        result = _table(["A", "B"], [["1", "2"], ["3", "4"]])
        lines = result.splitlines()
        assert len(lines) == 4  # header, sep, 2 data rows
        assert "A" in lines[0] and "B" in lines[0]
        # separator line: contains dashes within pipes (e.g. "| - | - |" or "| --- | --- |")
        assert "-" in lines[1] and "|" in lines[1]
        assert "1" in lines[2] and "2" in lines[2]

    def test_empty_rows(self):
        result = _table(["X", "Y"], [])
        lines = result.splitlines()
        assert len(lines) == 2  # header + sep only

    def test_column_padding(self):
        result = _table(["Short", "A very long column header"], [["x", "y"]])
        # Headers should be padded to match the longest cell
        assert "A very long column header" in result

    def test_single_column(self):
        result = _table(["Name"], [["Alice"], ["Bob"]])
        assert "Alice" in result
        assert "Bob" in result

    def test_empty_headers(self):
        result = _table([], [])
        assert result == ""

    def test_pipe_separators(self):
        result = _table(["H1", "H2"], [["v1", "v2"]])
        assert result.count("|") >= 6  # at least | H1 | H2 |


class TestFence:
    def test_basic_new_file(self):
        result = _fence("test-fence", "hello world", None)
        assert "<!-- service:test-fence:begin -->" in result
        assert "<!-- service:test-fence:end -->" in result
        assert "hello world" in result

    def test_preserves_existing_content(self):
        existing = (
            "<!-- service:test-fence:begin -->\n"
            "user wrote this\n"
            "<!-- service:test-fence:end -->"
        )
        result = _fence("test-fence", "NEW BODY", existing)
        assert "user wrote this" in result
        assert "NEW BODY" not in result

    def test_idempotent(self):
        existing = (
            "<!-- service:test-fence:begin -->\n"
            "original content\n"
            "<!-- service:test-fence:end -->"
        )
        r1 = _fence("test-fence", "body", existing)
        r2 = _fence("test-fence", "body", r1)
        assert r1 == r2

    def test_no_existing_fence_uses_body(self):
        existing = "just some text with no fence"
        result = _fence("my-fence", "default body", existing)
        assert "default body" in result

    def test_empty_body(self):
        result = _fence("x", "", None)
        assert "<!-- service:x:begin -->" in result
        assert "<!-- service:x:end -->" in result

    def test_different_fence_name_does_not_match(self):
        existing = (
            "<!-- service:other-fence:begin -->\n"
            "other content\n"
            "<!-- service:other-fence:end -->"
        )
        result = _fence("my-fence", "my body", existing)
        assert "my body" in result
        assert "other content" not in result


class TestStateBadge:
    def test_known_classifications(self):
        assert _state_badge("clean-and-ready") == "[clean]"
        assert _state_badge("mid-implementation") == "[wip]"
        assert _state_badge("blocked-by-tests") == "[tests-fail]"
        assert _state_badge("unknown") == "[unknown]"

    def test_unknown_classification(self):
        badge = _state_badge("some-new-state")
        assert badge == "[some-new-state]"


# ===========================================================================
# B. generate_global_dashboard
# ===========================================================================

class TestGenerateGlobalDashboard:

    def test_three_sections_in_order(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            generate_global_dashboard(v, now_iso=NOW, dry_run=False)

        content = (v / "Dashboard.md").read_text(encoding="utf-8")

        # Check the three sections exist in order
        idx_do_next = content.index("## ▶ Do next")
        idx_projects = content.index("## Projects")
        idx_needs_dec = content.index("## Needs decision")

        assert idx_do_next < idx_projects < idx_needs_dec, (
            "Sections must appear in order: Do next, Projects, Needs decision"
        )
        # Also check the other rollups exist and are ordered: Needs decision -> Stale -> Clean & ready
        assert "## Stale" in content
        assert "## Clean & ready" in content

        idx_stale = content.index("## Stale")
        idx_clean = content.index("## Clean & ready")
        assert idx_needs_dec < idx_stale < idx_clean, (
            "Rollup sections must appear in order: Needs decision, Stale, Clean & ready"
        )

    def test_projects_table_has_correct_columns(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            generate_global_dashboard(v, now_iso=NOW, dry_run=False)

        content = (v / "Dashboard.md").read_text(encoding="utf-8")
        # Table header row must contain all expected columns
        assert "Project" in content
        assert "Pri" in content
        assert "State" in content
        assert "Repos" in content
        assert "Flags" in content
        assert "Next action" in content

        # Columns must appear in order within the header row
        # Find the header line (first line containing all column names)
        header_line = next(
            line for line in content.splitlines()
            if "Project" in line and "Pri" in line and "State" in line
        )
        assert (
            header_line.index("Project") < header_line.index("Pri")
            < header_line.index("State") < header_line.index("Repos")
            < header_line.index("Flags") < header_line.index("Next action")
        ), f"Columns must appear in order in header line: {header_line!r}"

    def test_do_next_shows_actions(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            generate_global_dashboard(v, now_iso=NOW, dry_run=False)

        content = (v / "Dashboard.md").read_text(encoding="utf-8")
        assert "Fix the failing ERP tests" in content
        assert "Review open PR #42" in content

    def test_reruns_are_byte_stable(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            generate_global_dashboard(v, now_iso=NOW, dry_run=False)
            first = (v / "Dashboard.md").read_text(encoding="utf-8")
            generate_global_dashboard(v, now_iso=NOW, dry_run=False)
            second = (v / "Dashboard.md").read_text(encoding="utf-8")

        assert first == second, "Re-running must produce byte-identical output"

    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = generate_global_dashboard(v, now_iso=NOW, dry_run=True)

        assert result["dry_run"] is True
        assert not (v / "Dashboard.md").exists(), "dry_run must not create the file"

    def test_returns_path_and_dry_run(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = generate_global_dashboard(v, now_iso=NOW, dry_run=False)

        assert result["path"] == "Dashboard.md"
        assert result["dry_run"] is False

    def test_frontmatter_has_last_sync(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            generate_global_dashboard(v, now_iso=NOW, dry_run=False)

        content = (v / "Dashboard.md").read_text(encoding="utf-8")
        # _fm() quotes strings with special chars (colons in ISO timestamps)
        assert "last_sync:" in content
        assert NOW in content


# ===========================================================================
# C. generate_project_dashboard
# ===========================================================================

class TestGenerateProjectDashboard:

    def _dashboard_path(self, v: Path, project_slug: str) -> Path:
        from obsidian_connector import creation_projects as cp
        proj = cp.get_project(v, project_slug)
        assert proj is not None, f"Project {project_slug} not found"
        return v / "Projects" / proj.name / "Project Dashboard.md"

    def test_section_order(self, tmp_path, monkeypatch):
        """## Repos appears before ## Top backlog which appears before ## Load for an agent."""
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            generate_project_dashboard(v, "mcmc", now_iso=NOW, dry_run=False)

        content = self._dashboard_path(v, "mcmc").read_text(encoding="utf-8")

        idx_repos = content.index("## Repos")
        idx_backlog = content.index("## Top backlog")
        idx_agent = content.index("## Load for an agent")
        assert idx_repos < idx_backlog < idx_agent, (
            "Sections must appear in order: ## Repos, ## Top backlog, ## Load for an agent"
        )

    def test_repos_table_columns(self, tmp_path, monkeypatch):
        """Repos table must have Repo, Branch, State, Next columns."""
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            generate_project_dashboard(v, "mcmc", now_iso=NOW, dry_run=False)

        content = self._dashboard_path(v, "mcmc").read_text(encoding="utf-8")
        # Find the header line that contains all repo-table columns
        header_line = next(
            (line for line in content.splitlines()
             if "Repo" in line and "Branch" in line and "State" in line and "Next" in line),
            None,
        )
        assert header_line is not None, (
            "Repos table must contain a header row with Repo, Branch, State, Next columns"
        )

    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        """dry_run=True must not create Project Dashboard.md."""
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = generate_project_dashboard(v, "mcmc", now_iso=NOW, dry_run=True)

        assert result["dry_run"] is True
        path = self._dashboard_path(v, "mcmc")
        assert not path.exists(), "dry_run must not create Project Dashboard.md"

    def test_non_dry_run_returns_path_and_creates_file(self, tmp_path, monkeypatch):
        """Non-dry run must return {path, dry_run} with correct path and create the file."""
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = generate_project_dashboard(v, "mcmc", now_iso=NOW, dry_run=False)

        assert result["dry_run"] is False
        assert result["path"] is not None
        # Path must be of the form Projects/{Project}/Project Dashboard.md
        assert "Project Dashboard.md" in result["path"]
        assert "Projects" in result["path"]
        # File must exist on disk
        assert self._dashboard_path(v, "mcmc").exists(), (
            "generate_project_dashboard must create the file on a non-dry run"
        )

    def test_unknown_project_returns_error(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_project_dashboard(v, "nonexistent", now_iso=NOW, dry_run=True)
        assert result["path"] is None
        assert "error" in result


# ===========================================================================
# D. generate_repo_view
# ===========================================================================

class TestGenerateRepoView:

    def _get_repo_view_path(self, v: Path, project_slug: str, repo: str) -> Path:
        """Return the path to a repo view file, resolving the project display name."""
        from obsidian_connector import creation_projects as cp
        proj = cp.get_project(v, project_slug)
        assert proj is not None, f"Project {project_slug} not found"
        return v / "Projects" / proj.name / "Repos" / f"{repo}.md"

    def test_section_order(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with patch("obsidian_connector.creation_repo_status.repo_status",
                   side_effect=_canned_repo_status):
            generate_repo_view(v, "mcmc", "mcmc-erp", now_iso=NOW, dry_run=False)

        path = self._get_repo_view_path(v, "mcmc", "mcmc-erp")
        content = path.read_text(encoding="utf-8")

        # Check that service fence exists
        assert "<!-- service:repo-status:begin -->" in content
        assert "<!-- service:repo-status:end -->" in content

        # Check the key sections inside the fence
        assert "## Git" in content
        assert "## PRs" in content
        assert "## Tests / build / deploy" in content
        assert "## Work context" in content

        # Ordering
        idx_git = content.index("## Git")
        idx_prs = content.index("## PRs")
        idx_tbd = content.index("## Tests / build / deploy")
        idx_ctx = content.index("## Work context")
        assert idx_git < idx_prs < idx_tbd < idx_ctx

    def test_user_notes_outside_fence_preserved(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with patch("obsidian_connector.creation_repo_status.repo_status",
                   side_effect=_canned_repo_status):
            generate_repo_view(v, "mcmc", "mcmc-erp", now_iso=NOW, dry_run=False)

        repo_path = self._get_repo_view_path(v, "mcmc", "mcmc-erp")

        # Add user notes AFTER the service fence in the existing file
        original_content = repo_path.read_text(encoding="utf-8")
        user_note = "## My hand-written notes\n\nThis is important context I wrote manually."
        enriched_content = original_content + "\n\n" + user_note
        repo_path.write_text(enriched_content, encoding="utf-8")

        # Regenerate
        with patch("obsidian_connector.creation_repo_status.repo_status",
                   side_effect=_canned_repo_status):
            generate_repo_view(v, "mcmc", "mcmc-erp", now_iso=NOW, dry_run=False)

        new_content = repo_path.read_text(encoding="utf-8")
        assert "This is important context I wrote manually." in new_content, (
            "User notes outside the service fence must be preserved across regeneration"
        )

    def test_fence_content_preserved_across_rerun(self, tmp_path, monkeypatch):
        """Fence preserve: if a user edited inside the fence, that too is kept."""
        v = _make_vault(tmp_path, monkeypatch)
        with patch("obsidian_connector.creation_repo_status.repo_status",
                   side_effect=_canned_repo_status):
            generate_repo_view(v, "mcmc", "mcmc-erp", now_iso=NOW, dry_run=False)

        repo_path = self._get_repo_view_path(v, "mcmc", "mcmc-erp")

        # Simulate user editing inside the service fence
        content = repo_path.read_text(encoding="utf-8")
        begin = "<!-- service:repo-status:begin -->"
        end = "<!-- service:repo-status:end -->"
        b = content.index(begin)
        e = content.index(end)
        modified = (
            content[: b + len(begin)]
            + "\nUNIQUE_USER_EDIT_INSIDE_FENCE\n"
            + content[e:]
        )
        repo_path.write_text(modified, encoding="utf-8")

        # Regenerate
        with patch("obsidian_connector.creation_repo_status.repo_status",
                   side_effect=_canned_repo_status):
            generate_repo_view(v, "mcmc", "mcmc-erp", now_iso=NOW, dry_run=False)

        new_content = repo_path.read_text(encoding="utf-8")
        assert "UNIQUE_USER_EDIT_INSIDE_FENCE" in new_content

    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with patch("obsidian_connector.creation_repo_status.repo_status",
                   side_effect=_canned_repo_status):
            result = generate_repo_view(v, "mcmc", "mcmc-erp", now_iso=NOW, dry_run=True)

        assert result["dry_run"] is True
        repo_path = self._get_repo_view_path(v, "mcmc", "mcmc-erp")
        assert not repo_path.exists()

    def test_unknown_project_returns_error(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_repo_view(v, "nonexistent-project", "some-repo", now_iso=NOW, dry_run=True)
        assert result["path"] is None
        assert "error" in result


# ===========================================================================
# D. generate_project_one_pager
# ===========================================================================

class TestGenerateProjectOnePager:

    def _one_pager_path(self, v: Path, project_slug: str) -> Path:
        from obsidian_connector import creation_projects as cp
        proj = cp.get_project(v, project_slug)
        assert proj is not None, f"Project {project_slug} not found"
        return v / "Projects" / proj.name / "Project One-Pager.md"

    def test_creates_scaffold_when_absent(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_project_one_pager(v, "mcmc", now_iso=NOW, dry_run=False)

        assert result["created"] is True
        assert result["path"] is not None

        path = self._one_pager_path(v, "mcmc")
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "<!-- service:one-pager-goal:begin -->" in content
        assert "<!-- service:one-pager-intent:begin -->" in content

    def test_does_not_overwrite_existing(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)

        # First create
        result1 = generate_project_one_pager(v, "mcmc", now_iso=NOW, dry_run=False)
        assert result1["created"] is True

        path = self._one_pager_path(v, "mcmc")
        existing_content = path.read_text(encoding="utf-8")
        user_prose = "\n\nMY CUSTOM PROSE THAT MUST NOT BE OVERWRITTEN\n"
        path.write_text(existing_content + user_prose, encoding="utf-8")

        # Attempt to overwrite
        result2 = generate_project_one_pager(v, "mcmc", now_iso=NOW, dry_run=False)
        assert result2["created"] is False

        # Verify user prose is still there
        final_content = path.read_text(encoding="utf-8")
        assert "MY CUSTOM PROSE THAT MUST NOT BE OVERWRITTEN" in final_content

    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_project_one_pager(v, "mcmc", now_iso=NOW, dry_run=True)

        assert result["dry_run"] is True
        path = self._one_pager_path(v, "mcmc")
        assert not path.exists()

    def test_unknown_project_returns_error(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_project_one_pager(v, "nonexistent", now_iso=NOW, dry_run=True)
        assert result["path"] is None
        assert "error" in result


# ===========================================================================
# E. Focused generators
# ===========================================================================

class TestGenerateProjectsIndex:
    def test_writes_projects_md(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_projects_index(v, now_iso=NOW, dry_run=False)
        assert result["path"] == "Projects.md"
        content = (v / "Projects.md").read_text(encoding="utf-8")
        assert "# Projects" in content
        assert "Project" in content  # table header

    def test_dry_run(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_projects_index(v, now_iso=NOW, dry_run=True)
        assert result["dry_run"] is True
        assert not (v / "Projects.md").exists()


class TestGenerateNextActions:
    def test_writes_next_actions_md(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = generate_next_actions(v, now_iso=NOW, dry_run=False)

        assert result["path"] == "Next Actions.md"
        content = (v / "Next Actions.md").read_text(encoding="utf-8")
        assert "# Next Actions" in content
        assert "Fix the failing ERP tests" in content
        # Footer scoring formula
        assert "Scoring formula" in content
        assert "dashboard-weights.json" in content

    def test_dry_run(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = generate_next_actions(v, now_iso=NOW, dry_run=True)

        assert result["dry_run"] is True
        assert not (v / "Next Actions.md").exists()


class TestGenerateStaleContext:
    def test_writes_stale_context_md(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_stale_context(v, now_iso=NOW, dry_run=False)
        assert result["path"] == "Stale Context.md"
        content = (v / "Stale Context.md").read_text(encoding="utf-8")
        assert "# Stale Context" in content
        assert "## Stale" in content
        assert "## Conflicting" in content

    def test_dry_run(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_stale_context(v, now_iso=NOW, dry_run=True)
        assert result["dry_run"] is True
        assert not (v / "Stale Context.md").exists()


class TestGeneratePendingDecisions:
    def test_writes_pending_decisions_md(self, tmp_path, monkeypatch):
        from obsidian_connector import creation_backlog as cb
        v = _make_vault(tmp_path, monkeypatch)
        # Add a backlog item that needs a decision
        cb.add_backlog_item(
            v, title="Choose auth strategy", project="mcmc",
            needs_decision=True, now_iso=NOW
        )
        result = generate_pending_decisions(v, now_iso=NOW, dry_run=False)
        assert result["path"] == "Pending Decisions.md"
        content = (v / "Pending Decisions.md").read_text(encoding="utf-8")
        assert "# Pending Decisions" in content
        assert "Choose auth strategy" in content

    def test_empty_when_no_decisions(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_pending_decisions(v, now_iso=NOW, dry_run=False)
        content = (v / "Pending Decisions.md").read_text(encoding="utf-8")
        assert "No pending decisions" in content

    def test_dry_run(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_pending_decisions(v, now_iso=NOW, dry_run=True)
        assert result["dry_run"] is True
        assert not (v / "Pending Decisions.md").exists()


class TestGenerateActiveSessions:
    def test_writes_active_sessions_md(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_active_sessions(v, now_iso=NOW, dry_run=False)
        assert result["path"] == "Active Sessions.md"
        content = (v / "Active Sessions.md").read_text(encoding="utf-8")
        assert "# Active Sessions" in content
        assert "## Active" in content
        assert "## Recent sessions" in content

    def test_shows_active_session_when_present(self, tmp_path, monkeypatch):
        from obsidian_connector.creation_session import start_session
        v = _make_vault(tmp_path, monkeypatch)
        start_session(v, repo="mcmc-erp", branch="main", now_iso=NOW)
        result = generate_active_sessions(v, now_iso=NOW, dry_run=False)
        content = (v / "Active Sessions.md").read_text(encoding="utf-8")
        assert "Active session" in content

    def test_dry_run(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        result = generate_active_sessions(v, now_iso=NOW, dry_run=True)
        assert result["dry_run"] is True
        assert not (v / "Active Sessions.md").exists()


# ===========================================================================
# F. refresh_all
# ===========================================================================

class TestRefreshAll:

    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = refresh_all(v, now_iso=NOW, dry_run=True)

        assert result["dry_run"] is True
        # No files should have been written
        assert not (v / "Dashboard.md").exists()
        assert not (v / "Projects.md").exists()
        assert not (v / "Next Actions.md").exists()
        assert not (v / "Stale Context.md").exists()
        assert not (v / "Pending Decisions.md").exists()
        assert not (v / "Active Sessions.md").exists()

    def test_writes_global_set(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = refresh_all(v, now_iso=NOW, dry_run=False)

        written = result["written"]
        assert result["dry_run"] is False

        # All global dashboards must be in the written list
        expected_files = {
            "Dashboard.md",
            "Projects.md",
            "Next Actions.md",
            "Stale Context.md",
            "Pending Decisions.md",
            "Active Sessions.md",
        }
        written_set = set(written)
        for expected in expected_files:
            assert expected in written_set, f"Expected {expected} in written: {written_set}"

        # Verify files actually exist on disk
        for f in expected_files:
            assert (v / f).exists(), f"{f} was listed as written but does not exist"

    def test_scoped_to_project_writes_drilldowns(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = refresh_all(v, now_iso=NOW, scope="mcmc", dry_run=False)

        written = result["written"]
        # Project dashboard must be written
        proj_dashboard_paths = [p for p in written if "Project Dashboard" in p]
        assert len(proj_dashboard_paths) >= 1, "Project Dashboard should be written when scoped"

    def test_returns_written_list(self, tmp_path, monkeypatch):
        v = _make_vault(tmp_path, monkeypatch)
        with (
            patch("obsidian_connector.creation_next.next_actions", side_effect=_canned_next_actions),
            patch("obsidian_connector.creation_repo_status.repo_status", side_effect=_canned_repo_status),
        ):
            result = refresh_all(v, now_iso=NOW, dry_run=False)

        assert isinstance(result["written"], list)
        assert len(result["written"]) >= 6  # at least the 6 global files
