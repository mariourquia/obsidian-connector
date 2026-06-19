"""Tests for obsidian_connector.creation_repo_status.

All tests are fully offline -- the subprocess runner is always injected.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from obsidian_connector.creation_repo_status import (
    CLASSIFICATIONS,
    RepoStatus,
    classify,
    extract_repo_state,
    repo_status,
)
from obsidian_connector.project_sync import RepoEntry, RepoState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cp(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    """Build a fake CompletedProcess."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=""
    )


def _make_entry(
    dir_name: str = "my-repo",
    display_name: str = "My Repo",
    **kwargs,
) -> RepoEntry:
    entry = RepoEntry(dir_name=dir_name, display_name=display_name)
    for k, v in kwargs.items():
        object.__setattr__(entry, k, v)
    return entry


# ---------------------------------------------------------------------------
# classify() -- exhaustive branch coverage
# ---------------------------------------------------------------------------

class TestClassify:
    """One test per classification branch, plus priority-order tests."""

    def _base(self) -> dict:
        return {
            "unmerged_conflicts": [],
            "test_status": "unknown",
            "open_prs": [],
            "dirty": False,
            "branch": "main",
            "ahead": 0,
            "behind": 0,
            "needs_decision": False,
            "days_since_commit": 1,
            "stale_freshness": False,
            "untracked": 0,
        }

    def test_needs_sync(self):
        f = self._base()
        f["unmerged_conflicts"] = ["src/foo.py"]
        cls, action, blockers = classify(f)
        assert cls == "needs-sync"
        assert "conflict" in blockers[0]

    def test_blocked_by_tests_failed(self):
        f = self._base()
        f["test_status"] = "failed"
        cls, action, blockers = classify(f)
        assert cls == "blocked-by-tests"
        assert "failed" in blockers[0]

    def test_blocked_by_tests_errored(self):
        f = self._base()
        f["test_status"] = "errored"
        cls, _, blockers = classify(f)
        assert cls == "blocked-by-tests"
        assert "errored" in blockers[0]

    def test_waiting_on_pr_review(self):
        f = self._base()
        f["open_prs"] = [{"number": 42, "title": "Fix thing", "is_draft": False}]
        cls, action, blockers = classify(f)
        assert cls == "waiting-on-pr-review"
        assert "42" in blockers[0]

    def test_draft_pr_does_not_trigger_waiting(self):
        # A draft PR is still "open work", so clean-and-ready condition fails.
        # With no other signals it lands on ready-for-next-agent.
        f = self._base()
        f["open_prs"] = [{"number": 7, "title": "WIP", "is_draft": True}]
        cls, _, _ = classify(f)
        # Should NOT be waiting-on-pr-review (draft PRs are excluded from that branch)
        assert cls != "waiting-on-pr-review"
        # Should land on ready-for-next-agent (draft PR = open work but not a review blocker)
        assert cls == "ready-for-next-agent"

    def test_mid_implementation_dirty(self):
        f = self._base()
        f["dirty"] = True
        cls, action, blockers = classify(f)
        assert cls == "mid-implementation"
        assert "uncommitted" in blockers[0]

    def test_mid_implementation_non_main_branch_with_ahead(self):
        f = self._base()
        f["branch"] = "feat/my-feature"
        f["ahead"] = 2
        cls, _, blockers = classify(f)
        assert cls == "mid-implementation"
        assert any("feat/my-feature" in b for b in blockers)

    def test_behind(self):
        f = self._base()
        f["behind"] = 3
        cls, action, blockers = classify(f)
        assert cls == "behind"
        assert "3" in action

    def test_ahead_clean(self):
        f = self._base()
        f["ahead"] = 1
        # not dirty, on main
        cls, action, _ = classify(f)
        assert cls == "ahead"
        assert "1" in action

    def test_blocked_by_decision(self):
        f = self._base()
        f["needs_decision"] = True
        cls, action, blockers = classify(f)
        assert cls == "blocked-by-decision"
        assert "decision" in blockers[0]

    def test_dormant(self):
        f = self._base()
        f["days_since_commit"] = 40
        cls, action, blockers = classify(f)
        assert cls == "dormant"
        assert "40" in action or "40" in blockers[0]

    def test_stale(self):
        f = self._base()
        f["stale_freshness"] = True
        cls, _, blockers = classify(f)
        assert cls == "stale"
        assert "stale" in blockers[0]

    def test_clean_and_ready(self):
        f = self._base()
        # all defaults: main, clean, no PRs, fresh
        cls, action, blockers = classify(f)
        assert cls == "clean-and-ready"
        assert blockers == ()

    def test_ready_for_next_agent(self):
        # edge: on main, up-to-date, but has a draft PR (won't match clean-and-ready)
        f = self._base()
        f["open_prs"] = [{"number": 1, "title": "WIP", "is_draft": True}]
        cls, _, _ = classify(f)
        # draft PR present -> open_prs is non-empty -> clean-and-ready condition fails
        assert cls == "ready-for-next-agent"

    # --- priority ordering ---

    def test_tests_failed_beats_dirty(self):
        f = self._base()
        f["test_status"] = "failed"
        f["dirty"] = True
        cls, _, _ = classify(f)
        assert cls == "blocked-by-tests"

    def test_needs_sync_beats_tests_failed(self):
        f = self._base()
        f["unmerged_conflicts"] = ["foo.py"]
        f["test_status"] = "failed"
        cls, _, _ = classify(f)
        assert cls == "needs-sync"

    def test_open_pr_beats_behind(self):
        f = self._base()
        f["open_prs"] = [{"number": 5, "title": "Review me", "is_draft": False}]
        f["behind"] = 2
        cls, _, _ = classify(f)
        assert cls == "waiting-on-pr-review"

    def test_all_classifications_are_known(self):
        """Every constant in CLASSIFICATIONS is a real string."""
        assert all(isinstance(c, str) for c in CLASSIFICATIONS)
        assert len(CLASSIFICATIONS) >= 10


