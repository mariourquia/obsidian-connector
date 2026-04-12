"""Idea routing and project incubation for obsidian-connector.

Routes ideas to the correct project's idea file based on keyword matching
against the repo registry. Also supports creating inception cards for
projects that don't exist yet -- tangential ideas worth capturing but
not immediately building.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from obsidian_connector.audit import log_action
from obsidian_connector.config import resolve_vault_path
from obsidian_connector.project_sync import (
    GROUP_DISPLAY,
    RepoEntry,
    group_display,
    load_sync_config,
)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _build_keyword_index(repos: list[RepoEntry]) -> dict[str, str]:
    """Build a keyword -> project mapping from the repo registry.

    Each repo contributes its dir_name, display_name words, group, and
    tags as keywords. Returns a dict mapping lowercase keywords to the
    repo's group (for group-level routing) or dir_name (for project-level).
    """
    index: dict[str, str] = {}

    for repo in repos:
        # Direct name match (highest priority)
        index[repo.dir_name.lower()] = repo.dir_name

        # Display name words
        for word in re.split(r"[\s\-_/()]+", repo.display_name.lower()):
            if len(word) > 2:  # skip noise like "OS", "v7"
                index[word] = repo.dir_name

        # Group name
        index[repo.group.lower()] = repo.group

        # Tags
        for tag in repo.tags:
            if tag != "project" and len(tag) > 2:
                index[tag.lower()] = repo.dir_name

    # Add group display names
    for key, display in GROUP_DISPLAY.items():
        index[display.lower()] = key
        index[key.lower()] = key

    return index


def route_idea(idea_text: str, repos: list[RepoEntry]) -> str:
    """Determine which project or group an idea belongs to.

    Returns the project dir_name, group name, or "general" if no match.
    """
    index = _build_keyword_index(repos)
    text_lower = idea_text.lower()

    # Score each candidate by keyword hits
    scores: dict[str, int] = {}
    for keyword, target in index.items():
        if keyword in text_lower:
            scores[target] = scores.get(target, 0) + len(keyword)

    if not scores:
        return "general"

    # Return the highest-scoring target
    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# Idea files
# ---------------------------------------------------------------------------

def _ensure_idea_file(vault_path: Path, target: str) -> Path:
    """Ensure the idea file exists for a target project/group."""
    ideas_dir = vault_path / "Inbox" / "Ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)

    idea_file = ideas_dir / f"{target}.md"
    if not idea_file.exists():
        now = datetime.now().strftime("%Y-%m-%d")
        idea_file.write_text(
            f"---\n"
            f"title: \"Ideas -- {target}\"\n"
            f"created: {now}\n"
            f"tags: [ideas, {target}]\n"
            f"---\n\n"
            f"# Ideas -- {target}\n\n"
            f"> Accumulated ideas routed to this project.\n\n",
            encoding="utf-8",
        )

    return idea_file


def float_idea(
    idea: str,
    project: str = "",
    vault: str | None = None,
) -> dict[str, Any]:
    """Route an idea to the appropriate project's idea file.

    If project is specified, routes directly. Otherwise, uses keyword
    matching against the repo registry to find the best match.
    """
    vault_path = resolve_vault_path(vault)
    config = load_sync_config(vault)

    # Determine target
    if project:
        target = project.lower().strip()
    else:
        target = route_idea(idea, config.repos)

    # Write the idea
    idea_file = _ensure_idea_file(vault_path, target)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    entry = f"- **{now}** -- {idea}\n"
    with open(idea_file, "a", encoding="utf-8") as f:
        f.write(entry)

    log_action(
        "float-idea",
        {"target": target, "idea_length": len(idea)},
        vault,
        affected_path=str(idea_file),
        content=idea,
    )

    return {
        "routed_to": target,
        "file": str(idea_file),
        "idea": idea,
        "auto_routed": not bool(project),
    }


# ---------------------------------------------------------------------------
# Project inception
# ---------------------------------------------------------------------------

def incubate_project(
    name: str,
    description: str,
    why: str = "",
    tags: str = "",
    related_projects: str = "",
    vault: str | None = None,
) -> dict[str, Any]:
    """Create an inception card for a project that doesn't exist yet.

    This captures tangential ideas worth revisiting -- things that might
    become repos or products someday but aren't being built now.
    """
    vault_path = resolve_vault_path(vault)

    inception_dir = vault_path / "Inbox" / "Project Ideas"
    inception_dir.mkdir(parents=True, exist_ok=True)

    # Slugify the name for the filename
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    card_file = inception_dir / f"{slug}.md"

    now = datetime.now().strftime("%Y-%m-%d")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    related = [r.strip() for r in related_projects.split(",") if r.strip()] if related_projects else []

    tags_yaml = ", ".join(["project-idea"] + tag_list)
    related_links = "\n".join(f"- [[{r}]]" for r in related) if related else "- (none yet)"

    content = (
        f"---\n"
        f"title: \"{name}\"\n"
        f"status: idea\n"
        f"created: {now}\n"
        f"tags: [{tags_yaml}]\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"**Status**: idea (not started)\n"
        f"**Created**: {now}\n\n"
        f"## What\n\n"
        f"{description}\n\n"
    )

    if why:
        content += f"## Why\n\n{why}\n\n"

    content += (
        f"## Related Projects\n\n"
        f"{related_links}\n\n"
        f"## Notes\n\n"
        f"> Add thoughts, links, and sketches here as they come up.\n\n"
    )

    # Don't overwrite existing cards -- append a note instead
    if card_file.exists():
        with open(card_file, "a", encoding="utf-8") as f:
            f.write(f"\n---\n\n## Update ({now})\n\n{description}\n")
        created = False
    else:
        card_file.write_text(content, encoding="utf-8")
        created = True

    log_action(
        "incubate-project",
        {"name": name, "slug": slug, "created": created},
        vault,
        affected_path=str(card_file),
    )

    return {
        "name": name,
        "slug": slug,
        "file": str(card_file),
        "created": created,
        "status": "idea",
    }


def list_incubating(vault: str | None = None) -> dict[str, Any]:
    """List all project inception cards."""
    vault_path = resolve_vault_path(vault)
    inception_dir = vault_path / "Inbox" / "Project Ideas"

    if not inception_dir.is_dir():
        return {"projects": [], "count": 0}

    projects = []
    for card in sorted(inception_dir.glob("*.md")):
        content = card.read_text(encoding="utf-8", errors="replace")

        # Extract title from frontmatter
        title = card.stem
        title_match = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1)

        projects.append({
            "name": title,
            "slug": card.stem,
            "file": str(card),
        })

    return {"projects": projects, "count": len(projects)}


def list_idea_files(vault: str | None = None) -> dict[str, Any]:
    """List all idea routing files with item counts."""
    vault_path = resolve_vault_path(vault)
    ideas_dir = vault_path / "Inbox" / "Ideas"

    if not ideas_dir.is_dir():
        return {"files": [], "total_ideas": 0}

    files = []
    total = 0
    for idea_file in sorted(ideas_dir.glob("*.md")):
        content = idea_file.read_text(encoding="utf-8", errors="replace")
        count = content.count("\n- **")
        total += count
        files.append({
            "project": idea_file.stem,
            "file": str(idea_file),
            "idea_count": count,
        })

    return {"files": files, "total_ideas": total}
