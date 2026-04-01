#!/usr/bin/env python3
"""Tests for project_intelligence module."""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
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


def assert_ge(label: str, got, expected) -> None:
    _check(label, got >= expected, f"got {got!r}, expected >= {expected!r}")


def assert_le(label: str, got, expected) -> None:
    _check(label, got <= expected, f"got {got!r}, expected <= {expected!r}")


# ---------------------------------------------------------------------------
# Test imports
# ---------------------------------------------------------------------------

print("\n=== Import tests ===")

try:
    from obsidian_connector.project_intelligence import (
        ProjectHealth,
        project_health,
        project_changelog,
        detect_stale_projects,
        graduation_suggestions,
        project_packet,
    )
    _check("import project_intelligence", True)
except ImportError as e:
    _check("import project_intelligence", False, str(e))
    print(f"\nFATAL: cannot import module: {e}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _build_vault(tmpdir: str) -> Path:
    """Build a temporary vault with project files, session logs, and ideas."""
    vault = Path(tmpdir)

    # Project Tracking folder with mock project files
    projects_dir = vault / "Project Tracking"
    projects_dir.mkdir(parents=True)

    # Healthy project: recent commit, active sessions
    today = datetime.now()
    recent_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    (projects_dir / "alpha-app.md").write_text(
        f"---\n"
        f'title: "Alpha App"\n'
        f"dir: alpha-app\n"
        f"status: active\n"
        f"group: standalone\n"
        f"branch: feature/new-ui\n"
        f'last_commit: "{recent_date} 10:00:00 -0400"\n'
        f"uncommitted: 2\n"
        f'activity: "active (2d ago)"\n'
        f"---\n\n"
        f"# Alpha App\n\n"
        f"## Active Branches\n\n"
        f"- feature/new-ui (2 days ago)\n\n"
        f"## TODOs\n\n"
        f"- [ ] Write tests\n"
        f"- [ ] Update docs\n"
        f"- [x] Deploy v1\n",
        encoding="utf-8",
    )

    # Stale project: old commit, no sessions
    old_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    (projects_dir / "legacy-tool.md").write_text(
        f"---\n"
        f'title: "Legacy Tool"\n'
        f"dir: legacy-tool\n"
        f"status: active\n"
        f"group: standalone\n"
        f"branch: main\n"
        f'last_commit: "{old_date} 10:00:00 -0400"\n'
        f"uncommitted: 0\n"
        f'activity: "dormant (60d)"\n'
        f"---\n\n"
        f"# Legacy Tool\n\n"
        f"- [ ] Eventually migrate\n",
        encoding="utf-8",
    )

    # Medium-health project
    medium_date = (today - timedelta(days=15)).strftime("%Y-%m-%d")
    (projects_dir / "beta-service.md").write_text(
        f"---\n"
        f'title: "Beta Service"\n'
        f"dir: beta-service\n"
        f"status: active\n"
        f"group: standalone\n"
        f"branch: main\n"
        f'last_commit: "{medium_date} 10:00:00 -0400"\n'
        f"uncommitted: 0\n"
        f'activity: "quiet (15d)"\n'
        f"---\n\n"
        f"# Beta Service\n\n"
        f"- [ ] Add caching\n"
        f"- [ ] Fix auth bug\n"
        f"- [ ] Review PR #42\n",
        encoding="utf-8",
    )

    # Session logs
    sessions_dir = vault / "sessions"
    sessions_dir.mkdir(parents=True)

    # Recent session mentioning alpha-app
    session_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    (sessions_dir / f"{session_date}-session.md").write_text(
        f"---\n"
        f'title: "Session Log - {session_date}"\n'
        f"date: {session_date}\n"
        f"tags: [session, feature-dev]\n"
        f"projects_touched:\n"
        f"  - name: alpha-app\n"
        f"    work_type: [feature-dev, testing]\n"
        f"    files_changed: 12\n"
        f"total_files_changed: 12\n"
        f"---\n\n"
        f"## 14:00 - alpha-app\n\n"
        f"**Work type**: feature-dev, testing\n\n"
        f"**Completed**:\n"
        f"- Built new dashboard component\n"
        f"- Added unit tests for auth module\n\n"
        f"**Next steps**:\n"
        f"- Wire up API endpoints\n",
        encoding="utf-8",
    )

    # Another session 3 days ago mentioning alpha-app
    session_date2 = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    (sessions_dir / f"{session_date2}-session.md").write_text(
        f"---\n"
        f'title: "Session Log - {session_date2}"\n'
        f"date: {session_date2}\n"
        f"tags: [session, refactor]\n"
        f"projects_touched:\n"
        f"  - name: alpha-app\n"
        f"    work_type: [refactor]\n"
        f"    files_changed: 5\n"
        f"total_files_changed: 5\n"
        f"---\n\n"
        f"## 10:00 - alpha-app\n\n"
        f"**Work type**: refactor\n\n"
        f"**Completed**:\n"
        f"- Refactored config loading\n",
        encoding="utf-8",
    )

    # Session mentioning beta-service (older, outside 7d but within 30d)
    session_date3 = (today - timedelta(days=10)).strftime("%Y-%m-%d")
    (sessions_dir / f"{session_date3}-session.md").write_text(
        f"---\n"
        f'title: "Session Log - {session_date3}"\n'
        f"date: {session_date3}\n"
        f"tags: [session, bugfix]\n"
        f"projects_touched:\n"
        f"  - name: beta-service\n"
        f"    work_type: [bugfix]\n"
        f"    files_changed: 3\n"
        f"total_files_changed: 3\n"
        f"---\n\n"
        f"## 09:00 - beta-service\n\n"
        f"**Work type**: bugfix\n\n"
        f"**Completed**:\n"
        f"- Fixed race condition in queue handler\n",
        encoding="utf-8",
    )

    # Inbox/Project Ideas
    ideas_dir = vault / "Inbox" / "Project Ideas"
    ideas_dir.mkdir(parents=True)

    # Idea with many references (should graduate)
    (ideas_dir / "data-pipeline.md").write_text(
        "# Data Pipeline\n\n"
        "Build an ETL pipeline for market data.\n\n"
        "Tags: #data #pipeline #alpha-app\n",
        encoding="utf-8",
    )

    # Idea with few references (should not graduate)
    (ideas_dir / "random-thought.md").write_text(
        "# Random Thought\n\n"
        "Maybe build a CLI for something.\n",
        encoding="utf-8",
    )

    # Create notes that reference the data-pipeline idea
    notes_dir = vault / "notes"
    notes_dir.mkdir(parents=True)

    (notes_dir / "market-data-research.md").write_text(
        "# Market Data Research\n\n"
        "Related to [[data-pipeline]] idea.\n",
        encoding="utf-8",
    )

    (notes_dir / "etl-patterns.md").write_text(
        "# ETL Patterns\n\n"
        "Could use for the [[data-pipeline]] project.\n",
        encoding="utf-8",
    )

    (notes_dir / "integration-notes.md").write_text(
        "# Integration Notes\n\n"
        "The data-pipeline concept keeps coming up.\n",
        encoding="utf-8",
    )

    return vault


# ---------------------------------------------------------------------------
# Test ProjectHealth dataclass
# ---------------------------------------------------------------------------

print("\n=== ProjectHealth dataclass tests ===")

ph = ProjectHealth(name="test-project", score=75.0, status="healthy")
assert_eq("ProjectHealth.name", ph.name, "test-project")
assert_eq("ProjectHealth.score", ph.score, 75.0)
assert_eq("ProjectHealth.status", ph.status, "healthy")
assert_in("factors has days_since_last_commit", "days_since_last_commit", ph.factors)
assert_in("factors has open_todo_count", "open_todo_count", ph.factors)
assert_in("factors has session_count_30d", "session_count_30d", ph.factors)
assert_in("factors has stale_thread_count", "stale_thread_count", ph.factors)
assert_in("factors has idea_count", "idea_count", ph.factors)


# ---------------------------------------------------------------------------
# Test project_health
# ---------------------------------------------------------------------------

print("\n=== project_health tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault = _build_vault(tmpdir)

    healths = project_health(vault)

    _check("project_health returns list", isinstance(healths, list))
    assert_eq("project_health finds 3 projects", len(healths), 3)

    # Find specific projects
    by_name = {h.name: h for h in healths}

    # Alpha (healthy): 2 days since commit, 2 sessions in 30d, 2 open todos, 1 idea
    alpha = by_name["alpha-app"]
    assert_eq("alpha status is healthy", alpha.status, "healthy")
    assert_ge("alpha score >= 70", alpha.score, 70)
    assert_eq("alpha days_since_commit", alpha.factors["days_since_last_commit"], 2)
    assert_eq("alpha open_todo_count", alpha.factors["open_todo_count"], 2)
    assert_ge("alpha session_count_30d >= 2", alpha.factors["session_count_30d"], 2)

    # Legacy (stale/inactive): 60 days since commit, no sessions
    legacy = by_name["legacy-tool"]
    _check(
        "legacy status is stale or inactive",
        legacy.status in ("stale", "inactive"),
        f"got {legacy.status}",
    )
    assert_le("legacy score < 40", legacy.score, 40)

    # Beta (warning range): 15 days since commit, 1 session
    beta = by_name["beta-service"]
    _check(
        "beta status is warning or healthy",
        beta.status in ("warning", "healthy"),
        f"got {beta.status}",
    )


# ---------------------------------------------------------------------------
# Test score clamping
# ---------------------------------------------------------------------------

print("\n=== Score clamping tests ===")

from obsidian_connector.project_intelligence import _compute_score, _score_to_status

# Score should clamp to 0 for very stale project
extreme_stale = _compute_score({
    "days_since_last_commit": 200,
    "stale_thread_count": 10,
    "session_count_30d": 0,
    "idea_count": 0,
})
assert_eq("extreme stale score clamped to 0", extreme_stale, 0.0)

# Score should clamp to 100 for extremely active project
extreme_active = _compute_score({
    "days_since_last_commit": 0,
    "stale_thread_count": 0,
    "session_count_30d": 50,
    "idea_count": 20,
})
assert_eq("extreme active score clamped to 100", extreme_active, 100.0)

# Status thresholds
assert_eq("score 80 -> healthy", _score_to_status(80), "healthy")
assert_eq("score 70 -> healthy", _score_to_status(70), "healthy")
assert_eq("score 69 -> warning", _score_to_status(69), "warning")
assert_eq("score 40 -> warning", _score_to_status(40), "warning")
assert_eq("score 39 -> stale", _score_to_status(39), "stale")
assert_eq("score 10 -> stale", _score_to_status(10), "stale")
assert_eq("score 9 -> inactive", _score_to_status(9), "inactive")
assert_eq("score 0 -> inactive", _score_to_status(0), "inactive")


# ---------------------------------------------------------------------------
# Test detect_stale_projects
# ---------------------------------------------------------------------------

print("\n=== detect_stale_projects tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault = _build_vault(tmpdir)

    stale = detect_stale_projects(vault, stale_days=30)

    assert_type("stale is list", stale, list)
    assert_in("legacy-tool is stale", "legacy-tool", stale)
    _check("alpha-app is NOT stale", "alpha-app" not in stale,
           f"alpha-app found in stale list: {stale}")
    _check("beta-service is NOT stale", "beta-service" not in stale,
           f"beta-service found in stale list: {stale}")


# ---------------------------------------------------------------------------
# Test project_changelog
# ---------------------------------------------------------------------------

print("\n=== project_changelog tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault = _build_vault(tmpdir)

    # Changelog for alpha-app (should find sessions)
    cl = project_changelog(vault, "alpha-app", since_days=7)
    assert_type("changelog is str", cl, str)
    assert_in("changelog has project name", "alpha-app", cl)
    assert_in("changelog has table header", "Date", cl)
    assert_in("changelog has work type column", "Work Type", cl)
    assert_in("changelog has completed item", "Built new dashboard component", cl)

    # Changelog filtered by project name -- legacy-tool has no sessions
    cl_legacy = project_changelog(vault, "legacy-tool", since_days=7)
    assert_in("legacy changelog reports no sessions", "No sessions found", cl_legacy)

    # Changelog date range filter -- beta-service session is 10d ago, outside 7d window
    cl_beta_7d = project_changelog(vault, "beta-service", since_days=7)
    assert_in("beta 7d changelog has no sessions", "No sessions found", cl_beta_7d)

    # But within 14d window it should appear
    cl_beta_14d = project_changelog(vault, "beta-service", since_days=14)
    assert_in("beta 14d changelog has session", "beta-service", cl_beta_14d)


# ---------------------------------------------------------------------------
# Test graduation_suggestions
# ---------------------------------------------------------------------------

print("\n=== graduation_suggestions tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault = _build_vault(tmpdir)

    grads = graduation_suggestions(vault)
    assert_type("grads is list", grads, list)

    # data-pipeline has 3 referencing notes -> should be suggested
    pipeline_grads = [g for g in grads if g["idea_title"] == "data-pipeline"]
    _check("data-pipeline suggested for graduation", len(pipeline_grads) == 1,
           f"found {len(pipeline_grads)} suggestions")

    if pipeline_grads:
        g = pipeline_grads[0]
        assert_ge("data-pipeline has >= 3 related notes", g["related_notes_count"], 3)
        assert_in("suggestion has idea_path", "idea_path", g)
        assert_in("suggestion has suggested_project", "suggested_project", g)

    # random-thought has < 3 references -> should NOT be suggested
    random_grads = [g for g in grads if g["idea_title"] == "random-thought"]
    assert_eq("random-thought not suggested", len(random_grads), 0)


# ---------------------------------------------------------------------------
# Test project_packet
# ---------------------------------------------------------------------------

print("\n=== project_packet tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault = _build_vault(tmpdir)

    packet = project_packet(vault, days=7)
    assert_type("packet is str", packet, str)
    assert_in("packet has title", "Weekly Project Packet", packet)
    assert_in("packet has date range", "Period:", packet)
    assert_in("packet has overview section", "Overview", packet)
    assert_in("packet has alpha section", "alpha-app", packet)
    assert_in("packet has legacy section", "legacy-tool", packet)
    assert_in("packet has status label", "Status", packet)
    assert_in("packet mentions sessions", "Sessions", packet)
    assert_in("packet mentions TODOs", "TODOs", packet)


# ---------------------------------------------------------------------------
# Test empty vault
# ---------------------------------------------------------------------------

print("\n=== Empty vault tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    empty_vault = Path(tmpdir)

    empty_health = project_health(empty_vault)
    assert_eq("empty vault health returns empty list", empty_health, [])

    empty_stale = detect_stale_projects(empty_vault)
    assert_eq("empty vault stale returns empty list", empty_stale, [])

    empty_cl = project_changelog(empty_vault, "nonexistent", since_days=7)
    assert_in("empty vault changelog has no sessions msg", "No sessions found", empty_cl)

    empty_grads = graduation_suggestions(empty_vault)
    assert_eq("empty vault grads returns empty list", empty_grads, [])

    empty_packet = project_packet(empty_vault)
    assert_in("empty vault packet has title", "Weekly Project Packet", empty_packet)
    assert_eq("empty vault packet has 0 projects in health", len(project_health(empty_vault)), 0)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'=' * 50}")
print(f"  {_PASS} passed, {_FAIL} failed")
print(f"{'=' * 50}")

sys.exit(1 if _FAIL > 0 else 0)
