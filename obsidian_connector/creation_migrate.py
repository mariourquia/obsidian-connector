"""Reversible migration of flat per-repo hub notes into Projects/{Project}/Repos/{slug}.md.

Moves the flat ``projects/{dir_name}.md`` notes written by ``project_sync``
into the hierarchical Projects tree introduced by the Creation Dashboard.

Public API
----------
- ``plan_migration(vault) -> list[dict]``   -- pure, no writes
- ``migrate(vault, *, now_iso, dry_run=True) -> dict``
- ``undo_migration(vault, *, dry_run=True) -> dict``
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from obsidian_connector.config import resolve_vault_path
from obsidian_connector.project_sync import group_display, load_sync_config
from obsidian_connector.write_manager import atomic_write

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIGRATION_MAP_REL = "Projects/_migration-map.md"

# fence markers for the machine-readable migration map block
_MAP_FENCE_BEGIN = "<!-- service:migration-map:begin -->"
_MAP_FENCE_END = "<!-- service:migration-map:end -->"

# fence markers for preserved hand-written repo-status content
_REPO_FENCE_BEGIN = "<!-- service:repo-status:begin -->"
_REPO_FENCE_END = "<!-- service:repo-status:end -->"

# Scaffold note names per-project
_SCAFFOLD_NAMES = ("Project One-Pager.md", "Project Dashboard.md", "Backlog.md")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _vault_path(vault: str | None) -> Path:
    return resolve_vault_path(vault)


def _project_name_for_repo(dir_name: str, group: str, display_name: str) -> str:
    """Return the Projects/ folder name for this repo.

    Non-standalone groups map to group_display(group); standalone repos use
    their display_name.
    """
    if group == "standalone":
        return display_name
    return group_display(group)


def _flat_note_path(vault_path: Path, dir_name: str) -> Path | None:
    """Return path of the existing flat note for *dir_name*, or None."""
    # Primary: projects/{dir_name}.md
    primary = vault_path / "projects" / f"{dir_name}.md"
    if primary.is_file():
        return primary
    # Defensive fallback: projects/{dir_name}/index.md
    fallback = vault_path / "projects" / dir_name / "index.md"
    if fallback.is_file():
        return fallback
    return None


def _extract_body(content: str) -> str:
    """Return the hand-written body of a note (everything after the frontmatter fence).

    If the note has no frontmatter, the entire content is the body.
    """
    m = re.match(r"^---\s*\n.*?\n---\s*\n?", content, re.DOTALL)
    if m:
        return content[m.end():]
    return content


def _extract_map_entries(map_content: str) -> list[dict]:
    """Parse the JSON array inside the service:migration-map fence."""
    b = map_content.find(_MAP_FENCE_BEGIN)
    e = map_content.find(_MAP_FENCE_END)
    if b == -1 or e == -1 or e < b:
        return []
    raw = map_content[b + len(_MAP_FENCE_BEGIN):e].strip()
    try:
        entries = json.loads(raw)
        if isinstance(entries, list):
            return entries
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _render_repo_view_note(dir_name: str, project_name: str, body: str) -> str:
    """Render a new repo-view note carrying over the old hand-written body."""
    lines = [
        "---",
        f"dir: {dir_name}",
        f"project: {project_name}",
        "type: repo-view",
        "---",
        "",
        f"# {dir_name}",
        "",
        _REPO_FENCE_BEGIN,
        body.strip("\n"),
        _REPO_FENCE_END,
        "",
    ]
    return "\n".join(lines)


def _render_scaffold_note(title: str, project_name: str) -> str:
    """Render a minimal scaffold note with a service: fence for prose."""
    slug = title.replace(".md", "").lower().replace(" ", "-")
    fence_begin = f"<!-- service:{slug}:begin -->"
    fence_end = f"<!-- service:{slug}:end -->"
    lines = [
        "---",
        f"title: {title.replace('.md', '')}",
        f"project: {project_name}",
        "---",
        "",
        f"# {title.replace('.md', '')}",
        "",
        fence_begin,
        "",
        fence_end,
        "",
    ]
    return "\n".join(lines)


def _render_migration_map(entries: list[dict], now_iso: str) -> str:
    """Render the Projects/_migration-map.md note."""
    json_block = json.dumps(entries, indent=2)
    lines = [
        "---",
        "title: Migration Map",
        f"generated_at: {now_iso}",
        "type: migration-map",
        "---",
        "",
        "# Migration Map",
        "",
        "> Records every flat note path migrated to the Projects/ tree.",
        "> Use `undo_migration` to reverse.",
        "",
        _MAP_FENCE_BEGIN,
        json_block,
        _MAP_FENCE_END,
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_migration(vault: str | None = None) -> list[dict]:
    """Return a migration plan (pure -- no writes).

    Each entry is a dict with keys:
    - ``action``: ``"move"`` or ``"scaffold"``
    - ``old_path``: vault-relative source path (move entries only)
    - ``new_path``: vault-relative destination path
    - ``project_name``: display name of the target Projects/ folder
    - ``dir_name``: repo dir_name (move entries only)

    For ``action="scaffold"`` entries the ``old_path`` key is absent.
    """
    vault_path = _vault_path(vault)
    config = load_sync_config(vault)

    plan: list[dict] = []
    seen_projects: set[str] = set()
    seen_repo_paths: set[str] = set()

    for repo in config.repos:
        flat_note = _flat_note_path(vault_path, repo.dir_name)
        project_name = _project_name_for_repo(
            repo.dir_name, repo.group, repo.display_name
        )
        new_repo_path = f"Projects/{project_name}/Repos/{repo.dir_name}.md"

        if flat_note is not None and new_repo_path not in seen_repo_paths:
            old_rel = str(flat_note.relative_to(vault_path))
            plan.append({
                "action": "move",
                "old_path": old_rel,
                "new_path": new_repo_path,
                "project_name": project_name,
                "dir_name": repo.dir_name,
            })
            seen_repo_paths.add(new_repo_path)

        if project_name not in seen_projects:
            seen_projects.add(project_name)
            # Scaffold notes for this project
            for scaffold_name in _SCAFFOLD_NAMES:
                scaffold_path = f"Projects/{project_name}/{scaffold_name}"
                plan.append({
                    "action": "scaffold",
                    "new_path": scaffold_path,
                    "project_name": project_name,
                })

    return plan


def migrate(
    vault: str | None = None,
    *,
    now_iso: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Run (or preview) the flat-to-Projects migration.

    When ``dry_run=True`` (the default): computes the plan and returns it
    without writing anything.

    When ``dry_run=False``:
    - Writes each repo-view note to ``Projects/{ProjectName}/Repos/{dir_name}.md``
      carrying over the old note's body inside a ``service:repo-status`` fence.
    - Creates per-project scaffold notes (One-Pager, Dashboard, Backlog) only
      when they do NOT already exist (never overwrites prose).
    - Writes ``Projects/_migration-map.md`` with the full old->new map.
    - Does NOT delete the flat ``projects/{dir_name}.md`` notes.
    - Idempotent: a second run skips already-present notes and does not clobber.

    Returns ``{planned, written, map_path, dry_run}``.
    """
    vault_path = _vault_path(vault)
    plan = plan_migration(vault)

    if dry_run:
        return {
            "planned": len(plan),
            "written": 0,
            "map_path": None,
            "dry_run": True,
        }

    written = 0
    map_entries: list[dict] = []

    for entry in plan:
        action = entry["action"]
        project_name = entry["project_name"]
        new_path = vault_path / entry["new_path"]

        if action == "move":
            old_path = vault_path / entry["old_path"]
            dir_name = entry["dir_name"]

            # Idempotency: skip if destination already exists
            if new_path.is_file():
                continue

            # Read old note and preserve its body
            try:
                old_content = old_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                old_content = ""
            body = _extract_body(old_content)

            note_content = _render_repo_view_note(dir_name, project_name, body)
            atomic_write(
                new_path,
                note_content,
                vault_root=vault_path,
                tool_name="creation_migrate",
            )
            written += 1
            map_entries.append({
                "old_path": entry["old_path"],
                "new_path": entry["new_path"],
                "dir_name": dir_name,
            })

        elif action == "scaffold":
            # Only create when absent (never overwrite user prose)
            if new_path.is_file():
                continue

            # Extract title from last path segment
            scaffold_name = Path(entry["new_path"]).name
            scaffold_content = _render_scaffold_note(scaffold_name, project_name)
            atomic_write(
                new_path,
                scaffold_content,
                vault_root=vault_path,
                tool_name="creation_migrate",
            )
            written += 1

    # Write the reversible migration map
    map_path = vault_path / _MIGRATION_MAP_REL
    map_content = _render_migration_map(map_entries, now_iso)
    atomic_write(
        map_path,
        map_content,
        vault_root=vault_path,
        tool_name="creation_migrate",
    )

    return {
        "planned": len(plan),
        "written": written,
        "map_path": _MIGRATION_MAP_REL,
        "dry_run": False,
    }


