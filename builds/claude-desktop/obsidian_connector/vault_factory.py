"""Vault factory for obsidian-connector.

Creates new Obsidian vaults for any topic or idea. Detects where the
user's existing vaults live and creates new ones alongside them.
Optionally seeds the vault with an initial knowledge base by researching
the topic.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from obsidian_connector.audit import log_action
from obsidian_connector.platform import obsidian_app_json_path


# ---------------------------------------------------------------------------
# Vault location detection
# ---------------------------------------------------------------------------

def detect_vault_root() -> Path | None:
    """Find where the user's Obsidian vaults are stored.

    Reads Obsidian's obsidian.json to find registered vaults, then
    determines the common parent directory.
    """
    app_json = obsidian_app_json_path()
    if not app_json.is_file():
        return None

    try:
        with open(app_json) as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    vaults = cfg.get("vaults", {})
    if not vaults:
        return None

    # Collect vault parent directories
    parents: list[Path] = []
    for _vid, vinfo in vaults.items():
        vpath = Path(vinfo.get("path", ""))
        if vpath.is_dir():
            parents.append(vpath.parent)

    if not parents:
        return None

    # If all vaults share the same parent, use it
    # Otherwise, use the most common parent
    from collections import Counter
    parent_counts = Counter(str(p) for p in parents)
    most_common = parent_counts.most_common(1)[0][0]
    return Path(most_common)


def list_existing_vaults() -> list[dict[str, Any]]:
    """List all vaults registered with Obsidian."""
    app_json = obsidian_app_json_path()
    if not app_json.is_file():
        return []

    try:
        with open(app_json) as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    vaults = []
    for vid, vinfo in cfg.get("vaults", {}).items():
        vpath = Path(vinfo.get("path", ""))
        vaults.append({
            "id": vid,
            "name": vpath.name,
            "path": str(vpath),
            "exists": vpath.is_dir(),
        })

    return vaults


# ---------------------------------------------------------------------------
# Vault creation
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert text to a vault-safe directory name."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60]  # reasonable directory name length


def _render_seed_note(title: str, content: str, tags: list[str]) -> str:
    """Render a seed knowledge note."""
    now = datetime.now().strftime("%Y-%m-%d")
    tags_yaml = ", ".join(tags) if tags else "seed"

    return (
        f"---\n"
        f"title: \"{title}\"\n"
        f"created: {now}\n"
        f"tags: [{tags_yaml}]\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{content}\n"
    )


def create_vault(
    name: str,
    description: str = "",
    seed_topics: list[str] | None = None,
    seed_notes: list[dict[str, str]] | None = None,
    vault_root: str = "",
    preset: str = "",
) -> dict[str, Any]:
    """Create a new Obsidian vault for a topic or idea.

    Parameters
    ----------
    name:
        Human-readable vault name (e.g., "Aviation Research")
    description:
        What this vault is for
    seed_topics:
        List of topic strings to create initial research stubs for
    seed_notes:
        Pre-written seed notes as [{title, content, tags?}]
    vault_root:
        Override: parent directory for the vault. If empty, auto-detects
        from existing Obsidian vault locations.

    Returns
    -------
    dict with vault_path, created files, and next steps.
    """
    # Determine where to create the vault
    if vault_root:
        root = Path(vault_root).expanduser()
    else:
        root = detect_vault_root()
        if root is None:
            # Default fallback locations by platform
            import sys
            if sys.platform == "darwin":
                root = Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents"
            else:
                root = Path.home() / "Documents" / "Obsidian"

    # Apply preset if specified
    preset_data = None
    if preset:
        from obsidian_connector.vault_presets import get_preset
        preset_data = get_preset(preset)
        if preset_data and not description:
            description = preset_data.description

    slug = _slugify(name)
    vault_path = root / slug
    vault_path.mkdir(parents=True, exist_ok=True)

    created_files: list[str] = []

    # Create directories -- preset dirs + standard dirs
    standard_dirs = ["Cards", "Inbox", "Research", "daily", "templates"]
    if preset_data:
        standard_dirs = list(set(standard_dirs + preset_data.directories))
    for dirname in standard_dirs:
        (vault_path / dirname).mkdir(parents=True, exist_ok=True)

    # Create the home note
    now = datetime.now().strftime("%Y-%m-%d")
    home = vault_path / "Home.md"
    if not home.exists():
        home_content = (
            f"---\n"
            f"title: \"{name}\"\n"
            f"created: {now}\n"
            f"tags: [home, index]\n"
            f"---\n\n"
            f"# {name}\n\n"
        )

        if description:
            home_content += f"> {description}\n\n"

        home_content += (
            f"## Quick Links\n\n"
            f"- [[Research/|Research Notes]]\n"
            f"- [[Cards/|Knowledge Cards]]\n"
            f"- [[Inbox/|Inbox]]\n\n"
        )

        if seed_topics:
            home_content += "## Topics to Explore\n\n"
            for topic in seed_topics:
                topic_slug = _slugify(topic)
                home_content += f"- [[Research/{topic_slug}|{topic}]]\n"
            home_content += "\n"

        home_content += (
            f"## About This Vault\n\n"
            f"Created: {now}\n"
            f"Purpose: {description or 'Exploration and research'}\n\n"
            f"> This vault was created by obsidian-connector. "
            f"Add notes freely -- the `Research/` folder is for deep dives, "
            f"`Cards/` for reference notes, and `Inbox/` for quick captures.\n"
        )

        home.write_text(home_content, encoding="utf-8")
        created_files.append("Home.md")

    # Create seed topic stubs
    if seed_topics:
        research_dir = vault_path / "Research"
        research_dir.mkdir(exist_ok=True)

        for topic in seed_topics:
            topic_slug = _slugify(topic)
            topic_file = research_dir / f"{topic_slug}.md"
            if not topic_file.exists():
                topic_content = _render_seed_note(
                    title=topic,
                    content=(
                        f"## Overview\n\n"
                        f"> Research this topic and add findings here.\n\n"
                        f"## Key Questions\n\n"
                        f"- [ ] What is the current state of {topic}?\n"
                        f"- [ ] Who are the key players/resources?\n"
                        f"- [ ] What are the open problems?\n"
                        f"- [ ] How does this connect to other interests?\n\n"
                        f"## Notes\n\n"
                        f"(Add research notes, links, and findings below)\n"
                    ),
                    tags=["research", "seed", _slugify(topic)],
                )
                topic_file.write_text(topic_content, encoding="utf-8")
                created_files.append(f"Research/{topic_slug}.md")

    # Write pre-built seed notes
    if seed_notes:
        cards_dir = vault_path / "Cards"
        cards_dir.mkdir(exist_ok=True)

        for note in seed_notes:
            title = note.get("title", "Untitled")
            content = note.get("content", "")
            tags = [t.strip() for t in note.get("tags", "").split(",") if t.strip()]

            note_slug = _slugify(title)
            note_file = cards_dir / f"{note_slug}.md"
            if not note_file.exists():
                note_content = _render_seed_note(
                    title=title,
                    content=content,
                    tags=tags or ["seed"],
                )
                note_file.write_text(note_content, encoding="utf-8")
                created_files.append(f"Cards/{note_slug}.md")

    # Write preset seed notes
    if preset_data:
        for note in preset_data.seed_notes:
            folder = note.get("folder", ".")
            title = note.get("title", "Untitled")
            content = note.get("content", "")
            note_tags = [t.strip() for t in note.get("tags", "").split(",") if t.strip()]

            note_slug = _slugify(title)
            if folder == ".":
                note_file = vault_path / f"{note_slug}.md"
                rel_path = f"{note_slug}.md"
            else:
                target_dir = vault_path / folder
                target_dir.mkdir(parents=True, exist_ok=True)
                note_file = target_dir / f"{note_slug}.md"
                rel_path = f"{folder}/{note_slug}.md"

            if not note_file.exists():
                note_content = _render_seed_note(title=title, content=content, tags=note_tags or ["seed"])
                note_file.write_text(note_content, encoding="utf-8")
                created_files.append(rel_path)

        # Write daily template if provided
        if preset_data.daily_template:
            template_file = vault_path / "templates" / "daily-template.md"
            if not template_file.exists():
                template_file.write_text(preset_data.daily_template, encoding="utf-8")
                created_files.append("templates/daily-template.md")

    # Audit
    log_action(
        "create-vault",
        {"name": name, "slug": slug, "preset": preset,
         "seed_topics": len(seed_topics or []),
         "seed_notes": len(seed_notes or [])},
        None,
        affected_path=str(vault_path),
    )

    return {
        "name": name,
        "slug": slug,
        "vault_path": str(vault_path),
        "created_files": created_files,
        "file_count": len(created_files),
        "next_steps": [
            f"Open in Obsidian: the vault is at {vault_path}",
            "Use obsidian_search to explore seed notes",
            "Add more notes freely in Cards/ and Research/",
            "To discard: just delete the vault folder",
        ],
    }


def discard_vault(
    vault_path: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Remove a vault that's no longer useful.

    Requires explicit confirm=True. Lists contents before deletion
    when confirm=False (dry-run mode).
    """
    vpath = Path(vault_path).expanduser()

    if not vpath.is_dir():
        return {"error": f"Not a directory: {vault_path}", "removed": False}

    # Count contents
    file_count = sum(1 for _ in vpath.rglob("*") if _.is_file())
    dir_count = sum(1 for _ in vpath.rglob("*") if _.is_dir())

    if not confirm:
        return {
            "vault_path": str(vpath),
            "file_count": file_count,
            "dir_count": dir_count,
            "confirm_required": True,
            "message": f"Vault has {file_count} files in {dir_count} folders. "
                       f"Call again with confirm=True to delete.",
        }

    import shutil
    shutil.rmtree(vpath)

    log_action(
        "discard-vault",
        {"vault_path": str(vpath), "file_count": file_count},
        None,
        affected_path=str(vpath),
    )

    return {
        "vault_path": str(vpath),
        "removed": True,
        "files_removed": file_count,
    }
