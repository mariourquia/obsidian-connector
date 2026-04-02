# Install Surfaces

## What This Project Is

Obsidian Connector bridges your Obsidian vault and Claude. It works as an **MCP server** (gives Claude tools to read, write, and search your vault) and as a **skill set** (gives Claude structured workflows like morning briefings, evening reflections, and weekly reviews). Everything runs locally -- your vault never leaves your machine.

## Choose Your Install Method

| If you... | Use this | What you get |
|-----------|----------|--------------|
| Use Claude Code (CLI) | `claude plugin install obsidian-connector` | 17 skills + hooks + 62 MCP tools |
| Use Claude Desktop | Add marketplace (paste repo URL) | 62 MCP tools |
| Want a one-click macOS install | Download .dmg from Releases | 62 MCP tools in Claude Desktop |
| Want a one-click Windows install | Download .exe from Releases | 62 MCP tools + plugin registration |
| Use another AI agent (Codex, Gemini) | Download portable zip | 5 knowledge reference skills |
| Are a Python developer | `pip install obsidian-connector` | Python API + 65 CLI commands |

## What Is a Marketplace Repo?

Claude Desktop has an "Add marketplace" feature in **Settings > Extensions**. When you paste a GitHub repo URL, Claude Desktop looks for `.claude-plugin/marketplace.json` inside that repo to discover what it provides. This repo supports that flow -- paste `https://github.com/mariourquia/obsidian-connector` and Claude Desktop registers the MCP server automatically.

## What Are Skills vs MCP Tools?

**MCP tools** (62): Individual operations Claude can call -- search notes, read a note, write a draft, check your calendar, list open tasks, analyze your vault graph, and more. Available in both Claude Desktop and Claude Code.

**Skills** (17): Structured workflows that tell Claude *how* to use the tools. The morning briefing skill reads your daily note, surfaces open loops, checks delegations, and writes a summary. The evening reflection skill reviews what you accomplished and suggests what to carry forward. Skills are a Claude Code feature and are only available there.

## What Are Presets and Workflows?

**Presets** (13): Pre-configured vault structures. Run `obsx init` or `obsx create-vault --preset journaling` to set up your vault for project tracking, research, journaling, creative writing, and more. Each preset creates starter notes, templates, and a directory structure.

**Workflows**: Multi-step routines that combine several tools into a coherent process. Morning briefing, evening reflection, weekly review, idea capture, and project sync. In Claude Code these are triggered via skills (e.g., `/morning`). In Claude Desktop you can ask Claude to run them manually step by step.

## What Appears After Installation

**In Claude Desktop**: 62 MCP tools appear in the tools panel (the hammer icon in the input area). You can ask Claude to search your vault, read notes, create drafts, run check-ins, and more. Claude sees your vault contents only when you explicitly ask it to use a tool.

**In Claude Code**: 17 skills appear as slash commands (`/morning`, `/evening`, `/capture`, `/sync`, etc.). A SessionStart hook automatically suggests workflows based on time of day. A Stop hook syncs your vault when a session ends. All 62 MCP tools are also available.

## How the Installer Works

The macOS (.dmg) and Windows (.exe) installers handle everything:

1. Copy the Python package to your machine
2. Create a Python virtual environment
3. Register the MCP server in Claude Desktop's config (`claude_desktop_config.json`)
4. Register the plugin in Claude Code's plugin system (if Claude Code is installed)
5. You restart Claude Desktop and the tools appear

No terminal, no git, no pip commands required.

## Privacy

Everything runs locally. Your vault stays on your machine. Claude only sees note content when you explicitly ask it to use a tool -- it cannot browse your vault on its own. No data is sent to external servers. The only network call is optional anonymous telemetry on installer failures (no vault content, no personal data, can be disabled).

## How to Verify It Worked

**Claude Desktop:**

1. Restart Claude Desktop
2. Open a new conversation
3. Ask: "Search my Obsidian vault for recent notes"
4. Claude should use the `obsidian_search` tool

**Claude Code:**

1. Start a new session -- the SessionStart hook prints a greeting
2. Run `/morning` or `/evening` to confirm skills load
3. Ask Claude to use any obsidian tool

**CLI:**

```bash
obsx doctor
```

A passing result confirms Obsidian connectivity and vault resolution.

## Uninstall

| Surface | How to remove |
|---------|---------------|
| Claude Code | `claude plugin remove obsidian-connector` |
| Claude Desktop | Remove the `obsidian-connector` entry from `claude_desktop_config.json` |
| pip | `pip uninstall obsidian-connector` |
| Full cleanup | `obsx uninstall` (removes config, cache, audit logs) |

Config file locations:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

## Feedback and Issues

- GitHub Issues: https://github.com/mariourquia/obsidian-connector/issues
- The installer collects anonymous failure reports to improve reliability (no vault content, no personal data)