# ---------------------------------------------------------------------------
# extract_repo_state() -- smoke / signature test (offline)
# ---------------------------------------------------------------------------

class TestExtractRepoState:
    def test_returns_repo_state_for_missing_dir(self, tmp_path: Path):
        """extract_repo_state returns a RepoState even when the dir doesn't exist."""
        entry = RepoEntry(dir_name="nonexistent", display_name="Nonexistent")
        state = extract_repo_state(entry, tmp_path)
        assert isinstance(state, RepoState)
        assert state.dir_name == "nonexistent"
        assert not state.exists

    def test_returns_repo_state_for_non_git_dir(self, tmp_path: Path):
        (tmp_path / "bare-dir").mkdir()
        entry = RepoEntry(dir_name="bare-dir", display_name="Bare")
        state = extract_repo_state(entry, tmp_path)
        assert isinstance(state, RepoState)
        assert not state.is_git

    def test_signature_matches_repo_entry_and_path(self, tmp_path: Path):
        """Function accepts (RepoEntry, Path) and returns RepoState."""
        entry = RepoEntry(dir_name="x", display_name="X")
        result = extract_repo_state(entry, tmp_path)
        assert hasattr(result, "dir_name")
        assert hasattr(result, "branch")
        assert hasattr(result, "uncommitted_count")


# ---------------------------------------------------------------------------
# repo_status() with injected runner
# ---------------------------------------------------------------------------

