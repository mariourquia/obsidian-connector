"""Project intelligence layer for obsidian-connector.

Compounds existing project sync features into analytics, health scoring,
changelog generation, stale detection, graduation suggestions, and
weekly project packets.

All functions operate on vault filesystem state (Markdown files, session
logs, project files) and return structured data or formatted Markdown.
No network calls, no external dependencies beyond stdlib.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TODO_RE = re.compile(r"^- \[ \] (.+)$", re.MULTILINE)
_DONE_RE = re.compile(r"^- \[[xX]\] (.+)$", re.MULTILINE)

# Folders where project files live (checked in order)
_PROJECT_FOLDERS = ("projects", "Project Tracking")

# Folders where session logs live (checked in order)
_SESSION_FOLDERS = ("sessions", "daily")

# Folder where idea cards live
_IDEAS_FOLDER = "Inbox/Project Ideas"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProjectHealth:
    """Health assessment for a single project."""

    name: str
    score: float  # 0-100
    factors: dict[str, Any] = field(default_factory=dict)
    status: str = "inactive"  # healthy | warning | stale | inactive

    def __post_init__(self) -> None:
        # Ensure factors has all required keys with defaults
        defaults = {
            "days_since_last_commit": 0,
            "open_todo_count": 0,
            "session_count_30d": 0,
            "stale_thread_count": 0,
            "idea_count": 0,
        }
        for key, default in defaults.items():
            self.factors.setdefault(key, default)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_project_dir(vault_path: Path) -> Path | None:
    """Locate the project files directory within the vault."""
    for name in _PROJECT_FOLDERS:
        candidate = vault_path / name
        if candidate.is_dir():
            return candidate
    return None


def _find_session_files(vault_path: Path) -> list[Path]:
    """Collect all session/daily Markdown files."""
    files: list[Path] = []
    for name in _SESSION_FOLDERS:
        d = vault_path / name
        if d.is_dir():
            files.extend(sorted(d.glob("*.md"), reverse=True))
    return files


def _parse_date_from_filename(filename: str) -> datetime | None:
    """Extract a date from a filename like '2026-03-23.md' or '2026-03-23-session.md'."""
    # Match YYYY-MM-DD at the start of the filename
    m = re.match(r"(\d{4}-\d{2}-\d{2})", filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            pass
    return None


def _read_file_safe(path: Path) -> str:
    """Read a file, returning empty string on any error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _extract_days_since_commit(content: str) -> int:
    """Extract days_since_commit from a project file's frontmatter or table."""
    # Try frontmatter field: last_commit: "2026-03-23 ..."
    m = re.search(r'last_commit:\s*["\']?(\d{4}-\d{2}-\d{2})', content)
    if m:
        try:
            commit_date = datetime.strptime(m.group(1), "%Y-%m-%d")
            now = datetime.now()
            return max(0, (now - commit_date).days)
        except ValueError:
            pass

    # Try activity field: activity: "active (2d ago)" or "dormant (45d)"
    m = re.search(r'activity:\s*"[^"]*\((\d+)d', content)
    if m:
        return int(m.group(1))

    return 999  # Unknown -- treat as very stale


def _count_open_todos(content: str) -> int:
    """Count unchecked TODO items in content."""
    return len(_TODO_RE.findall(content))


def _count_sessions_for_project(
    session_files: list[Path],
    project_name: str,
    since_days: int,
) -> int:
    """Count session files mentioning a project within a date window."""
    cutoff = datetime.now() - timedelta(days=since_days)
    count = 0
    for path in session_files:
        file_date = _parse_date_from_filename(path.name)
        if file_date and file_date < cutoff:
            continue
        content = _read_file_safe(path)
        if project_name.lower() in content.lower():
            count += 1
    return count


