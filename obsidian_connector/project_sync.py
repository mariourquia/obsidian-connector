"""Project sync engine for obsidian-connector.

Syncs git repository state into an Obsidian vault, generating per-project
Markdown files, a dashboard, active threads, session logs with structured
tags for time-series analysis, and a running TODO list with completion
tracking.

Replaces the standalone bash script (sync-creation-vault) with a
cross-platform Python implementation that integrates with the plugin's
config, audit, and error infrastructure.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obsidian_connector.audit import log_action
from obsidian_connector.config import resolve_vault_path
from obsidian_connector.errors import ObsidianCLIError, VaultNotFound

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GIT_TIMEOUT = 10  # seconds per git command

_DEFAULT_GITHUB_ROOT = Path.home() / "Documents" / "GitHub"

SYNC_CONFIG_FILENAME = "sync_config.json"

# Default subdirectory for sync output within the vault.
# Keeps project tracking isolated from the user's own notes.
# Set to "" in sync_config.json to use the vault root (only for
# dedicated project-tracking vaults like "creation").
DEFAULT_SYNC_SUBDIR = "Project Tracking"

# Work type tags for session classification
WORK_TYPES = frozenset({
    "feature-dev",
    "bugfix",
    "refactor",
    "research",
    "ops",
    "docs",
    "testing",
    "review",
    "planning",
    "setup",
})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RepoEntry:
    """A single repository to track."""

    dir_name: str
    display_name: str
    guidance_file: str = "CLAUDE.md"
    status: str = "active"
    group: str = "standalone"
    tags: list[str] = field(default_factory=list)


@dataclass
class RepoState:
    """Git state snapshot for a single repository."""

    dir_name: str
    display_name: str
    group: str
    status: str
    repo_path: str = ""  # absolute path to the repo directory
    branch: str = "main"
    last_commit_date: str = "unknown"
    last_commit_msg: str = "no commits"
    last_commit_author: str = "unknown"
    uncommitted_count: int = 0
    staged_count: int = 0
    recent_commits: list[str] = field(default_factory=list)
    active_branches: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    uncommitted_short: str = ""  # git status --short output
    days_since_commit: int = 0
    activity_label: str = "active"
    exists: bool = True
    is_git: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class SessionEntry:
    """A session log entry for one project."""

    project: str
    work_types: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    files_changed: int = 0


@dataclass
class TodoItem:
    """A single TODO item with source tracking."""

    text: str
    source: str  # file path or project name
    created_date: str = ""
    completed: bool = False
    completed_date: str = ""


@dataclass
class SyncConfig:
    """Configuration for project sync."""

    github_root: Path = field(default_factory=lambda: _DEFAULT_GITHUB_ROOT)
    vault_subdir: str = ""  # subdirectory within the vault for sync output
    repos: list[RepoEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Group display names
# ---------------------------------------------------------------------------

GROUP_DISPLAY: dict[str, str] = {
    "amos": "AMOS",
    "keiki": "Keiki",
    "mcmc": "MCMC",
    "signalforge": "SignalForge",
    "standalone": "Standalone",
    "research": "Research",
}


def group_display(group: str) -> str:
    return GROUP_DISPLAY.get(group, group)


# ---------------------------------------------------------------------------
# Default repo registry (matches the user's existing setup)
# ---------------------------------------------------------------------------

def default_repos() -> list[RepoEntry]:
    """Return the default repo registry."""
    return [
        RepoEntry("site", "mariourquia.com (Portfolio OS)", "claude.md", "active", "standalone",
                   ["portfolio", "next-js", "react", "vercel", "retro-ui", "personal-brand"]),
        RepoEntry("cre-asset-mgmt-os", "AMOS Backend", "CLAUDE.md", "active", "amos",
                   ["cre", "commercial-real-estate", "fastapi", "python", "backend", "fintech"]),
        RepoEntry("fe-cre-asset-mgmt-os", "AMOS Frontend", "CLAUDE.md", "active", "amos",
                   ["cre", "commercial-real-estate", "next-js", "typescript", "mui", "frontend", "fintech"]),
        RepoEntry("cre-skills-plugin", "CRE Skills Plugin", "README.md", "active", "amos",
                   ["cre", "commercial-real-estate", "claude-code", "plugin", "ai-skills"]),
        RepoEntry("keiki", "Keiki Monorepo", "AGENTS.md", "active", "keiki",
                   ["childcare", "marketplace", "monorepo"]),
        RepoEntry("keiki-platform", "Keiki Backend", "AGENTS.md", "active", "keiki",
                   ["childcare", "marketplace", "fastapi", "python", "azure", "backend"]),
        RepoEntry("keiki-ios", "Keiki iOS", "AGENTS.md", "active", "keiki",
                   ["childcare", "marketplace", "swiftui", "ios", "mobile"]),
        RepoEntry("mcmc-erp", "MCMC ERP Backend", "CLAUDE.md", "active", "mcmc",
                   ["healthcare", "honduras", "erp", "fastapi", "python", "backend", "multi-tenant"]),
        RepoEntry("mcmc-erp-web", "MCMC ERP Frontend", "CLAUDE.md", "active", "mcmc",
                   ["healthcare", "honduras", "erp", "next-js", "typescript", "shadcn", "frontend"]),
        RepoEntry("mcmc-ehr", "MCMC EHR Backend", "CLAUDE.md", "active", "mcmc",
                   ["healthcare", "honduras", "ehr", "fastapi", "python", "backend"]),
        RepoEntry("mcmc-ehr-web", "MCMC EHR Frontend", "CLAUDE.md", "active", "mcmc",
                   ["healthcare", "honduras", "ehr", "next-js", "typescript", "frontend"]),
        RepoEntry("signalforge", "SignalForge", "CLAUDE.md", "active", "signalforge",
                   ["quant", "finance", "next-js", "supabase", "open-source"]),
        RepoEntry("signalforge-opencore", "SignalForge Open-Core DSL", "README.md", "active", "signalforge",
                   ["quant", "finance", "typescript", "dsl", "compiler", "open-source"]),
        RepoEntry("harness-engineering", "Harness Engineering", "AGENTS.md", "active", "standalone",
                   ["engineering", "python", "docs-as-code", "framework"]),
        RepoEntry("obsidian-connector", "Obsidian Connector", "CLAUDE.md", "active", "standalone",
                   ["obsidian", "mcp", "claude-code", "plugin", "knowledge-management"]),
        RepoEntry("skills-creation-agent", "Skill Factory", "README.md", "active", "standalone",
                   ["skill-factory", "agent-skills", "python", "cli", "registry", "automation"]),
        RepoEntry("rag-fin-midterm-1", "Course RAG Engine", "README.md", "active", "research",
                   ["rag", "finance", "education", "python", "llm-evaluation", "retrieval", "nyu-stern"]),
    ]


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command with timeout. Returns stdout or empty string on error."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _extract_repo_state(entry: RepoEntry, github_root: Path) -> RepoState:
    """Extract git state for a single repository."""
    repo_path = github_root / entry.dir_name

    state = RepoState(
        dir_name=entry.dir_name,
        display_name=entry.display_name,
        group=entry.group,
        status=entry.status,
        repo_path=str(repo_path),
        tags=["project", entry.group] + entry.tags,
    )

    if not repo_path.is_dir():
        state.exists = False
        state.is_git = False
        state.activity_label = "missing"
        return state

    if not (repo_path / ".git").is_dir():
        state.is_git = False
        state.activity_label = "no-git"
        state.tags.append("no-git")
        return state

    # Branch
    branch = _run_git(["branch", "--show-current"], repo_path)
    state.branch = branch if branch else "detached"

    # Last commit
    state.last_commit_date = _run_git(["log", "-1", "--format=%ci"], repo_path) or "unknown"
    state.last_commit_msg = _run_git(["log", "-1", "--format=%s"], repo_path) or "no commits"
    state.last_commit_author = _run_git(["log", "-1", "--format=%an"], repo_path) or "unknown"

    # Counts and short status
    porcelain = _run_git(["status", "--porcelain"], repo_path)
    state.uncommitted_count = len(porcelain.splitlines()) if porcelain else 0
    short_status = _run_git(["status", "--short"], repo_path)
    state.uncommitted_short = short_status[:2000] if short_status else ""

    cached = _run_git(["diff", "--cached", "--name-only"], repo_path)
    state.staged_count = len(cached.splitlines()) if cached else 0

    # Recent commits (7 days)
    recent = _run_git(["log", "--since=7 days ago", "--oneline", "--no-merges", "-15"], repo_path)
    state.recent_commits = recent.splitlines() if recent else []

    # Active branches
    branches_raw = _run_git(
        ["branch", "--sort=-committerdate", "--format=%(refname:short) (%(committerdate:relative))"],
        repo_path,
    )
    if branches_raw:
        state.active_branches = [
            b for b in branches_raw.splitlines()
            if not b.startswith(("main ", "master "))
        ][:10]

    # Modified files
    modified = _run_git(["diff", "--name-only"], repo_path)
    state.modified_files = modified.splitlines()[:15] if modified else []

    # Untracked files
    untracked = _run_git(["ls-files", "--others", "--exclude-standard"], repo_path)
    state.untracked_files = untracked.splitlines()[:10] if untracked else []

    # Days since last commit
    epoch_str = _run_git(["log", "-1", "--format=%ct"], repo_path)
    if epoch_str and epoch_str.isdigit():
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        state.days_since_commit = (now_epoch - int(epoch_str)) // 86400
    else:
        state.days_since_commit = 999

    if state.days_since_commit > 30:
        state.activity_label = f"dormant ({state.days_since_commit}d)"
    elif state.days_since_commit > 7:
        state.activity_label = f"quiet ({state.days_since_commit}d)"
    else:
        state.activity_label = f"active ({state.days_since_commit}d ago)"

    return state


# ---------------------------------------------------------------------------
# Markdown generators
# ---------------------------------------------------------------------------

def _render_project_file(state: RepoState) -> str:
    """Render a per-project Markdown file."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    tags_yaml = "\n".join(f"  - {t}" for t in state.tags)

    if not state.exists:
        return (
            f"---\n"
            f"title: \"{state.display_name}\"\n"
            f"status: missing\n"
            f"group: {state.group}\n"
            f"last_sync: \"{now}\"\n"
            f"tags:\n{tags_yaml}\n  - missing\n"
            f"---\n\n"
            f"# {state.display_name}\n\n"
            f"> Part of [[{group_display(state.group)}]] project group\n\n"
            f"> [!warning] Directory not found\n"
        )

    if not state.is_git:
        return (
            f"---\n"
            f"title: \"{state.display_name}\"\n"
            f"dir: {state.dir_name}\n"
            f"status: {state.status}\n"
            f"group: {state.group}\n"
            f"last_sync: \"{now}\"\n"
            f"tags:\n{tags_yaml}\n  - no-git\n"
            f"---\n\n"
            f"# {state.display_name}\n\n"
            f"> Part of [[{group_display(state.group)}]] project group\n\n"
            f"| Field | Value |\n"
            f"|-------|-------|\n"
            f"| Path | `{state.repo_path}` |\n"
            f"| Git | not initialized |\n"
            f"| Activity | directory exists, no version control |\n"
        )

    lines = [
        f"---",
        f"title: \"{state.display_name}\"",
        f"dir: {state.dir_name}",
        f"status: {state.status}",
        f"group: {state.group}",
        f"branch: {state.branch}",
        f"last_commit: \"{state.last_commit_date}\"",
        f"uncommitted: {state.uncommitted_count}",
        f"activity: \"{state.activity_label}\"",
        f"last_sync: \"{now}\"",
        f"tags:",
        tags_yaml,
        f"---",
        f"",
        f"# {state.display_name}",
        f"",
        f"> Part of [[{group_display(state.group)}]] project group",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Path | `{state.repo_path}` |",
        f"| Branch | `{state.branch}` |",
        f"| Last commit | {state.last_commit_msg} |",
        f"| Last commit date | {state.last_commit_date} |",
        f"| Author | {state.last_commit_author} |",
        f"| Uncommitted changes | {state.uncommitted_count} |",
        f"| Staged | {state.staged_count} |",
        f"| Activity | {state.activity_label} |",
        f"",
    ]

    if state.branch not in ("main", "master", "detached"):
        lines += [
            f"## Current Focus",
            f"",
            f"Currently on branch `{state.branch}`",
            f"",
        ]

    if state.uncommitted_count > 0:
        lines += [
            f"## Uncommitted Changes",
            f"",
            f"```",
            state.uncommitted_short if state.uncommitted_short else "(could not read)",
            f"```",
            f"",
        ]

    if state.modified_files:
        lines.append("## Modified Files")
        lines.append("")
        for f in state.modified_files:
            lines.append(f"- `{f}`")
        lines.append("")

    if state.recent_commits:
        lines.append("## Recent Commits (7d)")
        lines.append("")
        for c in state.recent_commits:
            lines.append(f"- {c}")
        lines.append("")

    if state.active_branches:
        lines.append("## Active Branches")
        lines.append("")
        for b in state.active_branches:
            lines.append(f"- {b}")
        lines.append("")

    return "\n".join(lines)


