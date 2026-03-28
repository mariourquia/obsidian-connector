"""Vault guardian for obsidian-connector.

Protects auto-generated files from manual edits, detects unorganized
user-created notes, and suggests or executes placement into the vault's
folder structure.

Design principle: the vault is a canvas for humans to think freely.
The guardian organizes without restricting -- it never deletes or
overwrites user content.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from obsidian_connector.audit import log_action
from obsidian_connector.config import resolve_vault_path

# ---------------------------------------------------------------------------
# Auto-generated file registry
# ---------------------------------------------------------------------------

# Files that get OVERWRITTEN on every sync (user edits will be lost)
OVERWRITTEN_FILES = {
    "Dashboard.md",
    "Running TODO.md",
    "context/active-threads.md",
    ".last-sync",
}

# Patterns for files that get overwritten (project files)
OVERWRITTEN_PATTERNS = [
    "projects/*.md",  # per-repo state files
]

# Files that get APPENDED to (user content at the top is preserved)
APPEND_SAFE_FILES = {
    "sessions/*.md",  # session logs (new sessions = new files)
}

# Directories where auto-generated content lives
AUTO_DIRS = {"projects", "context"}

# Directories where user content is expected
USER_DIRS = {
    "daily", "Daily Notes", "Journal",  # daily notes
    "Cards",                             # knowledge cards
    "Inbox", "Inbox/Ideas", "Inbox/Agent Drafts", "Inbox/Project Ideas",
    "groups",                            # group MOCs (semi-auto)
    "sessions",                          # session logs
    "templates",                         # user templates
}

# The callout to inject into auto-generated files
_AUTO_GENERATED_CALLOUT = (
    "> [!caution] Auto-generated file\n"
    "> This file is overwritten on every sync. Do not edit manually.\n"
    "> To add persistent notes about this project, create a file in `Cards/` instead.\n"
)


# ---------------------------------------------------------------------------
# File protection
# ---------------------------------------------------------------------------

def mark_auto_generated(vault_path: Path) -> dict[str, Any]:
    """Add auto-generated callouts to files that get overwritten.

    Scans OVERWRITTEN_FILES and OVERWRITTEN_PATTERNS for files that
    don't already have the callout, and injects it after the frontmatter.
    """
    marked = []

    for rel_path in OVERWRITTEN_FILES:
        full = vault_path / rel_path
        if not full.is_file():
            continue
        if _inject_callout(full):
            marked.append(rel_path)

    # Pattern-based (projects/*.md)
    for pattern in OVERWRITTEN_PATTERNS:
        for full in vault_path.glob(pattern):
            rel = str(full.relative_to(vault_path))
            if _inject_callout(full):
                marked.append(rel)

    return {"marked": marked, "count": len(marked)}


def _inject_callout(file_path: Path) -> bool:
    """Inject the auto-generated callout into a file if not already present.

    Returns True if the callout was injected.
    """
    content = file_path.read_text(encoding="utf-8", errors="replace")

    if "Auto-generated file" in content:
        return False  # already marked

    # Insert after frontmatter (after the second '---')
    parts = content.split("---", 2)
    if len(parts) >= 3:
        # Has frontmatter
        new_content = (
            parts[0] + "---" + parts[1] + "---\n\n"
            + _AUTO_GENERATED_CALLOUT + "\n"
            + parts[2].lstrip("\n")
        )
    else:
        # No frontmatter -- prepend
        new_content = _AUTO_GENERATED_CALLOUT + "\n" + content

    file_path.write_text(new_content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

# Known folder purposes for routing
_FOLDER_PURPOSES: dict[str, str] = {
    "daily": "Daily notes and journal entries",
    "Daily Notes": "Daily notes and journal entries",
    "Journal": "Daily notes and journal entries",
    "Cards": "Knowledge cards, reference notes, permanent notes",
    "Inbox": "Incoming items, quick captures, unsorted notes",
    "Inbox/Ideas": "Ideas routed to specific projects",
    "Inbox/Agent Drafts": "AI-generated drafts pending review",
    "Inbox/Project Ideas": "Inception cards for potential projects",
    "projects": "Auto-generated project state (do not edit)",
    "context": "Auto-generated context files (do not edit)",
    "sessions": "Session logs from AI conversations",
    "groups": "Project group MOCs (Maps of Content)",
    "templates": "Note templates for common formats",
}


def detect_unorganized(vault_path: Path) -> list[dict[str, Any]]:
    """Find notes in the vault root that should be in a subfolder.

    Returns a list of suggestions, each with the file, suggested folder,
    and reasoning.
    """
    suggestions = []

    # Known system files that belong in the root
    root_system_files = {
        "Dashboard.md", "Running TODO.md", "CLAUDE.md",
        ".obsidian", ".last-sync", "sync_config.json",
    }

    for item in vault_path.iterdir():
        if item.name.startswith("."):
            continue
        if item.name in root_system_files:
            continue
        if item.is_dir():
            continue
        if not item.name.endswith(".md"):
            continue

        # This is a .md file in the root that isn't a known system file
        suggestion = _suggest_placement(item)
        if suggestion:
            suggestions.append(suggestion)

    return suggestions


def _suggest_placement(file_path: Path) -> dict[str, Any] | None:
    """Suggest where a root-level file should be placed."""
    name = file_path.stem
    content = ""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        pass

    # Check for daily note pattern (YYYY-MM-DD)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", name):
        return {
            "file": file_path.name,
            "suggested_folder": "daily",
            "reason": "Filename matches daily note pattern (YYYY-MM-DD)",
        }

    # Check frontmatter tags for clues
    tags = _extract_tags(content)
    if "session" in tags:
        return {
            "file": file_path.name,
            "suggested_folder": "sessions",
            "reason": "Has 'session' tag",
        }
    if "project-idea" in tags:
        return {
            "file": file_path.name,
            "suggested_folder": "Inbox/Project Ideas",
            "reason": "Has 'project-idea' tag",
        }
    if "ideas" in tags:
        return {
            "file": file_path.name,
            "suggested_folder": "Inbox/Ideas",
            "reason": "Has 'ideas' tag",
        }
    if "template" in tags:
        return {
            "file": file_path.name,
            "suggested_folder": "templates",
            "reason": "Has 'template' tag",
        }

    # Default: suggest Cards/ for anything else
    return {
        "file": file_path.name,
        "suggested_folder": "Cards",
        "reason": "Unorganized note in vault root -- Cards/ is for general knowledge notes",
    }


def _extract_tags(content: str) -> set[str]:
    """Extract tags from YAML frontmatter."""
    tags: set[str] = set()

    # Match tags in frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        # Inline: tags: [a, b, c]
        inline = re.search(r"tags:\s*\[([^\]]+)\]", fm)
        if inline:
            for t in inline.group(1).split(","):
                tags.add(t.strip().strip('"').strip("'"))
        # Multiline: tags:\n  - a\n  - b
        multi = re.findall(r"^\s+-\s+(.+)$", fm, re.MULTILINE)
        for t in multi:
            tags.add(t.strip().strip('"').strip("'"))

    # Inline tags in body (#tag)
    for m in re.finditer(r"(?:^|\s)#([a-zA-Z][a-zA-Z0-9_/-]*)", content):
        tags.add(m.group(1).lower())

    return tags


def organize_file(
    file_name: str,
    target_folder: str,
    vault: str | None = None,
) -> dict[str, Any]:
    """Move a file from the vault root to the target folder.

    Only moves files FROM the vault root. Does not touch files already
    in subfolders (to avoid disrupting user organization).
    """
    vault_path = resolve_vault_path(vault)
    source = vault_path / file_name

    if not source.is_file():
        return {"error": f"File not found: {file_name}", "moved": False}

    # Safety: only move from root
    if source.parent != vault_path:
        return {"error": "Can only organize files from the vault root", "moved": False}

    target_dir = vault_path / target_folder
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / file_name

    # Don't overwrite existing files
    if dest.exists():
        return {
            "error": f"Target already exists: {target_folder}/{file_name}",
            "moved": False,
        }

    source.rename(dest)

    log_action(
        "organize-file",
        {"file": file_name, "from": ".", "to": target_folder},
        vault,
        affected_path=str(dest),
    )

    return {
        "file": file_name,
        "from": ".",
        "to": target_folder,
        "moved": True,
        "new_path": str(dest),
    }
