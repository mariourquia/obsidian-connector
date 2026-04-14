---
title: "Installation Guide"
status: verified
owner: core
last_reviewed: "2026-04-13"
---

# Installation Guide

Install obsidian-connector on any AI agent surface. Each platform has a dedicated distribution target.

## Python package variants

- `pip install obsidian-connector` installs the core CLI, Python API, and MCP server dependencies.
- `pip install 'obsidian-connector[tui]'` adds the optional Textual dashboard used by `obsx menu` and `obsx setup-wizard`.
- The first-party installers and `scripts/setup.sh` install the dashboard dependency automatically.

## Claude Code (CLI, Desktop Code tab, IDEs)

Full plugin with 17 skills, 62 MCP tools, hooks, and CLI.

**Marketplace (recommended):**
```bash
claude plugin marketplace add mariourquia/obsidian-connector
claude plugin install obsidian-connector@obsidian-connector
```

**From release asset:**
```bash
# Download claude-code.zip from the latest release
unzip obsidian-connector-claude-code-*.zip -d obsidian-connector
claude plugin add ./obsidian-connector
```

**From source:**
```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[tui]'
claude plugin add .
```

## Claude Desktop (Chat tab)

MCP server providing 62 tools in the Chat tab. No skills (use the Code tab for skills).

**macOS installer (recommended):**

Download `obsidian-connector-*.dmg` from the [latest release](https://github.com/mariourquia/obsidian-connector/releases/latest). Double-click to install. The installer registers the MCP server automatically.

**Windows installer:**

Download `obsidian-connector-*-setup.exe` from the [latest release](https://github.com/mariourquia/obsidian-connector/releases/latest). Run the wizard. Update Claude Code first: `npm i -g @anthropic-ai/claude-code@latest`

**Manual MCP config:**

Add to `claude_desktop_config.json` ([location](https://code.claude.com/docs/en/mcp)):

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "/path/to/venv/bin/python3",
      "args": ["-m", "obsidian_connector.mcp_server"]
    }
  }
}
```

Restart Claude Desktop after editing.

If you only install the base Python package, `obsx menu` and `obsx setup-wizard`
print install guidance for the optional `tui` extra instead of showing a traceback.

## Claude Desktop (Cowork tab)

Skills and portable hooks for the Cowork autonomous agent.

Download `obsidian-connector-cowork-*.zip` from the [latest release](https://github.com/mariourquia/obsidian-connector/releases/latest), then upload via **Customize > Browse plugins** in the Cowork tab.

## Codex CLI (OpenAI)

```bash
# Download portable.zip from the latest release
unzip obsidian-connector-portable-*.zip -d /tmp/obsx-skills

# Project-level (recommended)
cp -r /tmp/obsx-skills/skills/ .agents/skills/

# User-level (all projects)
cp -r /tmp/obsx-skills/skills/ ~/.codex/skills/
```

Skills are detected automatically. Run `/skills` to verify.

## Gemini CLI (Google)

```bash
# Download portable.zip from the latest release
unzip obsidian-connector-portable-*.zip -d /tmp/obsx-skills

# Workspace-level (recommended)
cp -r /tmp/obsx-skills/skills/ .gemini/skills/

# User-level (all projects)
cp -r /tmp/obsx-skills/skills/ ~/.gemini/skills/
```

Or install via the `gemini skills install` command if available.

## Grok CLI (xAI)

```bash
# Download portable.zip from the latest release
unzip obsidian-connector-portable-*.zip -d /tmp/obsx-skills

# Project-level
cp -r /tmp/obsx-skills/skills/ .agents/skills/

# User-level
cp -r /tmp/obsx-skills/skills/ ~/.agents/skills/
```

Run `/skills` in the TUI to verify.

## Manus

```bash
# Download portable.zip from the latest release
unzip obsidian-connector-portable-*.zip -d /tmp/obsx-skills

# Copy to Manus skills directory
cp -r /tmp/obsx-skills/skills/* /home/ubuntu/skills/
```

Skills are auto-detected. Type `/SKILL_NAME` to invoke.

## Any other agent

The `portable.zip` contains universal `SKILL.md` files that work with any AI agent that supports the Agent Skills standard. Extract and copy the `skills/` directory to wherever your agent reads skill definitions.

## Verifying installation

After installing on any Claude surface:
- **CLI/Code tab**: Type `/` and look for skill names
- **Chat tab**: Check Settings > Developer > MCP Servers
- **Cowork tab**: Check Customize > Plugins

After installing on non-Claude surfaces:
- Run your agent's skill listing command (e.g., `/skills`)
- Try invoking a skill by name

<details>
<summary>Verify downloads (developers)</summary>

All release assets include SHA-256 checksums (`.sha256` file) and [Sigstore cosign](https://www.sigstore.dev/) signatures (`.sig` + `.cert` files) for supply-chain verification. Most users do not need these.

```bash
cosign verify-blob --certificate obsidian-connector-*.cert \
  --signature obsidian-connector-*.sig \
  --certificate-identity-regexp "github.com/mariourquia" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  obsidian-connector-*.zip
```
</details>
