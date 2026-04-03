# Install Surfaces

obsidian-connector can be installed several ways. Each method gives you different capabilities depending on which Claude surface you use.

## Quick reference

| Install method | What you get | Best for |
|---|---|---|
| Marketplace install | Full plugin: 17 skills, hooks, 62 MCP tools | Claude Code users (CLI or Desktop Code tab) |
| DMG installer (macOS) | Full plugin + Claude Desktop MCP registration | Non-technical users on macOS |
| EXE installer (Windows) | Full plugin + Claude Desktop MCP registration | Non-technical users on Windows |
| Manual install | Full plugin via `claude --plugin-dir` | Developers |
| MCP-only (Desktop config) | 62 MCP tools only | Chat tab users who don't need skills |

## Install via marketplace (recommended)

This repo is a self-contained marketplace. Add it and install the plugin:

```
/plugin marketplace add mariourquia/obsidian-connector
/plugin install obsidian-connector@obsidian-connector
```

Or from the terminal:
```bash
claude plugin marketplace add mariourquia/obsidian-connector
claude plugin install obsidian-connector@obsidian-connector
```

This gives you the full experience: 17 skills (e.g., /capture, /ritual, /sync), hooks, and 62 MCP tools.

## Install via DMG or EXE

Download from the [latest release](https://github.com/mariourquia/obsidian-connector/releases/latest).

The installer:
1. Copies the plugin to your system
2. Registers it with the Claude Code plugin system (skills + hooks + MCP)
3. Registers the MCP server with Claude Desktop (for the Chat tab)
4. Creates a Python virtual environment for the MCP server

After install, restart Claude Desktop.

## What appears in Claude Desktop

### Code tab
Full experience: all 17 skills available via `/`, hooks fire on session events, 62 MCP tools available.

### Chat tab
62 MCP tools only (the MCP server registered in `claude_desktop_config.json`). No skills, no hooks.

### Cowork tab
If you install the marketplace plugin, the MCP tools are available. Skills/hooks are not supported in Cowork.

## Glossary

| Term | What it means here |
|---|---|
| **Plugin** | The full obsidian-connector package: skills, hooks, MCP tools, CLI |
| **Marketplace** | This GitHub repo serves as its own marketplace for plugin discovery |
| **MCP server** | The Python process that provides 62 tools to Claude Desktop/Code |
| **Skills** | Claude Code slash commands (e.g., /capture, /ritual, /sync) |
| **Hooks** | Automatic behaviors on session start/stop |
| **Connector** | Cowork term for MCP-like integrations -- not directly applicable here |

## Troubleshooting

### Skills not appearing
- Make sure you installed via marketplace or DMG/EXE, not just MCP config
- Open the **Code tab** in Claude Desktop (not Chat or Cowork)
- Run `/plugin` to verify the plugin is enabled

### MCP tools not appearing in Chat tab
- Check `~/Library/Application Support/Claude/claude_desktop_config.json` has an `obsidian-connector` entry
- Restart Claude Desktop completely (Cmd+Q, reopen)
- Run `obsx doctor` to check connectivity

### Nothing works
- Run `/plugin marketplace update` then `/plugin install obsidian-connector@obsidian-connector`
- If using the DMG installer, try running `Install.command` again
