"""Project entity derived from repo groups in the sync registry.

Provides a stable, group-aware abstraction over raw RepoEntry records:
- Each distinct non-"standalone" group collapses to one Project.
- Each standalone repo becomes its own single-repo Project.

Pure module -- no clock, no network, no writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from obsidian_connector.project_sync import (
    RepoEntry,
    group_display,
    load_sync_config,
)
from obsidian_connector.draft_manager import _parse_frontmatter


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Project:
    """A logical project derived from one or more RepoEntry records."""

    slug: str
    name: str
    group: str
    repos: tuple[str, ...]
    status: str
    tags: tuple[str, ...]


# ---------------------------------------------------------------------------
# Status rollup
# ---------------------------------------------------------------------------

_STATUS_RANK = {"active": 2, "paused": 1, "dormant": 0, "archived": -1}


def _rollup_status(statuses: list[str]) -> str:
    """Return the highest-priority status from a list.

    Priority: active > paused > dormant > archived.
    """
    best = "archived"
    best_rank = _STATUS_RANK.get("archived", -1)
    for s in statuses:
        rank = _STATUS_RANK.get(s, 0)
        if rank > best_rank:
            best = s
            best_rank = rank
    return best


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_projects(vault: "str | None" = None) -> list[Project]:
    """Derive a sorted list of Projects from the sync registry.

    Groups:
    - Non-"standalone" groups: one Project per distinct group slug.
    - "standalone" repos: each becomes its own single-repo Project.
    """
    config = load_sync_config(vault)
    repos = config.repos

    # Separate grouped from standalone
    grouped: dict[str, list[RepoEntry]] = {}
    standalone: list[RepoEntry] = []

    for repo in repos:
        if repo.group == "standalone":
            standalone.append(repo)
        else:
            grouped.setdefault(repo.group, []).append(repo)

    projects: list[Project] = []

    # One Project per non-standalone group
    for group_slug, entries in grouped.items():
        repo_dirs = tuple(e.dir_name for e in entries)
        statuses = [e.status for e in entries]
        merged_tags: set[str] = set()
        for e in entries:
            merged_tags.update(e.tags)

        projects.append(Project(
            slug=group_slug,
            name=config.group_display_names.get(group_slug) or group_display(group_slug),
            group=group_slug,
            repos=repo_dirs,
            status=_rollup_status(statuses),
            tags=tuple(sorted(merged_tags)),
        ))

    # One Project per standalone repo
    for entry in standalone:
        projects.append(Project(
            slug=entry.dir_name,
            name=entry.display_name,
            group="standalone",
            repos=(entry.dir_name,),
            status=entry.status,
            tags=tuple(sorted(entry.tags)),
        ))

    return sorted(projects, key=lambda p: p.name.lower())


def get_project(
    vault: "str | None",
    name_or_slug: str,
) -> Optional[Project]:
    """Return the Project matching *name_or_slug* (case-insensitive) or None."""
    needle = name_or_slug.lower()
    for project in list_projects(vault):
        if project.slug.lower() == needle or project.name.lower() == needle:
            return project
    return None


def project_repo_entries(
    vault: "str | None",
    project: Project,
) -> list[RepoEntry]:
    """Return the RepoEntry records belonging to *project*."""
    config = load_sync_config(vault)
    repo_set = set(project.repos)
    return [r for r in config.repos if r.dir_name in repo_set]


# Prose keys read from One-Pager frontmatter
_ONE_PAGER_PROSE_KEYS = frozenset({"goal", "intent", "target_users", "architecture", "why"})


def read_one_pager_prose(
    vault: "str | None",
    project: Project,
) -> dict:
    """Parse frontmatter prose fields from Projects/{project.name}/Project One-Pager.md.

    Returns a dict containing only the keys present among:
    ``goal``, ``intent``, ``target_users``, ``architecture``, ``why``.

    Returns ``{}`` when the file is absent or has no matching frontmatter keys.
    """
    from obsidian_connector.config import resolve_vault_path
    from obsidian_connector.errors import VaultNotFound

    try:
        vault_path = resolve_vault_path(vault)
    except VaultNotFound:
        return {}

    one_pager = vault_path / "Projects" / project.name / "Project One-Pager.md"
    if not one_pager.is_file():
        return {}

    try:
        content = one_pager.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    parsed = _parse_frontmatter(content)
    return {k: v for k, v in parsed.items() if k in _ONE_PAGER_PROSE_KEYS}
