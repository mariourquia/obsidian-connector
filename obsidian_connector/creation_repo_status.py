"""Enriched git + PR + test/build repo classifier for the Creation Dashboard.

Produces a ``RepoStatus`` snapshot per repository, enriched with:
- ahead/behind counts (relative to origin/<branch>)
- open and recently-merged PRs (via ``gh pr list``)
- optional test and build outcomes
- a ``classification`` string that drives the dashboard action lane

The runner is fully injectable so callers (and tests) can swap subprocess
without monkey-patching module globals.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from obsidian_connector.project_sync import (
    RepoEntry,
    RepoState,
    _extract_repo_state,
)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_Runner = Callable[..., "subprocess.CompletedProcess[str]"]

# ---------------------------------------------------------------------------
# Valid classification strings (order defines priority in classify())
# ---------------------------------------------------------------------------

CLASSIFICATIONS = (
    "needs-sync",
    "blocked-by-tests",
    "waiting-on-pr-review",
    "mid-implementation",
    "behind",
    "ahead",
    "blocked-by-decision",
    "dormant",
    "stale",
    "clean-and-ready",
    "ready-for-next-agent",
)


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RepoStatus:
    """Enriched status snapshot for a single repository."""

    dir_name: str
    display_name: str
    project: str          # alias for dir_name, kept for dashboard consumers
    repo_path: str
    branch: str
    head: str             # short commit SHA, or ""
    dirty: bool
    untracked: int
    ahead: int
    behind: int
    recent_commits: tuple  # tuple[str, ...]
    open_prs: tuple        # tuple[dict, ...]
    merged_prs_recent: tuple  # tuple[dict, ...]
    tests: dict            # {status, summary, ran_at}
    build: dict            # {status, detail}
    deploy: dict           # {status, detail}
    classification: str
    next_action: str
    blockers: tuple        # tuple[str, ...]
    authority_level: str   # always "repo_grounded"


# ---------------------------------------------------------------------------
# Pure public wrapper for _extract_repo_state
# ---------------------------------------------------------------------------

def extract_repo_state(repo_entry: RepoEntry, github_root: Path) -> RepoState:
    """Public wrapper around project_sync._extract_repo_state.

    Delegates entirely to the private implementation so git logic lives
    in one place.
    """
    return _extract_repo_state(repo_entry, github_root)


# ---------------------------------------------------------------------------
# classify() -- pure function, no I/O
# ---------------------------------------------------------------------------

def classify(fields: dict) -> tuple[str, str, tuple]:
    """Derive (classification, next_action, blockers) from a fields snapshot.

    Priority order matches the spec:
      1. unmerged conflicts       -> needs-sync
      2. tests failed/errored     -> blocked-by-tests
      3. open non-draft PR        -> waiting-on-pr-review
      4. dirty OR non-main branch -> mid-implementation
      5. behind > 0               -> behind
      6. ahead > 0 and clean      -> ahead
      7. needs_decision backlog   -> blocked-by-decision
      8. days_since_commit > 30   -> dormant
      9. stale freshness note     -> stale
      10. clean + main + up-to-date + no open work -> clean-and-ready
      else                        -> ready-for-next-agent
    """
    unmerged_conflicts: list[str] = fields.get("unmerged_conflicts", [])
    test_status: str = fields.get("test_status", "unknown")
    open_prs: list[dict] = fields.get("open_prs", [])
    dirty: bool = bool(fields.get("dirty", False))
    branch: str = fields.get("branch", "main")
    ahead: int = int(fields.get("ahead", 0))
    behind: int = int(fields.get("behind", 0))
    needs_decision: bool = bool(fields.get("needs_decision", False))
    days_since_commit: int = int(fields.get("days_since_commit", 0))
    stale_freshness: bool = bool(fields.get("stale_freshness", False))
    untracked: int = int(fields.get("untracked", 0))

    on_main = branch in ("main", "master")
    has_open_non_draft = any(not pr.get("is_draft", True) for pr in open_prs)

    # 1. Unmerged conflicts
    if unmerged_conflicts:
        return (
            "needs-sync",
            "Resolve merge conflicts before continuing",
            tuple(f"conflict: {f}" for f in unmerged_conflicts),
        )

    # 2. Tests failed or errored
    if test_status in ("failed", "errored"):
        return (
            "blocked-by-tests",
            "Fix failing tests before merging",
            (f"test suite {test_status}",),
        )

    # 3. Open non-draft PR awaiting review
    if has_open_non_draft:
        pr_titles = tuple(
            f"PR #{pr.get('number', '?')}: {pr.get('title', '')}"
            for pr in open_prs
            if not pr.get("is_draft", True)
        )
        return (
            "waiting-on-pr-review",
            "Await or request PR review",
            pr_titles,
        )

    # 4. Dirty tree OR non-main branch with uncommitted/staged work or ahead commits
    if dirty or (not on_main and ahead > 0):
        blockers: list[str] = []
        if dirty:
            blockers.append("uncommitted changes in working tree")
        if not on_main:
            blockers.append(f"on branch '{branch}' — not yet merged to main")
        return (
            "mid-implementation",
            "Commit, push, and open a PR",
            tuple(blockers),
        )

    # 5. Behind origin
    if behind > 0:
        return (
            "behind",
            f"Pull {behind} commit(s) from origin/{branch}",
            (f"{behind} commit(s) behind origin",),
        )

    # 6. Ahead of origin and clean
    if ahead > 0:
        return (
            "ahead",
            f"Push {ahead} commit(s) to origin/{branch}",
            (),
        )

    # 7. Linked backlog item needs a decision
    if needs_decision:
        return (
            "blocked-by-decision",
            "Make the pending decision before proceeding",
            ("backlog item flagged needs_decision",),
        )

    # 8. Dormant (> 30 days without a commit)
    if days_since_commit > 30:
        return (
            "dormant",
            f"Review whether this repo is still active ({days_since_commit}d since last commit)",
            (f"no commits in {days_since_commit} days",),
        )

    # 9. Stale freshness on a linked note
    if stale_freshness:
        return (
            "stale",
            "Refresh the stale linked note",
            ("linked note flagged stale",),
        )

    # 10. Truly clean
    if on_main and not dirty and ahead == 0 and behind == 0 and not open_prs:
        return (
            "clean-and-ready",
            "Ready to start the next task",
            (),
        )

    return (
        "ready-for-next-agent",
        "No blockers detected — queue next agent task",
        (),
    )


# ---------------------------------------------------------------------------
# Default subprocess runner
# ---------------------------------------------------------------------------

def _default_runner(
    cmd: list[str],
    *,
    cwd: str,
    timeout: int,
) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Helpers (all use the injected runner)
# ---------------------------------------------------------------------------

def _get_head_sha(repo_path: str, runner: _Runner) -> str:
    try:
        result = runner(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_path,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _get_ahead_behind(
    repo_path: str,
    branch: str,
    runner: _Runner,
) -> tuple[int, int]:
    """Return (ahead, behind) relative to origin/<branch>."""
    try:
        result = runner(
            ["git", "rev-list", "--left-right", "--count", f"origin/{branch}...HEAD"],
            cwd=repo_path,
            timeout=10,
        )
        if result.returncode != 0:
            return 0, 0
        parts = result.stdout.strip().split()
        if len(parts) != 2:
            return 0, 0
        behind, ahead = int(parts[0]), int(parts[1])
        return ahead, behind
    except Exception:
        return 0, 0


def _get_unmerged_conflicts(repo_path: str, runner: _Runner) -> list[str]:
    try:
        result = runner(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=repo_path,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f]
    except Exception:
        return []


def _fetch_prs(
    repo_path: str,
    state: str,
    limit: int,
    runner: _Runner,
) -> tuple[list[dict], str]:
    """Fetch PRs via gh. Returns (pr_list, status_note).

    status_note is "" on success, "unavailable" on any failure.
    """
    cmd = [
        "gh", "pr", "list",
        "--json", "number,title,isDraft,reviewDecision,updatedAt",
        "--state", state,
        "--limit", str(limit),
    ]
    try:
        result = runner(cmd, cwd=repo_path, timeout=15)
        if result.returncode != 0:
            return [], "unavailable"
        raw = result.stdout.strip()
        if not raw:
            return [], ""
        data = json.loads(raw)
        prs = []
        for pr in data:
            prs.append({
                "number": pr.get("number"),
                "title": pr.get("title", ""),
                "is_draft": bool(pr.get("isDraft", False)),
                "review": pr.get("reviewDecision", ""),
                "updated": pr.get("updatedAt", ""),
            })
        return prs, ""
    except (json.JSONDecodeError, KeyError, TypeError):
        return [], "unavailable"
    except Exception:
        return [], "unavailable"


def _run_tests(
    repo_path: str,
    test_cmd: str,
    now_iso: str,
    runner: _Runner,
) -> dict:
    """Run the repo's test command and classify result."""
    try:
        parts = test_cmd.split()
        result = runner(parts, cwd=repo_path, timeout=120)
        if result.returncode == 0:
            status = "passed"
        else:
            # distinguish errored (exception/import error) from failed (assertion)
            combined = (result.stdout + result.stderr).lower()
            if "error" in combined and "assert" not in combined:
                status = "errored"
            else:
                status = "failed"
        summary = (result.stdout + result.stderr)[:500].strip()
        return {"status": status, "summary": summary, "ran_at": now_iso}
    except Exception as exc:
        return {"status": "errored", "summary": str(exc)[:200], "ran_at": now_iso}


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def repo_status(
    repo_entry: RepoEntry,
    *,
    github_root: Path,
    now_iso: str,
    with_prs: bool = True,
    with_tests: bool = False,
    with_build: bool = False,
    runner: _Runner = _default_runner,
) -> RepoStatus:
    """Build an enriched RepoStatus for repo_entry.

    No-raise contract: any sub-operation failure degrades gracefully to
    an empty/unknown sub-result rather than propagating.
    """
    rs: RepoState = extract_repo_state(repo_entry, github_root)

    repo_path = rs.repo_path
    branch = rs.branch
    dirty = rs.uncommitted_count > 0 or rs.staged_count > 0
    untracked = len(rs.untracked_files)

    # --- head SHA ---
    head = _get_head_sha(repo_path, runner) if rs.is_git else ""

    # --- ahead / behind ---
    if rs.is_git and branch not in ("detached", ""):
        ahead, behind = _get_ahead_behind(repo_path, branch, runner)
    else:
        ahead, behind = 0, 0

    # --- unmerged conflicts ---
    unmerged = _get_unmerged_conflicts(repo_path, runner) if rs.is_git else []

    # --- PRs ---
    open_prs: list[dict] = []
    merged_prs: list[dict] = []
    pr_note = ""

    if with_prs and rs.is_git:
        open_prs, open_note = _fetch_prs(repo_path, "open", 20, runner)
        merged_prs, merged_note = _fetch_prs(repo_path, "merged", 10, runner)
        pr_note = open_note or merged_note

    # --- tests ---
    test_cmd = getattr(repo_entry, "test_cmd", None)
    if with_tests and test_cmd:
        tests = _run_tests(repo_path, test_cmd, now_iso, runner)
    elif test_cmd:
        tests = {"status": "not-configured", "summary": "", "ran_at": ""}
    else:
        tests = {"status": "not-configured", "summary": "", "ran_at": ""}

    # Override "not-configured" label when with_tests=True but no cmd exists
    if with_tests and not test_cmd:
        tests = {"status": "not-configured", "summary": "no test_cmd declared", "ran_at": now_iso}

    # --- build / deploy ---
    build_cmd = getattr(repo_entry, "build_cmd", None)
    deploy_check = getattr(repo_entry, "deploy_check", None)

    if with_build and build_cmd:
        try:
            parts = build_cmd.split()
            result = runner(parts, cwd=repo_path, timeout=120)
            build_status = "passed" if result.returncode == 0 else "failed"
            build = {"status": build_status, "detail": (result.stdout + result.stderr)[:300].strip()}
        except Exception as exc:
            build = {"status": "errored", "detail": str(exc)[:200]}
    elif build_cmd:
        build = {"status": "unknown", "detail": "build not run (with_build=False)"}
    else:
        build = {"status": "unknown", "detail": "no build_cmd declared"}

    if deploy_check:
        try:
            parts = deploy_check.split()
            result = runner(parts, cwd=repo_path, timeout=30)
            deploy_status = "ok" if result.returncode == 0 else "error"
            deploy = {"status": deploy_status, "detail": result.stdout.strip()[:300]}
        except Exception as exc:
            deploy = {"status": "unknown", "detail": str(exc)[:200]}
    else:
        deploy = {"status": "unknown", "detail": "no deploy_check declared"}

    # --- classify ---
    classify_fields: dict[str, Any] = {
        "unmerged_conflicts": unmerged,
        "test_status": tests.get("status", "unknown"),
        "open_prs": open_prs,
        "dirty": dirty,
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "needs_decision": False,   # caller/dashboard populates from backlog
        "days_since_commit": rs.days_since_commit,
        "stale_freshness": False,  # caller/dashboard populates from freshness engine
        "untracked": untracked,
    }
    classification, next_action, blockers = classify(classify_fields)

    # Surface pr_note as a blocker if gh was unavailable
    if pr_note == "unavailable":
        blockers = blockers + ("gh pr unavailable — run `gh auth login`",)

    return RepoStatus(
        dir_name=rs.dir_name,
        display_name=rs.display_name,
        project=rs.dir_name,
        repo_path=repo_path,
        branch=branch,
        head=head,
        dirty=dirty,
        untracked=untracked,
        ahead=ahead,
        behind=behind,
        recent_commits=tuple(rs.recent_commits),
        open_prs=tuple(open_prs),
        merged_prs_recent=tuple(merged_prs),
        tests=tests,
        build=build,
        deploy=deploy,
        classification=classification,
        next_action=next_action,
        blockers=blockers,
        authority_level="repo_grounded",
    )
