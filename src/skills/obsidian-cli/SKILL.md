---
name: obsidian-cli
description: Interact with Obsidian vaults using the Obsidian CLI. Read, create, search, and manage notes, tasks, tags, and plugins from the command line. Use when the user asks to interact with an Obsidian vault directly via CLI commands.
---

# Obsidian CLI

The Obsidian desktop app (v1.12+) includes a built-in CLI for vault operations.
Run `obsidian help` for the authoritative command list -- the CLI evolves with
each Obsidian release.

## Prerequisites

- Obsidian desktop app v1.12+ installed
- CLI enabled in Obsidian Settings > General > CLI

## Syntax

```
obsidian <command> [vault=<name>] [parameter=<value>] [--flag]
```

- **Parameters** use `key=value` (no dashes)
- **Flags** use `--flag` (double dash, no value)
- **Vault targeting**: `vault=MyVault` or omit to use the default vault

## Core Commands

### Read a note

```bash
obsidian read path="folder/note.md"
obsidian read file="My Note"           # by display name
```

### Create or overwrite a note

```bash
obsidian create path="folder/new.md" content="# Title\n\nBody text"
obsidian create path="note.md" content="overwrite" --overwrite
```

### Append to a note

```bash
obsidian append path="daily/2026-03-25.md" content="\n- New item"
```

### Search the vault

```bash
obsidian search query="quarterly review"
obsidian search query="tag:#project" vault=Work
```

### Daily note

```bash
obsidian daily                          # open or create today's daily note
obsidian daily vault=Personal
```

### Tasks

```bash
obsidian tasks                          # list all tasks
obsidian tasks status=todo              # filter by status
obsidian tasks path="projects/"         # filter by folder
```

### Tags

```bash
obsidian tags                           # list all tags with counts
```

### Backlinks

```bash
obsidian backlinks path="note.md"       # notes that link to this note
```

## Plugin Development

```bash
obsidian reload vault=Dev               # reload plugins after code change
obsidian errors vault=Dev               # show plugin errors
obsidian screenshot vault=Dev           # capture vault screenshot
obsidian dom path="note.md"             # dump DOM tree for a note
obsidian console vault=Dev              # show console output
obsidian eval code="app.vault.getFiles().length"  # run JS in vault context
obsidian css                            # dump resolved CSS variables
obsidian mobile vault=Dev               # toggle mobile emulation
```

## Common Patterns

```bash
# Append to daily note
obsidian append path="$(date +%Y-%m-%d).md" content="\n- Meeting notes: ..."

# Search and read
obsidian search query="factor model" | head -5  # find notes
obsidian read path="research/factor-model.md"   # read the one you want

# Batch operations (use shell loops)
for f in projects/*.md; do
  obsidian read path="$f"
done
```

## Important Notes

- The CLI communicates with the running Obsidian app via IPC. Obsidian must be open.
- File paths are relative to the vault root.
- Content with newlines: use `\n` in the content parameter.
- The CLI is read/write. Mutations (create, append, overwrite) modify vault files.

## When to Use MCP Tools Instead

If the obsidian-connector MCP server is running, prefer MCP tools for:
- **Graph analysis** (neighborhood, backlinks with context, vault structure)
- **Thinking tools** (ghost voice, drift analysis, idea tracing)
- **Workflow operations** (morning briefing, evening close, graduation pipeline)
- **Project sync** (cross-repo state tracking, session logging, running TODO)

The raw CLI is best for simple read/write/search operations and plugin development.