def undo_migration(
    vault: str | None = None,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Reverse the migration by removing notes that this migration created.

    Reads ``Projects/_migration-map.md`` and removes:
    - Each ``new_path`` listed in the map (repo-view notes under Repos/).
    - The scaffold notes: ``Projects/{ProjectName}/{One-Pager,Dashboard,Backlog}.md``
      for every distinct project_name in the map.
    - The map note itself (``Projects/_migration-map.md``).

    Never touches:
    - The original flat ``projects/{dir_name}.md`` notes.
    - Any notes not listed in the map.

    Returns ``{reverted, dry_run}``.
    """
    vault_path = _vault_path(vault)
    map_path = vault_path / _MIGRATION_MAP_REL

    if not map_path.is_file():
        return {"reverted": 0, "dry_run": dry_run}

    map_content = map_path.read_text(encoding="utf-8", errors="replace")
    map_entries = _extract_map_entries(map_content)

    # Collect paths to remove
    to_remove: list[Path] = []

    project_names: set[str] = set()
    for entry in map_entries:
        new_path = vault_path / entry["new_path"]
        to_remove.append(new_path)
        # Infer project name from path: Projects/{ProjectName}/Repos/{slug}.md
        parts = Path(entry["new_path"]).parts
        if len(parts) >= 3 and parts[0] == "Projects":
            project_names.add(parts[1])

    # Scaffold notes for each project
    for project_name in project_names:
        for scaffold_name in _SCAFFOLD_NAMES:
            scaffold_path = vault_path / "Projects" / project_name / scaffold_name
            to_remove.append(scaffold_path)

    # The map note itself
    to_remove.append(map_path)

    if dry_run:
        reverted = sum(1 for p in to_remove if p.is_file())
        return {"reverted": reverted, "dry_run": True}

    reverted = 0
    for path in to_remove:
        if path.is_file():
            try:
                path.unlink()
                reverted += 1
            except OSError:
                pass

    return {"reverted": reverted, "dry_run": False}
