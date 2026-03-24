"""Vault initialization wizard for obsidian-connector.

Interactive setup that walks users through creating or connecting a vault
for project tracking and personal context. Supports both CLI interactive
mode and programmatic mode (for MCP tools).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from obsidian_connector.audit import log_action
from obsidian_connector.project_sync import (
    RepoEntry,
    SyncConfig,
    _SYNC_CONFIG_FILENAME,
    _default_repos,
    _group_display,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_VAULT_NAME = "creation"

_SCAFFOLD_DIRS = [
    "projects",
    "context",
    "sessions",
    "groups",
    "daily",
    "Inbox",
    "Inbox/Agent Drafts",
    "Cards",
]


# ---------------------------------------------------------------------------
# Scaffold generators
# ---------------------------------------------------------------------------

def _render_group_file(group: str, members: list[RepoEntry]) -> str:
    """Render a group MOC (Map of Content) file."""
    display = _group_display(group)
    member_links = "\n".join(f"- [[{m.dir_name}|{m.display_name}]]" for m in members)

    return (
        f"---\n"
        f"title: \"{display}\"\n"
        f"tags: [group, {group}]\n"
        f"---\n\n"
        f"# {display}\n\n"
        f"> Project group overview\n\n"
        f"## Projects\n\n"
        f"{member_links}\n"
    )


def _render_initial_dashboard(repos: list[RepoEntry]) -> str:
    """Render the initial Dashboard.md before first sync."""
    groups: dict[str, list[str]] = {}
    for r in repos:
        groups.setdefault(r.group, []).append(r.dir_name)

    group_lines = []
    for group, members in sorted(groups.items()):
        display = _group_display(group)
        member_links = " + ".join(f"[[{m}]]" for m in members)
        group_lines.append(f"- [[{display}]] -- {member_links}")

    return (
        f"---\n"
        f"title: Creation Dashboard\n"
        f"tags: [dashboard, index]\n"
        f"---\n\n"
        f"# Creation Dashboard\n\n"
        f"> Run `/sync-vault` or `obsx sync-projects` to populate project data.\n\n"
        f"## Quick Links\n\n"
        f"- [[Running TODO]] -- canonical open items across all projects\n"
        f"- [[active-threads|Active Threads]] -- what's in progress\n"
        f"- [[sessions/|Session Logs]] -- conversation context snapshots\n\n"
        f"## Project Groups\n\n"
        + "\n".join(group_lines)
        + "\n"
    )


def _render_initial_todo() -> str:
    """Render an empty Running TODO.md."""
    return (
        f"---\n"
        f"title: Running TODO\n"
        f"tags: [todo, index, running-list]\n"
        f"total_open: 0\n"
        f"---\n\n"
        f"# Running TODO\n\n"
        f"> Canonical list of all open items across the vault.\n"
        f"> Run `/sync-vault` or `obsx sync-projects` to scan for TODO items.\n\n"
        f"> No open TODO items found yet.\n\n"
        f"---\n\n"
        f"## Completed\n\n"
        f"> No completed items tracked yet.\n"
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_repos(github_root: Path) -> list[RepoEntry]:
    """Auto-discover git repos under a directory."""
    repos: list[RepoEntry] = []

    if not github_root.is_dir():
        return repos

    for child in sorted(github_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if not (child / ".git").is_dir():
            continue

        # Detect guidance file
        guidance = "CLAUDE.md"
        for candidate in ("CLAUDE.md", "claude.md", "AGENTS.md", "README.md"):
            if (child / candidate).is_file():
                guidance = candidate
                break

        repos.append(RepoEntry(
            dir_name=child.name,
            display_name=child.name,
            guidance_file=guidance,
            status="active",
            group="standalone",
        ))

    return repos


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_vault(
    vault_path: str | Path,
    github_root: str | Path | None = None,
    repos: list[RepoEntry] | None = None,
    vault_name: str = _DEFAULT_VAULT_NAME,
    use_defaults: bool = False,
) -> dict[str, Any]:
    """Initialize a vault for project sync.

    Creates the directory structure, scaffold files, and sync config.

    Parameters
    ----------
    vault_path:
        Path where the vault should be created or connected.
    github_root:
        Path to the directory containing git repos.
    repos:
        Explicit repo list. If None, uses defaults or auto-discovers.
    vault_name:
        Name for the vault (used in scaffold files).
    use_defaults:
        If True, use the hardcoded default repo list.

    Returns
    -------
    dict with created paths and repo count.
    """
    vault = Path(vault_path).expanduser().resolve()
    vault.mkdir(parents=True, exist_ok=True)

    gh_root = Path(github_root).expanduser() if github_root else Path.home() / "Documents" / "GitHub"

    # Determine repo list
    if repos is not None:
        tracked_repos = repos
    elif use_defaults:
        tracked_repos = _default_repos()
    else:
        tracked_repos = discover_repos(gh_root)

    # Create directories
    created_dirs = []
    for dirname in _SCAFFOLD_DIRS:
        d = vault / dirname
        d.mkdir(parents=True, exist_ok=True)
        created_dirs.append(str(d))

    # Write scaffold files
    created_files = []

    # Dashboard
    dashboard = vault / "Dashboard.md"
    if not dashboard.exists():
        dashboard.write_text(
            _render_initial_dashboard(tracked_repos), encoding="utf-8"
        )
        created_files.append(str(dashboard))

    # Running TODO
    todo = vault / "Running TODO.md"
    if not todo.exists():
        todo.write_text(_render_initial_todo(), encoding="utf-8")
        created_files.append(str(todo))

    # Active threads stub
    threads = vault / "context" / "active-threads.md"
    if not threads.exists():
        threads.write_text(
            "---\ntitle: Active Threads\ntags: [context, threads]\n---\n\n"
            "# Active Threads\n\n> Run sync to populate.\n",
            encoding="utf-8",
        )
        created_files.append(str(threads))

    # Group files
    groups: dict[str, list[RepoEntry]] = {}
    for r in tracked_repos:
        groups.setdefault(r.group, []).append(r)

    for group, members in groups.items():
        group_file = vault / "groups" / f"{_group_display(group)}.md"
        if not group_file.exists():
            group_file.write_text(
                _render_group_file(group, members), encoding="utf-8"
            )
            created_files.append(str(group_file))

    # Sync config
    config_file = vault / _SYNC_CONFIG_FILENAME
    config_data = {
        "github_root": str(gh_root),
        "vault_subdir": "",
        "repos": [
            {
                "dir_name": r.dir_name,
                "display_name": r.display_name,
                "guidance_file": r.guidance_file,
                "status": r.status,
                "group": r.group,
                "tags": r.tags,
            }
            for r in tracked_repos
        ],
    }
    config_file.write_text(
        json.dumps(config_data, indent=2), encoding="utf-8"
    )
    created_files.append(str(config_file))

    # Audit
    log_action(
        "init-vault",
        {"vault_path": str(vault), "repos": len(tracked_repos)},
        None,
        affected_path=str(vault),
    )

    return {
        "vault_path": str(vault),
        "repos_tracked": len(tracked_repos),
        "dirs_created": created_dirs,
        "files_created": created_files,
        "config_file": str(config_file),
        "next_step": "Run `obsx sync-projects` or use the `/sync-vault` skill to populate project data.",
    }


def interactive_init(
    default_vault_path: str | None = None,
    default_github_root: str | None = None,
) -> dict[str, Any]:
    """Run the interactive vault initialization wizard.

    Prompts the user for vault location, GitHub root, and repo selection.
    Returns the result of init_vault().

    Note: This function uses input() and is intended for CLI use only.
    MCP tools should use init_vault() directly with explicit parameters.
    """
    print("\n  Obsidian Connector -- Vault Setup Wizard")
    print("  " + "=" * 42)
    print()

    # 1. Vault path
    suggested_vault = default_vault_path or str(
        Path.home() / "Library" / "Mobile Documents"
        / "iCloud~md~obsidian" / "Documents" / _DEFAULT_VAULT_NAME
        / _DEFAULT_VAULT_NAME
    )
    vault_input = input(f"  Vault path [{suggested_vault}]: ").strip()
    vault_path = vault_input if vault_input else suggested_vault

    # 2. GitHub root
    suggested_gh = default_github_root or str(Path.home() / "Documents" / "GitHub")
    gh_input = input(f"  GitHub projects root [{suggested_gh}]: ").strip()
    github_root = gh_input if gh_input else suggested_gh

    # 3. Repo selection
    gh_path = Path(github_root).expanduser()
    discovered = discover_repos(gh_path)
    defaults = _default_repos()

    print()
    if discovered:
        print(f"  Found {len(discovered)} git repos in {github_root}:")
        for r in discovered:
            print(f"    - {r.dir_name}")
        print()

        use_discovered = input("  Track all discovered repos? [Y/n]: ").strip().lower()
        if use_discovered in ("n", "no"):
            use_default = input("  Use built-in default list instead? [y/N]: ").strip().lower()
            repos = defaults if use_default in ("y", "yes") else discovered
        else:
            repos = discovered
    else:
        print(f"  No git repos found in {github_root}.")
        use_default = input("  Use built-in default list? [Y/n]: ").strip().lower()
        repos = defaults if use_default not in ("n", "no") else []

    print()
    print(f"  Creating vault at: {vault_path}")
    print(f"  Tracking {len(repos)} repos from: {github_root}")
    print()

    confirm = input("  Proceed? [Y/n]: ").strip().lower()
    if confirm in ("n", "no"):
        print("  Cancelled.")
        return {"cancelled": True}

    result = init_vault(
        vault_path=vault_path,
        github_root=github_root,
        repos=repos,
    )

    print()
    print(f"  Vault initialized at: {result['vault_path']}")
    print(f"  Tracking {result['repos_tracked']} repos")
    print(f"  Created {len(result['files_created'])} files")
    print()
    print(f"  Next: run `obsx sync-projects` to populate project data.")
    print()

    return result
