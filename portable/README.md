# Obsidian Skills (Portable Bundle)

5 Agent Skills-compliant skills for working with Obsidian vaults. Compatible with
any agent that supports the [Agent Skills](https://agentskills.io) specification.

## Included Skills

| Skill | Description | Requires |
|-------|-------------|----------|
| `obsidian-markdown` | Obsidian Flavored Markdown syntax (wikilinks, callouts, embeds, properties) | Nothing |
| `obsidian-bases` | Obsidian Bases (.base files) with views, filters, formulas, summaries | Nothing |
| `json-canvas` | JSON Canvas format (.canvas files) with nodes, edges, groups | Nothing |
| `obsidian-cli` | Obsidian CLI command reference (read, create, search, tasks, plugins) | Obsidian 1.12+ |
| `defuddle` | Extract clean markdown from web pages, removing clutter | Node.js 18+ |

## Install

### Codex CLI

```bash
cp -r portable/skills/* ~/.codex/skills/
```

### OpenCode

```bash
cp -r portable/skills/* ~/.opencode/skills/
# Or: cp -r portable/skills/* ~/.config/opencode/skills/
```

### Gemini CLI

```bash
cp -r portable/skills/* ~/.gemini/skills/
```

### Claude Code (skills only, no MCP)

```bash
# Project-local
cp -r portable/skills/* .claude/skills/

# Global
cp -r portable/skills/* ~/.claude/skills/
```

### Universal (`~/.agents/skills/`)

```bash
cp -r portable/skills/* ~/.agents/skills/
```

This path is scanned natively by Codex CLI and OpenCode. For Claude Code,
add a symlink: `ln -s ~/.agents/skills/* ~/.claude/skills/`

## Full Platform

These 5 skills are a subset of the full obsidian-connector platform.
For the complete experience (62 MCP tools, 13 skills, workflow automation,
project sync, session logging), install the Claude Code plugin:

```bash
claude plugin install obsidian-connector
# Or: claude --plugin-dir /path/to/obsidian-connector
```

See the [main README](../README.md) for all installation options.