def _count_stale_threads(content: str, stale_days: int = 14) -> int:
    """Count thread-like sections with no recent activity marker.

    A thread is a ## heading that mentions branch or work. We check if the
    project file's activity label indicates staleness.
    """
    # Count branches listed in the project file
    branches = re.findall(r"^- .+\((\d+) (?:days?|weeks?) ago\)", content, re.MULTILINE)
    stale = 0
    for age_str in branches:
        try:
            if int(age_str) >= stale_days:
                stale += 1
        except ValueError:
            pass

    # Also check the activity label
    m = re.search(r'activity:\s*"(?:dormant|quiet)\s*\((\d+)d\)"', content)
    if m:
        days = int(m.group(1))
        if days >= stale_days:
            stale += 1

    return stale


def _count_ideas_for_project(vault_path: Path, project_name: str) -> int:
    """Count idea cards in the Ideas folder that reference this project."""
    ideas_dir = vault_path / _IDEAS_FOLDER
    if not ideas_dir.is_dir():
        return 0

    count = 0
    for idea_file in ideas_dir.glob("*.md"):
        content = _read_file_safe(idea_file)
        if project_name.lower() in content.lower():
            count += 1
    return count


def _compute_score(factors: dict[str, Any]) -> float:
    """Compute health score from factors, clamped to 0-100."""
    score = (
        100
        - (factors.get("days_since_last_commit", 0) * 2)
        - (factors.get("stale_thread_count", 0) * 5)
        + (factors.get("session_count_30d", 0) * 3)
        + (factors.get("idea_count", 0) * 2)
    )
    return max(0.0, min(100.0, float(score)))


def _score_to_status(score: float) -> str:
    """Map a health score to a status label."""
    if score >= 70:
        return "healthy"
    if score >= 40:
        return "warning"
    if score >= 10:
        return "stale"
    return "inactive"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def project_health(
    vault_path: Path,
    projects: list[str] | None = None,
) -> list[ProjectHealth]:
    """Compute health scores for projects in the vault.

    Parameters
    ----------
    vault_path:
        Root of the Obsidian vault.
    projects:
        Optional filter -- only score these project names.
        If None, scores all projects found in the project directory.

    Returns
    -------
    list[ProjectHealth]
        One entry per project, sorted by score descending.
    """
    project_dir = _find_project_dir(vault_path)
    if project_dir is None:
        return []

    session_files = _find_session_files(vault_path)
    results: list[ProjectHealth] = []

    project_files = sorted(project_dir.glob("*.md"))
    for pf in project_files:
        name = pf.stem
        if projects and name not in projects:
            continue

        content = _read_file_safe(pf)

        factors = {
            "days_since_last_commit": _extract_days_since_commit(content),
            "open_todo_count": _count_open_todos(content),
            "session_count_30d": _count_sessions_for_project(
                session_files, name, 30
            ),
            "stale_thread_count": _count_stale_threads(content),
            "idea_count": _count_ideas_for_project(vault_path, name),
        }

        score = _compute_score(factors)
        status = _score_to_status(score)

        results.append(ProjectHealth(
            name=name,
            score=score,
            factors=factors,
            status=status,
        ))

    results.sort(key=lambda h: h.score, reverse=True)
    return results