def _render_dashboard(states: list[RepoState]) -> str:
    """Render the Dashboard.md file."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"---",
        f"title: Creation Dashboard",
        f"last_sync: \"{now}\"",
        f"tags: [dashboard, index]",
        f"---",
        f"",
        f"# Creation Dashboard",
        f"",
        f"> Last synced: **{now}**",
        f"",
        f"## Projects",
        f"",
        f"| Project | Branch | Activity | Uncommitted | Group |",
        f"|---------|--------|----------|-------------|-------|",
    ]

    for s in states:
        if not s.exists or not s.is_git:
            lines.append(
                f"| [[{s.dir_name}]] | -- | {s.activity_label} | -- | [[{group_display(s.group)}]] |"
            )
        else:
            lines.append(
                f"| [[{s.dir_name}]] | `{s.branch}` | {s.activity_label} "
                f"| {s.uncommitted_count} | [[{group_display(s.group)}]] |"
            )

    # Collect unique groups for the quick links
    groups: dict[str, list[str]] = {}
    for s in states:
        groups.setdefault(s.group, []).append(s.dir_name)

    lines += [
        f"",
        f"## Quick Links",
        f"",
        f"- [[Running TODO]] -- canonical open items across all projects",
        f"- [[active-threads|Active Threads]] -- what's in progress across all projects",
        f"- [[sessions/|Session Logs]] -- conversation context snapshots",
        f"",
        f"## Project Groups",
        f"",
    ]

    for group, members in sorted(groups.items()):
        display = group_display(group)
        member_links = " + ".join(f"[[{m}]]" for m in members)
        lines.append(f"- [[{display}]] -- {member_links}")

    return "\n".join(lines)


def _render_active_threads(states: list[RepoState]) -> str:
    """Render the active-threads.md file."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"---",
        f"title: Active Threads",
        f"last_sync: \"{now}\"",
        f"tags: [context, threads]",
        f"---",
        f"",
        f"# Active Threads",
        f"",
        f"> Auto-detected from branch names, uncommitted work, and recent activity.",
        f"> Last synced: **{now}**",
        f"",
    ]

    # Filter to repos with active work, sort by most recently active first
    active = [
        s for s in states
        if s.is_git
        and (s.branch not in ("main", "master") or s.uncommitted_count > 0)
    ]
    active.sort(key=lambda s: (s.days_since_commit, -s.uncommitted_count))

    for s in active:
        lines.append(f"## [[{s.dir_name}|{s.display_name}]]")
        lines.append("")

        if s.branch not in ("main", "master"):
            lines.append(f"- **Branch**: `{s.branch}`")

        if s.uncommitted_count > 0:
            lines.append(f"- **Uncommitted**: {s.uncommitted_count} files")
            if s.uncommitted_short:
                for line in s.uncommitted_short.splitlines()[:5]:
                    lines.append(f"  - `{line.strip()}`")
                remaining = s.uncommitted_count - 5
                if remaining > 0:
                    lines.append(f"  - ... and {remaining} more")

        lines.append(f"- **Last commit**: {s.last_commit_msg}")
        lines.append("")

    if len(active) == 0:
        lines.append("> All projects are on main with clean working trees.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Running TODO
# ---------------------------------------------------------------------------

_TODO_RE = re.compile(r"^- \[ \] (.+)$", re.MULTILINE)
_DONE_RE = re.compile(r"^- \[[xX]\] (.+)$", re.MULTILINE)


def _scan_vault_todos(vault_path: Path) -> tuple[list[TodoItem], list[TodoItem]]:
    """Scan daily notes and project files for open/completed TODO items."""
    open_items: list[TodoItem] = []
    done_items: list[TodoItem] = []

    # Scan daily notes (common locations)
    daily_dirs = [
        vault_path / "daily",
        vault_path / "Daily Notes",
        vault_path / "Journal",
    ]

    scan_paths: list[Path] = []
    for d in daily_dirs:
        if d.is_dir():
            scan_paths.extend(sorted(d.glob("*.md"), reverse=True)[:30])

    # Also scan Inbox and project-related folders (capped for performance)
    for folder_name in ("Inbox", "projects", "Projects"):
        folder = vault_path / folder_name
        if folder.is_dir():
            scan_paths.extend(list(folder.glob("*.md"))[:100])

    for note_path in scan_paths:
        try:
            content = note_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel = str(note_path.relative_to(vault_path))

        for match in _TODO_RE.finditer(content):
            open_items.append(TodoItem(
                text=match.group(1).strip(),
                source=rel,
                created_date=note_path.stem if note_path.stem[:4].isdigit() else "",
            ))

        for match in _DONE_RE.finditer(content):
            done_items.append(TodoItem(
                text=match.group(1).strip(),
                source=rel,
                completed=True,
            ))

    return open_items, done_items


def _render_running_todo(
    vault_path: Path,
    existing_content: str | None = None,
) -> str:
    """Render the Running TODO.md note.

    Scans the vault for open/completed TODO items and produces a living
    list. Previously-tracked items that are now completed get moved to
    the Completed section with a timestamp.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_slug = datetime.now().strftime("%Y-%m-%d")

    open_items, done_items = _scan_vault_todos(vault_path)

    # Track which items were previously open but are now done
    newly_completed: list[str] = []
    if existing_content:
        prev_open = set(_TODO_RE.findall(existing_content))
        done_texts = {item.text for item in done_items}
        newly_completed = [t for t in prev_open if t in done_texts]

    # Group open items by source
    by_source: dict[str, list[TodoItem]] = {}
    for item in open_items:
        by_source.setdefault(item.source, []).append(item)

    lines = [
        f"---",
        f"title: Running TODO",
        f"last_sync: \"{now}\"",
        f"tags: [todo, index, running-list]",
        f"total_open: {len(open_items)}",
        f"---",
        f"",
        f"# Running TODO",
        f"",
        f"> Canonical list of all open items across the vault.",
        f"> Last synced: **{now}** | **{len(open_items)}** open items",
        f"",
    ]

    if not open_items:
        lines.append("> No open TODO items found. Nice work!")
        lines.append("")
    else:
        for source, items in sorted(by_source.items()):
            # Make source into a wikilink if it's a .md file
            source_display = source.replace(".md", "")
            lines.append(f"### [[{source_display}]]")
            lines.append("")
            for item in items:
                lines.append(f"- [ ] {item.text}")
            lines.append("")

    # Completed section
    lines.append("---")
    lines.append("")
    lines.append("## Completed")
    lines.append("")

    if newly_completed:
        lines.append(f"### Completed on {date_slug}")
        lines.append("")
        for text in newly_completed:
            lines.append(f"- [x] {text}")
        lines.append("")

    # Append recent completions from existing content
    if existing_content:
        completed_section = existing_content.split("## Completed")
        if len(completed_section) > 1:
            prev_completed = completed_section[1].strip()
            # Keep last 50 completed items to prevent unbounded growth
            prev_lines = prev_completed.splitlines()
            kept = []
            count = 0
            for line in prev_lines:
                if line.startswith("- [x]"):
                    count += 1
                    if count > 50:
                        continue
                kept.append(line)
            if kept:
                lines.extend(kept)

    if not newly_completed and (not existing_content or "## Completed" not in existing_content):
        lines.append("> No recently completed items tracked yet.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session logging
# ---------------------------------------------------------------------------

def render_session_entry(
    entries: list[SessionEntry],
    session_context: str = "",
) -> str:
    """Render a session log entry with structured frontmatter for time-series analysis."""
    now = datetime.now()
    date_slug = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    # Aggregate tags
    all_work_types: set[str] = set()
    all_projects: list[str] = []
    total_files = 0
    for e in entries:
        all_work_types.update(e.work_types)
        all_projects.append(e.project)
        total_files += e.files_changed

    # Build projects_touched YAML
    projects_yaml_lines = []
    for e in entries:
        projects_yaml_lines.append(f"  - name: {e.project}")
        if e.work_types:
            wt = ", ".join(e.work_types)
            projects_yaml_lines.append(f"    work_type: [{wt}]")
        if e.files_changed:
            projects_yaml_lines.append(f"    files_changed: {e.files_changed}")
    projects_yaml = "\n".join(projects_yaml_lines)

    # Filter to canonical work types; pass through unknown ones but warn
    validated_types = {wt for wt in all_work_types if wt in WORK_TYPES}
    extra_types = all_work_types - WORK_TYPES
    all_tags = validated_types | extra_types  # keep unknowns, don't silently drop
    work_type_tags = ", ".join(sorted(all_tags)) if all_tags else "general"

    lines = [
        f"---",
        f"title: \"Session Log - {date_slug}\"",
        f"date: {date_slug}",
        f"tags: [session, {work_type_tags}]",
        f"projects_touched:",
        projects_yaml,
        f"total_files_changed: {total_files}",
        f"---",
        f"",
    ]

    for e in entries:
        lines.append(f"## {time_str} - {e.project}")
        lines.append("")

        wt_display = ", ".join(e.work_types) if e.work_types else "general"
        lines.append(f"**Work type**: {wt_display}")
        lines.append("")

        if e.completed:
            lines.append("**Completed**:")
            for item in e.completed:
                lines.append(f"- {item}")
            lines.append("")

        if e.next_steps:
            lines.append("**Next steps**:")
            for item in e.next_steps:
                lines.append(f"- {item}")
            lines.append("")

        if e.decisions:
            lines.append("**Decisions/Notes**:")
            for item in e.decisions:
                lines.append(f"- {item}")
            lines.append("")

    if session_context:
        lines.append("## Session Context")
        lines.append("")
        lines.append(session_context)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_sync_config(vault: str | None = None) -> SyncConfig:
    """Load sync configuration.

    Checks for sync_config.json in the vault root, then falls back to
    defaults.
    """
    import json

    config = SyncConfig()

    try:
        vault_path = resolve_vault_path(vault)
    except VaultNotFound:
        return config

    config_file = vault_path / SYNC_CONFIG_FILENAME
    has_config = config_file.is_file()

    if has_config:
        try:
            with open(config_file) as f:
                raw = json.load(f)
            if "github_root" in raw:
                config.github_root = Path(raw["github_root"]).expanduser()
            # vault_subdir: "" means vault root (explicit opt-in for
            # dedicated project vaults). Absence means use default subdir.
            if "vault_subdir" in raw:
                config.vault_subdir = raw["vault_subdir"]
            else:
                config.vault_subdir = DEFAULT_SYNC_SUBDIR
            if "repos" in raw:
                config.repos = [
                    RepoEntry(
                        dir_name=r["dir_name"],
                        display_name=r.get("display_name", r["dir_name"]),
                        guidance_file=r.get("guidance_file", "CLAUDE.md"),
                        status=r.get("status", "active"),
                        group=r.get("group", "standalone"),
                        tags=r.get("tags", []),
                    )
                    for r in raw["repos"]
                    # Reject dir_name with path separators or traversal
                    if "/" not in r.get("dir_name", "")
                    and ".." not in r.get("dir_name", "")
                    and "\x00" not in r.get("dir_name", "")
                ]
        except (json.JSONDecodeError, KeyError, TypeError):
            import sys
            print(
                f"warning: could not parse {config_file}, using defaults",
                file=sys.stderr,
            )

    # If no config file found, default to safe subdir to avoid
    # polluting existing vaults with sync output
    if not has_config:
        config.vault_subdir = DEFAULT_SYNC_SUBDIR

    # If no repos from config, auto-discover from github_root
    if not config.repos:
        from obsidian_connector.vault_init import discover_repos
        config.repos = discover_repos(config.github_root)

    return config


def sync_projects(
    vault: str | None = None,
    github_root: str | None = None,
    update_todo: bool = True,
) -> dict[str, Any]:
    """Sync all tracked projects into the vault.

    Generates per-project files, Dashboard, Active Threads, and
    optionally updates the Running TODO list.

    Returns a summary dict suitable for JSON serialization.
    """
    vault_path = resolve_vault_path(vault)
    config = load_sync_config(vault)

    if github_root:
        config.github_root = Path(github_root).expanduser()

    # Determine output root within the vault (with containment check)
    vault_root = vault_path.resolve()
    if config.vault_subdir:
        out_root = (vault_root / config.vault_subdir).resolve()
        try:
            # Ensure out_root is contained within the vault root
            out_root.relative_to(vault_root)
        except ValueError:
            raise ObsidianCLIError(
                f"vault_subdir escapes vault root: {config.vault_subdir}"
            )
    else:
        out_root = vault_root
    projects_dir = out_root / "projects"
    context_dir = out_root / "context"
    sessions_dir = out_root / "sessions"

    projects_dir.mkdir(parents=True, exist_ok=True)
    context_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Extract state for all repos
    states: list[RepoState] = []
    for entry in config.repos:
        state = _extract_repo_state(entry, config.github_root)
        states.append(state)

        # Write per-project file
        project_md = _render_project_file(state)
        (projects_dir / f"{state.dir_name}.md").write_text(
            project_md, encoding="utf-8"
        )

    # Dashboard
    dashboard_md = _render_dashboard(states)
    (out_root / "Dashboard.md").write_text(dashboard_md, encoding="utf-8")

    # Active threads
    threads_md = _render_active_threads(states)
    (context_dir / "active-threads.md").write_text(threads_md, encoding="utf-8")

    # Running TODO
    todo_path = out_root / "Running TODO.md"
    existing_todo = None
    if update_todo and todo_path.is_file():
        try:
            existing_todo = todo_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

    if update_todo:
        todo_md = _render_running_todo(vault_path, existing_todo)
        todo_path.write_text(todo_md, encoding="utf-8")

    # Mark auto-generated files
    try:
        from obsidian_connector.vault_guardian import mark_auto_generated
        mark_auto_generated(vault_path)
    except Exception:
        pass  # Non-critical; don't fail sync over callout injection

    # Timestamp
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    (out_root / ".last-sync").write_text(now, encoding="utf-8")

    # Audit
    log_action(
        "sync-projects",
        {"repos": len(states), "update_todo": update_todo},
        vault,
        affected_path=str(out_root),
    )

    active_count = sum(
        1 for s in states
        if s.is_git and (s.branch not in ("main", "master") or s.uncommitted_count > 0)
    )

    return {
        "synced": len(states),
        "active_threads": active_count,
        "projects_dir": str(projects_dir),
        "dashboard": str(out_root / "Dashboard.md"),
        "timestamp": now,
        "todo_updated": update_todo,
    }


def get_project_status(
    project: str,
    vault: str | None = None,
    github_root: str | None = None,
) -> dict[str, Any]:
    """Get current git status for a single project."""
    config = load_sync_config(vault)
    root = Path(github_root).expanduser() if github_root else config.github_root

    # Find matching repo entry
    entry = None
    for r in config.repos:
        if r.dir_name == project or r.display_name == project:
            entry = r
            break

    if entry is None:
        # Create an ad-hoc entry for unregistered repos
        entry = RepoEntry(dir_name=project, display_name=project)

    state = _extract_repo_state(entry, root)

    return {
        "project": state.dir_name,
        "display_name": state.display_name,
        "group": state.group,
        "branch": state.branch,
        "last_commit": state.last_commit_msg,
        "last_commit_date": state.last_commit_date,
        "uncommitted": state.uncommitted_count,
        "staged": state.staged_count,
        "activity": state.activity_label,
        "modified_files": state.modified_files,
        "recent_commits": state.recent_commits,
        "active_branches": state.active_branches,
        "exists": state.exists,
        "is_git": state.is_git,
    }


def get_active_threads(
    vault: str | None = None,
    github_root: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of projects with active work (non-main branch or uncommitted)."""
    config = load_sync_config(vault)
    root = Path(github_root).expanduser() if github_root else config.github_root

    threads = []
    for entry in config.repos:
        state = _extract_repo_state(entry, root)
        if not state.is_git:
            continue
        has_branch = state.branch not in ("main", "master")
        has_uncommitted = state.uncommitted_count > 0
        if not has_branch and not has_uncommitted:
            continue
        threads.append({
            "project": state.dir_name,
            "display_name": state.display_name,
            "group": state.group,
            "branch": state.branch,
            "uncommitted": state.uncommitted_count,
            "last_commit": state.last_commit_msg,
            "modified_files": state.modified_files[:5],
        })

    return threads


def log_session(
    entries: list[SessionEntry],
    session_context: str = "",
    vault: str | None = None,
) -> dict[str, Any]:
    """Write a session log entry to the vault.

    Returns metadata about the written file.
    """
    vault_path = resolve_vault_path(vault)
    config = load_sync_config(vault)

    # Containment check for vault_subdir
    vault_root = vault_path.resolve()
    if config.vault_subdir:
        out_root = (vault_root / config.vault_subdir).resolve()
        try:
            out_root.relative_to(vault_root)
        except ValueError:
            raise ObsidianCLIError(
                f"vault_subdir escapes vault root: {config.vault_subdir}"
            )
    else:
        out_root = vault_root

    sessions_dir = out_root / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Use unique file per session to preserve frontmatter integrity.
    # Each session gets its own file so Obsidian Bases can query
    # per-session tags and project metadata accurately.
    date_slug = datetime.now().strftime("%Y-%m-%d")
    base_name = f"{date_slug}-session"
    session_file = sessions_dir / f"{base_name}.md"

    # Find next available filename if one already exists
    counter = 1
    was_appended = False
    while session_file.is_file():
        counter += 1
        session_file = sessions_dir / f"{base_name}-{counter}.md"
        was_appended = True

    content = render_session_entry(entries, session_context)
    session_file.write_text(content, encoding="utf-8")

    # Audit
    projects = [e.project for e in entries]
    log_action(
        "log-session",
        {"projects": projects, "entries": len(entries)},
        vault,
        affected_path=str(session_file),
        content=content,
    )

    return {
        "session_file": str(session_file),
        "date": date_slug,
        "projects": projects,
        "appended": was_appended,
    }


def get_running_todo(vault: str | None = None) -> dict[str, Any]:
    """Return the current running TODO state."""
    vault_path = resolve_vault_path(vault)
    open_items, done_items = _scan_vault_todos(vault_path)

    by_source: dict[str, list[str]] = {}
    for item in open_items:
        by_source.setdefault(item.source, []).append(item.text)

    return {
        "total_open": len(open_items),
        "total_completed": len(done_items),
        "by_source": by_source,
        "recent_completed": [item.text for item in done_items[:10]],
    }
