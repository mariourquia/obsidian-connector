"""Report generation engine for obsidian-connector.

Produces clean Markdown artifacts in the vault's ``Reports/`` folder,
covering weekly/monthly reviews, vault health diagnostics, project
status, and research digests.

This module uses only the stdlib -- no external dependencies.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------

class ReportType(str, Enum):
    """Supported report types."""

    weekly = "weekly"
    monthly = "monthly"
    vault_health = "vault_health"
    project_status = "project_status"
    research_digest = "research_digest"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ReportResult:
    """Outcome of a report generation run."""

    report_type: str
    path: str
    generated_at: str  # ISO datetime
    summary: dict[str, Any]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules", "__pycache__"}


def _format_date_range(start: datetime, end: datetime) -> str:
    """Human-readable date range for report headers."""
    fmt = "%Y-%m-%d"
    if start.date() == end.date():
        return start.strftime(fmt)
    return f"{start.strftime(fmt)} to {end.strftime(fmt)}"


def _write_report(vault_path: str, filename: str, content: str) -> str:
    """Write a report file to ``Reports/`` inside the vault.

    Creates the ``Reports/`` directory if it does not exist.

    Returns
    -------
    str
        Absolute path to the written report file.
    """
    reports_dir = Path(vault_path) / "Reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    target = reports_dir / filename
    target.write_text(content, encoding="utf-8")
    return str(target)


def _iter_md_files(vault_path: str):
    """Yield ``(relative_posix_path, full_Path)`` for every ``.md`` file."""
    root = Path(vault_path)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            full = Path(dirpath) / fname
            rel = full.relative_to(root).as_posix()
            yield rel, full


def _stat_safe(p: Path) -> float:
    """Return mtime or 0.0 on failure."""
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


# ---------------------------------------------------------------------------
# Report generators
# ---------------------------------------------------------------------------

def weekly_review(
    vault_path: str,
    index_store: Any | None = None,
) -> ReportResult:
    """Notes created/modified this week, tasks completed, open loops, sessions."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    week_ago_ts = week_ago.timestamp()

    created: list[str] = []
    modified: list[str] = []
    total = 0

    for rel, full in _iter_md_files(vault_path):
        total += 1
        mtime = _stat_safe(full)
        if mtime >= week_ago_ts:
            modified.append(rel)
        # Heuristic: if mtime ~= ctime the file was likely created this week.
        try:
            ctime = full.stat().st_birthtime  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            ctime = mtime
        if ctime >= week_ago_ts:
            created.append(rel)

    # Scan for tasks (checkbox lines).
    tasks_done = 0
    tasks_open = 0
    for rel, full in _iter_md_files(vault_path):
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
                tasks_done += 1
            elif stripped.startswith("- [ ]"):
                tasks_open += 1

    # Session logs (files matching daily/ pattern).
    sessions = 0
    daily_dir = Path(vault_path) / "daily"
    if daily_dir.is_dir():
        for f in daily_dir.iterdir():
            if f.suffix == ".md":
                mtime = _stat_safe(f)
                if mtime >= week_ago_ts:
                    sessions += 1

    date_range = _format_date_range(week_ago, now)
    lines = [
        f"# Weekly Review -- {date_range}",
        "",
        f"**Generated**: {now.isoformat()}",
        "",
        "## Activity",
        "",
        f"- Notes created: {len(created)}",
        f"- Notes modified: {len(modified)}",
        f"- Total vault notes: {total}",
        "",
        "## Tasks",
        "",
        f"- Completed: {tasks_done}",
        f"- Open: {tasks_open}",
        "",
        "## Sessions",
        "",
        f"- Daily notes touched: {sessions}",
        "",
    ]

    if created:
        lines.append("## New Notes")
        lines.append("")
        for n in sorted(created)[:20]:
            lines.append(f"- [[{n}]]")
        lines.append("")

    content = "\n".join(lines)
    filename = f"{now.strftime('%Y-%m-%d')}-weekly.md"
    path = _write_report(vault_path, filename, content)

    return ReportResult(
        report_type=ReportType.weekly.value,
        path=path,
        generated_at=now.isoformat(),
        summary={
            "notes_created": len(created),
            "notes_modified": len(modified),
            "tasks_done": tasks_done,
            "tasks_open": tasks_open,
            "sessions": sessions,
        },
    )