def project_changelog(
    vault_path: Path,
    project_name: str,
    since_days: int = 7,
) -> str:
    """Generate a Markdown changelog for a project from session logs.

    Scans session log files in daily/ and sessions/ for entries that
    mention the given project, extracts work type tags and file counts,
    and returns a formatted changelog.

    Parameters
    ----------
    vault_path:
        Root of the Obsidian vault.
    project_name:
        Name of the project to filter for.
    since_days:
        How many days back to scan. Default 7.

    Returns
    -------
    str
        Markdown-formatted changelog.
    """
    cutoff = datetime.now() - timedelta(days=since_days)
    session_files = _find_session_files(vault_path)
    since_str = cutoff.strftime("%Y-%m-%d")
    until_str = datetime.now().strftime("%Y-%m-%d")

    entries: list[dict[str, str]] = []

    for path in session_files:
        file_date = _parse_date_from_filename(path.name)
        if file_date and file_date < cutoff:
            continue

        content = _read_file_safe(path)
        if project_name.lower() not in content.lower():
            continue

        date_str = file_date.strftime("%Y-%m-%d") if file_date else path.stem

        # Extract work_type tags from frontmatter
        work_types: list[str] = []
        wt_match = re.search(r"work_type:\s*\[([^\]]*)\]", content)
        if wt_match:
            work_types = [
                t.strip() for t in wt_match.group(1).split(",") if t.strip()
            ]

        # Extract files_changed from frontmatter
        fc_match = re.search(r"files_changed:\s*(\d+)", content)
        files_changed = fc_match.group(1) if fc_match else "0"

        # Extract summary -- look for **Completed**: section items
        completed_items: list[str] = []
        in_completed = False
        for line in content.splitlines():
            if "**Completed**" in line:
                in_completed = True
                continue
            if in_completed:
                if line.startswith("- "):
                    completed_items.append(line[2:].strip())
                elif line.strip() and not line.startswith(" "):
                    in_completed = False

        summary = "; ".join(completed_items) if completed_items else "session recorded"
        work_str = ", ".join(work_types) if work_types else "general"

        entries.append({
            "date": date_str,
            "work_type": work_str,
            "files_changed": files_changed,
            "summary": summary,
        })

    # Build markdown
    lines = [
        f"# Changelog: {project_name}",
        f"",
        f"> Period: {since_str} to {until_str}",
        f"> Sessions found: {len(entries)}",
        f"",
    ]

    if not entries:
        lines.append(f"No sessions found for **{project_name}** in the last {since_days} days.")
    else:
        lines.append("| Date | Work Type | Files Changed | Summary |")
        lines.append("|------|-----------|---------------|---------|")
        for e in sorted(entries, key=lambda x: x["date"], reverse=True):
            lines.append(
                f"| {e['date']} | {e['work_type']} | {e['files_changed']} | {e['summary']} |"
            )

    lines.append("")
    return "\n".join(lines)


def detect_stale_projects(
    vault_path: Path,
    stale_days: int = 30,
) -> list[str]:
    """Detect projects with no commits AND no sessions within stale_days.

    Parameters
    ----------
    vault_path:
        Root of the Obsidian vault.
    stale_days:
        Threshold in days. Projects with no activity beyond this are stale.

    Returns
    -------
    list[str]
        Names of stale projects.
    """
    project_dir = _find_project_dir(vault_path)
    if project_dir is None:
        return []

    session_files = _find_session_files(vault_path)
    stale: list[str] = []

    for pf in sorted(project_dir.glob("*.md")):
        name = pf.stem
        content = _read_file_safe(pf)

        days = _extract_days_since_commit(content)
        if days < stale_days:
            continue

        sessions = _count_sessions_for_project(session_files, name, stale_days)
        if sessions > 0:
            continue

        stale.append(name)

    return stale


