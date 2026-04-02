---
name: init-vault
description: Initialize an Obsidian vault for project tracking and personal context. Walks through vault creation, repo discovery, and scaffold setup.
---

# Initialize Vault

Set up a new Obsidian vault (or connect an existing one) for project
tracking, session logging, and personal knowledge management.

## Steps

### 1. Ask the user about their setup

Determine:
- **Do they already have an Obsidian vault?** If yes, get the path.
  If no, suggest creating one (default: iCloud Obsidian directory on macOS, or `~/Documents/Obsidian/My Vault` as a cross-platform fallback).
- **Where are their projects?** Default: `~/Documents/GitHub/`
- **Do they want to track all discovered repos or select specific ones?**

### 2. Initialize the vault

Call `obsidian_init_vault` with:
- **vault_path**: the chosen vault location
- **github_root**: the projects directory
- **use_defaults**: true if they want the standard repo list, false for auto-discovery

This creates:
- `projects/` -- per-repo status files (populated on first sync)
- `sessions/` -- conversation session logs
- `context/` -- active threads and work-in-progress tracking
- `groups/` -- MOC (Map of Content) files for project groups
- `daily/` -- daily notes
- `Inbox/` and `Inbox/Agent Drafts/` -- incoming items
- `Cards/` -- knowledge cards
- `Dashboard.md` -- main index
- `Running TODO.md` -- canonical open items list
- `sync_config.json` -- repo registry (editable)

### 3. Run the first sync

Call `obsidian_sync_projects` to populate the vault with current project data.

### 4. Explain what they have

Tell the user:
- The vault is ready and has {N} projects tracked
- They can run `/sync-vault` (or `obsx sync-projects`) to refresh
- The Dashboard shows all projects at a glance
- Running TODO aggregates all open items
- Session logs capture conversation context with structured tags
- They can open the vault in Obsidian to see the graph view

### 5. Suggest next steps

- Open the vault in Obsidian
- If the morning/evening/idea/weekly skills are installed, mention them
  as available workflows
- Edit `sync_config.json` in the vault to customize tracked repos
- Re-run `/sync-vault` any time to refresh project data

## When to use

- First time using obsidian-connector
- When the user says "set up a vault", "create a vault", "init", "get started"
- When `obsidian_doctor` reports no vault found