def monthly_review(
    vault_path: str,
    index_store: Any | None = None,
) -> ReportResult:
    """Aggregate of weekly data with monthly trends."""
    now = datetime.now(timezone.utc)
    month_ago = now - timedelta(days=30)
    month_ago_ts = month_ago.timestamp()

    total = 0
    modified = 0
    created = 0
    sizes: list[int] = []

    for rel, full in _iter_md_files(vault_path):
        total += 1
        mtime = _stat_safe(full)
        if mtime >= month_ago_ts:
            modified += 1
        try:
            ctime = full.stat().st_birthtime  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            ctime = mtime
        if ctime >= month_ago_ts:
            created += 1
        try:
            sizes.append(full.stat().st_size)
        except OSError:
            pass

    avg_size = sum(sizes) // max(len(sizes), 1)

    # Task velocity.
    tasks_done = 0
    tasks_open = 0
    for rel, full in _iter_md_files(vault_path):
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
                tasks_done += 1
            elif stripped.startswith("- [ ]"):
                tasks_open += 1

    date_range = _format_date_range(month_ago, now)
    lines = [
        f"# Monthly Review -- {date_range}",
        "",
        f"**Generated**: {now.isoformat()}",
        "",
        "## Growth",
        "",
        f"- Total notes: {total}",
        f"- Notes created (30d): {created}",
        f"- Notes modified (30d): {modified}",
        f"- Average note size: {avg_size} bytes",
        "",
        "## Task Velocity",
        "",
        f"- Completed: {tasks_done}",
        f"- Open: {tasks_open}",
        "",
    ]

    content = "\n".join(lines)
    filename = f"{now.strftime('%Y-%m-%d')}-monthly.md"
    path = _write_report(vault_path, filename, content)

    return ReportResult(
        report_type=ReportType.monthly.value,
        path=path,
        generated_at=now.isoformat(),
        summary={
            "total_notes": total,
            "notes_created": created,
            "notes_modified": modified,
            "tasks_done": tasks_done,
            "tasks_open": tasks_open,
            "avg_note_size": avg_size,
        },
    )


def vault_health(
    vault_path: str,
    index_store: Any | None = None,
) -> ReportResult:
    """Orphans, weakly connected clusters, stale notes, index coverage, tags."""
    from obsidian_connector.graph import build_note_index

    now = datetime.now(timezone.utc)
    stale_threshold = now.timestamp() - (90 * 86400)  # 90 days

    index = build_note_index(vault_path)

    # Total .md files on disk (for coverage calculation).
    all_md: list[str] = []
    folder_counts: Counter[str] = Counter()
    for rel, full in _iter_md_files(vault_path):
        all_md.append(rel)
        folder = rel.rsplit("/", 1)[0] if "/" in rel else "(root)"
        folder_counts[folder] += 1

    total_files = len(all_md)
    indexed_count = len(index.notes)
    coverage = (indexed_count / max(total_files, 1)) * 100

    # Orphans.
    orphan_list = sorted(index.orphans)

    # Weakly connected: notes with exactly 1 link (inbound + outbound).
    weakly: list[str] = []
    for path, entry in index.notes.items():
        total_links = len(index.forward_links.get(path, set())) + len(
            index.backlinks.get(path, set())
        )
        if total_links == 1:
            weakly.append(path)
    weakly.sort()

    # Stale notes.
    stale: list[str] = []
    for path, entry in index.notes.items():
        if entry.mtime < stale_threshold:
            stale.append(path)
    stale.sort()

    # Tag distribution.
    tag_counter: Counter[str] = Counter()
    for path, entry in index.notes.items():
        for t in entry.tags:
            tag_counter[t] += 1
    top_tags = tag_counter.most_common(10)

    # Folder distribution (top 10).
    top_folders = folder_counts.most_common(10)

    lines = [
        f"# Vault Health Report -- {now.strftime('%Y-%m-%d')}",
        "",
        f"**Generated**: {now.isoformat()}",
        "",
        "## Index Coverage",
        "",
        f"- Files on disk: {total_files}",
        f"- Files in index: {indexed_count}",
        f"- Coverage: {coverage:.1f}%",
        "",
        f"## Orphan Notes ({len(orphan_list)})",
        "",
    ]
    for o in orphan_list[:20]:
        lines.append(f"- [[{o}]]")
    lines.append("")

    lines.append(f"## Weakly Connected ({len(weakly)})")
    lines.append("")
    for w in weakly[:20]:
        lines.append(f"- [[{w}]]")
    lines.append("")

    lines.append(f"## Stale Notes (>90 days) ({len(stale)})")
    lines.append("")
    for s in stale[:20]:
        lines.append(f"- [[{s}]]")
    lines.append("")

    lines.append("## Top Tags")
    lines.append("")
    for tag, count in top_tags:
        lines.append(f"- {tag}: {count}")
    lines.append("")

    lines.append("## Folder Distribution")
    lines.append("")
    for folder, count in top_folders:
        lines.append(f"- {folder}: {count}")
    lines.append("")

    content = "\n".join(lines)
    filename = f"{now.strftime('%Y-%m-%d')}-vault-health.md"
    path_out = _write_report(vault_path, filename, content)

    return ReportResult(
        report_type=ReportType.vault_health.value,
        path=path_out,
        generated_at=now.isoformat(),
        summary={
            "total_files": total_files,
            "indexed_count": indexed_count,
            "coverage_pct": round(coverage, 1),
            "orphans": len(orphan_list),
            "weakly_connected": len(weakly),
            "stale_notes": len(stale),
            "top_tags": dict(top_tags),
            "top_folders": dict(top_folders),
        },
    )