def graduation_suggestions(vault_path: Path) -> list[dict[str, Any]]:
    """Suggest idea cards ready for graduation to full projects.

    Cross-references Inbox/Project Ideas/ incubation cards with existing
    project names. An idea is suggested for graduation when it has >= 3
    related notes (approximated by backlink-style references or tag overlap).

    Parameters
    ----------
    vault_path:
        Root of the Obsidian vault.

    Returns
    -------
    list[dict]
        Each dict has: idea_path, idea_title, related_notes_count, suggested_project.
    """
    ideas_dir = vault_path / _IDEAS_FOLDER
    if not ideas_dir.is_dir():
        return []

    # Gather all note contents for backlink counting
    all_notes: list[tuple[Path, str]] = []
    for md in vault_path.rglob("*.md"):
        # Skip the ideas folder itself
        try:
            md.relative_to(ideas_dir)
            continue
        except ValueError:
            pass
        all_notes.append((md, _read_file_safe(md)))

    # Get existing project names
    project_dir = _find_project_dir(vault_path)
    existing_projects: set[str] = set()
    if project_dir:
        for pf in project_dir.glob("*.md"):
            existing_projects.add(pf.stem.lower())

    suggestions: list[dict[str, Any]] = []

    for idea_file in sorted(ideas_dir.glob("*.md")):
        idea_content = _read_file_safe(idea_file)
        idea_title = idea_file.stem

        # Count how many notes reference this idea (by filename or wikilink)
        related_count = 0
        for _note_path, note_content in all_notes:
            # Check for wikilink reference [[idea_title]] or plain mention
            if f"[[{idea_title}]]" in note_content or f"[[{idea_title}|" in note_content:
                related_count += 1
            elif idea_title.lower() in note_content.lower():
                related_count += 1

        if related_count < 3:
            continue

        # Suggest a project name -- use the idea title cleaned up
        suggested = idea_title.lower().replace(" ", "-")
        # If it matches an existing project, note that
        if suggested in existing_projects:
            suggested = f"{suggested} (exists)"

        suggestions.append({
            "idea_path": str(idea_file.relative_to(vault_path)),
            "idea_title": idea_title,
            "related_notes_count": related_count,
            "suggested_project": suggested,
        })

    return suggestions


def project_packet(
    vault_path: Path,
    days: int = 7,
) -> str:
    """Generate a weekly project packet summarizing all project activity.

    Parameters
    ----------
    vault_path:
        Root of the Obsidian vault.
    days:
        Number of days to cover. Default 7.

    Returns
    -------
    str
        Markdown-formatted weekly packet.
    """
    now = datetime.now()
    start = now - timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = now.strftime("%Y-%m-%d")

    healths = project_health(vault_path)
    session_files = _find_session_files(vault_path)

    # Overall stats
    active_count = sum(1 for h in healths if h.status == "healthy")
    warning_count = sum(1 for h in healths if h.status == "warning")
    stale_count = sum(1 for h in healths if h.status in ("stale", "inactive"))

    lines = [
        f"# Weekly Project Packet",
        f"",
        f"> Period: {start_str} to {end_str}",
        f"> Generated: {now.strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## Overview",
        f"",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total projects | {len(healths)} |",
        f"| Healthy | {active_count} |",
        f"| Warning | {warning_count} |",
        f"| Stale/Inactive | {stale_count} |",
        f"",
    ]

    # Per-project sections
    for h in healths:
        lines.append(f"## {h.name}")
        lines.append(f"")
        lines.append(f"**Status**: {h.status} (score: {h.score:.0f})")
        lines.append(f"")

        # Commits summary
        days_since = h.factors.get("days_since_last_commit", 0)
        if days_since == 0:
            lines.append("- **Commits**: active today")
        elif days_since < days:
            lines.append(f"- **Commits**: last commit {days_since}d ago")
        else:
            lines.append(f"- **Commits**: no commits in reporting period ({days_since}d ago)")

        # Sessions summary
        session_count = _count_sessions_for_project(session_files, h.name, days)
        lines.append(f"- **Sessions**: {session_count} in last {days}d")

        # TODOs
        todo_count = h.factors.get("open_todo_count", 0)
        lines.append(f"- **Open TODOs**: {todo_count}")

        # Ideas
        idea_count = h.factors.get("idea_count", 0)
        if idea_count > 0:
            lines.append(f"- **Ideas floated**: {idea_count}")

        lines.append(f"")

    # Graduation suggestions
    grads = graduation_suggestions(vault_path)
    if grads:
        lines.append("## Graduation Candidates")
        lines.append("")
        for g in grads:
            lines.append(
                f"- **{g['idea_title']}** -- {g['related_notes_count']} related notes"
                f" (suggested: {g['suggested_project']})"
            )
        lines.append("")

    return "\n".join(lines)