class TestRepoStatus:
    """All tests inject a fake runner -- no real git/gh/subprocess."""

    def _fake_repo(self, tmp_path: Path) -> tuple[Path, RepoEntry]:
        """Create a minimal fake git repo directory structure."""
        repo_dir = tmp_path / "my-repo"
        repo_dir.mkdir()
        git_dir = repo_dir / ".git"
        git_dir.mkdir()
        # HEAD file so git branch --show-current returns something
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        return repo_dir, RepoEntry(dir_name="my-repo", display_name="My Repo")

    def _runner_factory(self, responses: dict) -> "_Runner":
        """Return a fake runner that dispatches on the first token of cmd.

        Keys are matched against the full command string via substring match.
        The 'git branch' key intercepts branch-detection; include it to
        control what branch _extract_repo_state sees.
        """

        def runner(cmd, *, cwd, timeout):
            full_key = " ".join(cmd)
            for pattern, response in responses.items():
                if pattern in full_key:
                    if isinstance(response, Exception):
                        raise response
                    return response
            return _cp("")

        return runner

    def test_open_pr_classification(self, tmp_path: Path):
        repo_dir, entry = self._fake_repo(tmp_path)
        pr_json = json.dumps([
            {"number": 99, "title": "Add feature", "isDraft": False,
             "reviewDecision": "REVIEW_REQUIRED", "updatedAt": "2026-06-18T12:00:00Z"}
        ])
        runner = self._runner_factory({
            "git rev-parse": _cp("abc1234"),
            "git rev-list": _cp("0\t0"),
            "git diff --name": _cp(""),
            "gh pr list": _cp(pr_json),
        })
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T12:00:00Z",
            runner=runner,
        )
        assert isinstance(status, RepoStatus)
        assert len(status.open_prs) == 1
        assert status.open_prs[0]["number"] == 99
        assert status.classification == "waiting-on-pr-review"

    def test_behind_classification(self, tmp_path: Path):
        """_get_ahead_behind reads ahead/behind from the injected runner.

        _extract_repo_state uses its own internal _run_git (not the injected
        runner), so branch + dirty come from real git. We create a real git
        repo so branch='main' resolves, then intercept rev-list to inject
        behind=3. We verify the field value; classify()'s priority ordering
        for behind vs dirty is covered exhaustively in TestClassify.
        """
        import subprocess as sp

        repo_dir = tmp_path / "real-repo"
        repo_dir.mkdir()
        sp.run(["git", "init"], cwd=str(repo_dir), capture_output=True)
        sp.run(["git", "checkout", "-b", "main"], cwd=str(repo_dir),
               capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"],
               cwd=str(repo_dir), capture_output=True)
        sp.run(["git", "config", "user.name", "T"],
               cwd=str(repo_dir), capture_output=True)
        (repo_dir / "README.md").write_text("hello")
        sp.run(["git", "add", "README.md"], cwd=str(repo_dir),
               capture_output=True)
        sp.run(["git", "commit", "-m", "init", "--no-gpg-sign"],
               cwd=str(repo_dir), capture_output=True)

        entry = RepoEntry(dir_name="real-repo", display_name="Real Repo")

        def runner(cmd, *, cwd, timeout):
            if "rev-list" in " ".join(cmd):
                return _cp("3\t0")  # behind=3, ahead=0
            if cmd[0] == "gh":
                return _cp("[]")
            return sp.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)

        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T12:00:00Z",
            runner=runner,
        )
        assert status.branch == "main"
        assert status.behind == 3
        assert status.ahead == 0
        # With a clean real git repo + behind=3, classification is "behind"
        # (dirty is False because we committed all files above)
        assert status.classification == "behind"

    def test_assembled_fields(self, tmp_path: Path):
        repo_dir, entry = self._fake_repo(tmp_path)
        runner = self._runner_factory({
            "git rev-parse": _cp("deadbeef"),
            "git rev-list": _cp("0\t0"),
            "git diff --name": _cp(""),
            "gh pr list": _cp("[]"),
        })
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            runner=runner,
        )
        assert status.dir_name == "my-repo"
        assert status.display_name == "My Repo"
        assert status.project == "my-repo"
        assert status.authority_level == "repo_grounded"
        assert isinstance(status.open_prs, tuple)
        assert isinstance(status.merged_prs_recent, tuple)
        assert isinstance(status.blockers, tuple)
        assert isinstance(status.tests, dict)
        assert isinstance(status.build, dict)
        assert isinstance(status.deploy, dict)

    def test_no_raise_on_gh_error(self, tmp_path: Path):
        """A runner that raises on 'gh pr list' must yield open_prs=() and not propagate."""
        repo_dir, entry = self._fake_repo(tmp_path)

        def raising_runner(cmd, *, cwd, timeout):
            if cmd[0] == "gh":
                raise RuntimeError("gh: command not found")
            return _cp("")

        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            runner=raising_runner,
        )
        assert status.open_prs == ()
        # gh unavailability surfaced as a blocker, not an exception
        assert any("gh pr unavailable" in b for b in status.blockers)

    def test_no_raise_on_gh_nonzero(self, tmp_path: Path):
        """Non-zero returncode from gh degrades gracefully."""
        repo_dir, entry = self._fake_repo(tmp_path)
        runner = self._runner_factory({
            "git rev-parse": _cp("abc"),
            "git rev-list": _cp("0\t0"),
            "git diff --name": _cp(""),
            "gh pr list": _cp("error: not authenticated", returncode=1),
        })
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            runner=runner,
        )
        assert status.open_prs == ()

    def test_no_raise_on_malformed_gh_json(self, tmp_path: Path):
        """Malformed gh JSON output degrades gracefully."""
        repo_dir, entry = self._fake_repo(tmp_path)
        runner = self._runner_factory({
            "git rev-parse": _cp("abc"),
            "git rev-list": _cp("0\t0"),
            "git diff --name": _cp(""),
            "gh pr list": _cp("{not-valid-json"),
        })
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            runner=runner,
        )
        assert status.open_prs == ()

    def test_unmerged_conflicts_classification(self, tmp_path: Path):
        repo_dir, entry = self._fake_repo(tmp_path)
        runner = self._runner_factory({
            "git rev-parse": _cp("abc"),
            "git rev-list": _cp("0\t0"),
            "git diff --name": _cp("src/main.py\nconfig.json"),
            "gh pr list": _cp("[]"),
        })
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            runner=runner,
        )
        assert status.classification == "needs-sync"

    def test_with_tests_not_configured(self, tmp_path: Path):
        """Entry without test_cmd -> status not-configured, no runner call."""
        repo_dir, entry = self._fake_repo(tmp_path)
        runner = self._runner_factory({
            "git rev-parse": _cp("abc"),
            "git rev-list": _cp("0\t0"),
            "git diff --name": _cp(""),
            "gh pr list": _cp("[]"),
        })
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            with_tests=True,
            runner=runner,
        )
        assert status.tests["status"] == "not-configured"

    def test_missing_repo_dir_still_returns_status(self, tmp_path: Path):
        """repo_status on a non-existent directory returns a RepoStatus, not an exception."""
        entry = RepoEntry(dir_name="phantom", display_name="Phantom")
        runner = self._runner_factory({})
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            runner=runner,
        )
        assert isinstance(status, RepoStatus)
        assert status.authority_level == "repo_grounded"

    def test_with_prs_false_skips_gh(self, tmp_path: Path):
        """with_prs=False must not call gh at all."""
        repo_dir, entry = self._fake_repo(tmp_path)
        gh_called = []

        def runner(cmd, *, cwd, timeout):
            if cmd[0] == "gh":
                gh_called.append(True)
                return _cp("[]")
            return _cp("")

        repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            with_prs=False,
            runner=runner,
        )
        assert not gh_called

    # Fix 1 -- with_tests=False + declared test_cmd must yield "unknown", not "not-configured"
    def test_with_tests_false_and_declared_cmd_yields_unknown(self, tmp_path: Path):
        """with_tests=False even when test_cmd is declared must return status=unknown."""
        repo_dir, entry = self._fake_repo(tmp_path)
        object.__setattr__(entry, "test_cmd", "pytest -q")
        runner = self._runner_factory({
            "git rev-parse": _cp("abc"),
            "git rev-list": _cp("0\t0"),
            "git diff --name": _cp(""),
            "gh pr list": _cp("[]"),
        })
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            with_tests=False,
            runner=runner,
        )
        assert status.tests["status"] == "unknown", (
            f"Expected 'unknown' when with_tests=False but got {status.tests['status']!r}"
        )

    def test_with_tests_true_and_no_cmd_yields_not_configured(self, tmp_path: Path):
        """with_tests=True but no test_cmd declared must return status=not-configured."""
        repo_dir, entry = self._fake_repo(tmp_path)
        # Ensure no test_cmd attribute exists
        assert not hasattr(entry, "test_cmd") or getattr(entry, "test_cmd", None) is None
        runner = self._runner_factory({
            "git rev-parse": _cp("abc"),
            "git rev-list": _cp("0\t0"),
            "git diff --name": _cp(""),
            "gh pr list": _cp("[]"),
        })
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            with_tests=True,
            runner=runner,
        )
        assert status.tests["status"] == "not-configured", (
            f"Expected 'not-configured' when with_tests=True + no cmd but got {status.tests['status']!r}"
        )

    # Fix 2 -- extract_repo_state raising must return a degraded RepoStatus, not propagate
    def test_no_raise_when_extract_repo_state_raises(self, tmp_path: Path, monkeypatch):
        """When extract_repo_state raises, repo_status must return a degraded RepoStatus."""
        entry = RepoEntry(dir_name="boom-repo", display_name="Boom")

        import obsidian_connector.creation_repo_status as crs_mod
        monkeypatch.setattr(
            crs_mod,
            "extract_repo_state",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated failure")),
        )

        runner = self._runner_factory({})
        status = repo_status(
            entry,
            github_root=tmp_path,
            now_iso="2026-06-18T00:00:00Z",
            runner=runner,
        )
        assert isinstance(status, RepoStatus)
        assert status.classification == "unknown"
        assert any("repo state extraction failed" in b for b in status.blockers)
        assert status.dir_name == "boom-repo"
        assert status.display_name == "Boom"


# ---------------------------------------------------------------------------
# __init__.py export test
# ---------------------------------------------------------------------------

def test_exports_from_package():
    from obsidian_connector import __all__ as exports
    for name in ("RepoStatus", "repo_status", "classify", "extract_repo_state"):
        assert name in exports, f"{name} not in __all__"