def project_status(
    vault_path: str,
    index_store: Any | None = None,
) -> ReportResult:
    """Per-project summary from Project Tracking/ folder."""
    now = datetime.now(timezone.utc)
    pt_dir = Path(vault_path) / "Project Tracking"

    projects: list[dict[str, Any]] = []
    if pt_dir.is_dir():
        for f in sorted(pt_dir.iterdir()):
            if f.suffix != ".md":
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            mtime = _stat_safe(f)
            project_name = f.stem
            # Count tasks in the project file.
            done = sum(1 for l in text.split("\n") if l.strip().startswith("- [x]") or l.strip().startswith("- [X]"))
            open_t = sum(1 for l in text.split("\n") if l.strip().startswith("- [ ]"))
            projects.append({
                "name": project_name,
                "tasks_done": done,
                "tasks_open": open_t,
                "last_modified": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
            })

    lines = [
        f"# Project Status -- {now.strftime('%Y-%m-%d')}",
        "",
        f"**Generated**: {now.isoformat()}",
        "",
        f"**Projects tracked**: {len(projects)}",
        "",
    ]
    for p in projects:
        lines.append(f"### {p['name']}")
        lines.append("")
        lines.append(f"- Open tasks: {p['tasks_open']}")
        lines.append(f"- Done tasks: {p['tasks_done']}")
        lines.append(f"- Last modified: {p['last_modified']}")
        lines.append("")

    content = "\n".join(lines)
    filename = f"{now.strftime('%Y-%m-%d')}-project-status.md"
    path_out = _write_report(vault_path, filename, content)

    return ReportResult(
        report_type=ReportType.project_status.value,
        path=path_out,
        generated_at=now.isoformat(),
        summary={
            "project_count": len(projects),
            "projects": projects,
        },
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_GENERATORS = {
    ReportType.weekly: weekly_review,
    ReportType.monthly: monthly_review,
    ReportType.vault_health: vault_health,
    ReportType.project_status: project_status,
    ReportType.research_digest: weekly_review,  # alias for now
}


def generate_report(
    vault_path: str,
    report_type: str | ReportType,
    index_store: Any | None = None,
    config: Any | None = None,
) -> ReportResult:
    """Generate a report and write it to the vault's ``Reports/`` folder.

    Parameters
    ----------
    vault_path:
        Absolute path to the vault directory.
    report_type:
        One of the :class:`ReportType` values.
    index_store:
        Optional pre-built index (passed through to generators).
    config:
        Optional connector config (reserved for future use).

    Returns
    -------
    ReportResult
        Contains the path to the generated file and summary stats.
    """
    if isinstance(report_type, str):
        report_type = ReportType(report_type)

    generator = _GENERATORS.get(report_type)
    if generator is None:
        raise ValueError(f"Unknown report type: {report_type}")

    return generator(vault_path, index_store)
