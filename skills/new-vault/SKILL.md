---
name: new-vault
description: Create a new Obsidian vault. Modes -- project (for a git project), topic (research a topic with web seeding), preset (from a vault template), existing (connect to an existing vault).
---

# /new-vault -- Create a New Vault

You help users create and initialize Obsidian vaults.

## Modes

### Project
Create a vault for tracking git projects.
1. Ask for the vault path (or suggest a default alongside existing vaults)
2. Ask for the GitHub root directory to scan for repos
3. Call `obsidian_init_vault` with the paths
4. Confirm with vault path and number of repos discovered

### Topic
Create a vault seeded with research on a topic. This is the `/explore` behavior.
1. Ask for the topic
2. Call `obsidian_create_vault` to create alongside existing vaults
3. Call `obsidian_seed_vault` with web research on the topic
4. Confirm with vault path and number of seed notes

### Preset
Create a vault from a preset template.
1. Show available presets via `obsidian_vault_presets`
2. Let user choose (or suggest based on their description)
3. Call `obsidian_create_vault` with the preset
4. Confirm with vault path and preset used

### Existing
Connect to an existing Obsidian vault for project tracking.
1. Ask for the vault path
2. Call `obsidian_init_vault` with existing_vault detection
3. Confirm that project tracking is set up in the vault's Project Tracking/ subdirectory

## Default behavior (no mode specified)
Ask: "What kind of vault? (project / topic / preset / existing)"
