---
title: "Marketplace Strategy"
status: draft
owner: "mariourquia"
last_reviewed: "2026-03-06"
---

# Marketplace Strategy

Two paths exist for making obsidian-connector publicly discoverable:
the Claude Code plugin marketplace and the Anthropic MCP Connectors Directory.
This document researches both, compares them, and recommends a strategy.

## 1. Claude Code Plugin Marketplace

### What it is

Claude Code (the CLI tool) has a plugin system that lets users extend its
functionality with skills, agents, hooks, MCP servers, and LSP servers.
Plugins are distributed through "marketplaces" -- git repositories containing
a `marketplace.json` catalog. Anthropic also maintains an official curated
directory at [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official).

### How plugins work

A plugin is a directory with this structure:

```
obsidian-connector-plugin/
  .claude-plugin/
    plugin.json           # Required manifest (name, version, description)
  .mcp.json               # MCP server configuration
  skills/                  # Agent Skills with SKILL.md files
  commands/                # Slash commands (markdown files)
  agents/                  # Subagent definitions
  hooks/                   # Event handlers (hooks.json)
  README.md
```

The only required component is `.claude-plugin/plugin.json`. Claude Code
auto-discovers everything else from default locations.

**plugin.json manifest schema** (from [Claude Code docs](https://code.claude.com/docs/en/plugins-reference)):

| Field         | Required | Description                              |
|---------------|----------|------------------------------------------|
| `name`        | Yes      | Unique identifier (kebab-case)           |
| `version`     | No       | Semantic version                         |
| `description` | No       | Brief explanation                        |
| `author`      | No       | `{name, email, url}`                     |
| `homepage`    | No       | Documentation URL                        |
| `repository`  | No       | Source code URL                          |
| `license`     | No       | SPDX license identifier                 |
| `keywords`    | No       | Discovery tags                          |
| `mcpServers`  | No       | MCP server configs (or path to .mcp.json)|
| `commands`    | No       | Custom command paths                    |
| `agents`      | No       | Custom agent paths                      |
| `skills`      | No       | Custom skill paths                      |
| `hooks`       | No       | Hook configuration                      |

Plugins can bundle an MCP server via `.mcp.json` at the plugin root:

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "${CLAUDE_PLUGIN_ROOT}/.venv/bin/python3",
      "args": ["-m", "obsidian_connector.mcp_server"]
    }
  }
}
```

The `${CLAUDE_PLUGIN_ROOT}` variable resolves to the plugin's installation
directory. This is critical because plugins are copied to a cache location
(`~/.claude/plugins/cache`) during installation.

### Distribution paths

**Self-hosted marketplace.** Create a git repository with
`.claude-plugin/marketplace.json` listing the plugin. Users add it with
`/plugin marketplace add owner/repo` and install with
`/plugin install obsidian-connector@marketplace-name`.

**Anthropic official directory.** Submit to
[anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official)
via the submission form at [clau.de/plugin-directory-submission](https://clau.de/plugin-directory-submission).
Anthropic reviews for quality and security before inclusion. Once listed,
users discover and install via `/plugin > Discover`.

**In-app submission.** Anthropic also accepts submissions through:
- [claude.ai/settings/plugins/submit](https://claude.ai/settings/plugins/submit)
- [platform.claude.com/plugins/submit](https://platform.claude.com/plugins/submit)

### What obsidian-connector needs to become a plugin

1. Create `.claude-plugin/plugin.json` manifest
2. Create `.mcp.json` bundling the MCP server
3. Optionally add skills (e.g., `/obsidian:search`, `/obsidian:today`)
4. Optionally add slash commands for common workflows
5. Test with `claude --plugin-dir ./obsidian-connector`
6. Validate with `claude plugin validate .`

### Open questions

- The plugin system copies plugins to cache. obsidian-connector requires a
  Python venv with the `mcp` dependency. It is unclear whether the plugin
  system handles venv creation automatically or whether we need to provide
  an installation hook.
- Plugin categories in the official directory include: development,
  productivity, learning, security. We would target `productivity`.
- The submission review timeline is undefined. Anthropic notes they cannot
  guarantee acceptance or individual responses.

## 2. Anthropic MCP Connectors Directory

### What it is

The Connectors Directory is a curated hub within Claude's UI (web, Desktop,
mobile, Code, and API) where users discover MCP servers that Anthropic has
reviewed. It supports two types of servers:

- **Remote MCP servers** -- hosted services with HTTPS endpoints and OAuth
- **Local MCP servers** -- packaged as `.mcpb` bundles, installed locally

obsidian-connector is a **local MCP server** (runs entirely on the user's
machine, communicates with Obsidian via IPC).

### Submission requirements (local servers)

Based on the [Local MCP Server Submission Guide](https://support.claude.com/en/articles/12922832-local-mcp-server-submission-guide):

| Requirement                | Status      | Notes                                             |
|----------------------------|-------------|---------------------------------------------------|
| Tool annotations           | Done        | All 16 tools have readOnlyHint, destructiveHint   |
| Privacy policy in README   | Done        | Section present in README.md                      |
| Privacy policy in manifest | Partial     | mcpb.json has `privacy_policy` field; needs `privacy_policies` array with HTTPS URL (manifest v0.3+) |
| 3+ documentation examples  | Done        | README has CLI, Python API, and MCP examples      |
| Test credentials           | N/A         | No auth required (local-only operation)           |
| Comprehensive README       | Done        | All required sections present                     |
| LICENSE file                | Missing     | MIT license declared in pyproject.toml but no LICENSE file at repo root |
| Icon (512x512 PNG)         | Missing     | Not yet created                                   |
| Screenshots                | Missing     | Need Claude Desktop screenshots of tools in action|
| Cross-platform testing     | Partial     | macOS only; Linux/Windows support planned         |

### Submission process

1. Complete the pre-submission checklist (see SUBMISSION_CHECKLIST.md)
2. Package the server: `mcpb pack` (MCPB CLI required)
3. Submit via [Google Form](https://forms.gle/tyiAZvch1kDADKoP9) with server details, documentation links, examples, and contact info

### Top rejection reasons (from Anthropic)

1. Missing tool annotations (immediate rejection)
2. Portability issues (1-2 week delay)
3. Missing privacy policy in README or manifest
4. Incomplete documentation (fewer than 3 examples)

### What obsidian-connector already has

- Tool annotations on all 16 MCP tools (readOnlyHint, destructiveHint, title)
- PRIVACY.md with local-only operation policy
- mcpb.json manifest with metadata
- MIT license in pyproject.toml
- Comprehensive README with 10+ examples
- Structured error handling with typed exceptions
- Health check tool (doctor)
- Category tags (productivity, notes, knowledge-management)

### What is still missing

- LICENSE file at repo root
- Icon (512x512 PNG)
- Screenshots of tools in Claude Desktop
- `privacy_policies` array with HTTPS URL in manifest
- Cross-platform testing (Linux, Windows)
- MCPB CLI (not yet publicly available)

### Current status of MCPB

The MCPB CLI is referenced in Anthropic's submission guides (`mcpb pack`,
`mcpb info`) but no public binary, npm package, or PyPI distribution has
been released. The `mcpb.json` manifest at the repo root follows the
expected schema based on available documentation. See
[MCPB_RESEARCH.md](./MCPB_RESEARCH.md) for details.

## 3. Comparison

| Dimension           | Claude Code Plugin Marketplace                         | Anthropic MCP Connectors Directory                    |
|---------------------|--------------------------------------------------------|-------------------------------------------------------|
| **Audience**        | Claude Code CLI users (developers, power users)        | All Claude users (web, Desktop, mobile, Code, API)    |
| **Server type**     | Plugin with bundled MCP server                         | Standalone MCP server (local or remote)               |
| **Distribution**    | Git repository + marketplace.json                      | MCPB package + submission form                        |
| **Discovery**       | `/plugin > Discover` or marketplace add                | Connectors Directory in Claude UI                     |
| **Review process**  | Official: Anthropic review; Self-hosted: none          | Anthropic review (no guaranteed acceptance)            |
| **Self-serve**      | Yes (self-hosted marketplace, immediate)               | No (requires Anthropic review)                        |
| **Extra features**  | Skills, commands, hooks, agents, LSP servers           | MCP tools only                                        |
| **Effort**          | Medium (create plugin structure + manifest)            | Low-medium (already have most artifacts)              |
| **Visibility**      | Claude Code users who add the marketplace              | All Claude users via built-in directory                |
| **Timeline**        | Self-hosted: immediate; Official: review queue         | Blocked on MCPB CLI availability + review queue       |
| **Dependency**      | Python venv handling unclear                           | Blocked on MCPB CLI release                           |

## 4. Recommended Strategy

Pursue both paths. Neither is exclusive, and the artifacts overlap
significantly (README, privacy policy, tool annotations, manifest).

### Phase 1: Self-hosted Claude Code marketplace (now)

**Effort:** Low. **Timeline:** Immediate.

1. Create `.claude-plugin/plugin.json` in the repo
2. Create `.mcp.json` with the MCP server configuration
3. Create `.claude-plugin/marketplace.json` for self-hosted distribution
4. Test with `claude --plugin-dir .`
5. Users can install immediately via `/plugin marketplace add mariourquia/obsidian-connector`

This gives us immediate distribution with zero external dependencies.

### Phase 2: Official Claude Code plugin directory (next)

**Effort:** Low-medium. **Timeline:** Depends on review queue.

1. Submit to [clau.de/plugin-directory-submission](https://clau.de/plugin-directory-submission)
2. Or submit via [claude.ai/settings/plugins/submit](https://claude.ai/settings/plugins/submit)
3. Add optional skills for common workflows (search, today brief)
4. Wait for review and iterate on feedback

### Phase 3: Anthropic MCP Connectors Directory (when MCPB ships)

**Effort:** Medium. **Timeline:** Blocked on MCPB CLI.

1. Create LICENSE file at repo root
2. Create 512x512 PNG icon
3. Capture Claude Desktop screenshots
4. Update manifest with `privacy_policies` HTTPS URL array
5. Test cross-platform (Linux, Windows)
6. Package with `mcpb pack` when CLI is available
7. Submit via Google Form

### Phase 4: npm/PyPI package (optional, parallel)

**Effort:** Medium. **Timeline:** Anytime.

Publish `obsidian-connector` to PyPI so that plugin marketplaces can
reference it as a pip source instead of requiring a git clone. This also
simplifies the Claude Desktop setup to `pip install obsidian-connector`.

## 5. Timeline Summary

| Milestone                           | Dependency        | Target        |
|-------------------------------------|-------------------|---------------|
| Self-hosted marketplace (Phase 1)   | None              | This sprint   |
| Official plugin submission (Phase 2)| Review queue      | After Phase 1 |
| Screenshots and icon                | Claude Desktop    | Before Phase 3|
| LICENSE file at repo root           | None              | Before Phase 3|
| MCPB packaging (Phase 3)           | MCPB CLI release  | When available|
| PyPI publish (Phase 4)             | None              | Anytime       |

## References

- [Claude Code Plugin Docs](https://code.claude.com/docs/en/plugins)
- [Claude Code Plugins Reference](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code Plugin Marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [Anthropic Official Plugin Directory](https://github.com/anthropics/claude-plugins-official)
- [Local MCP Server Submission Guide](https://support.claude.com/en/articles/12922832-local-mcp-server-submission-guide)
- [Remote MCP Server Submission Guide](https://support.claude.com/en/articles/12922490-remote-mcp-server-submission-guide)
- [Anthropic Connectors Directory FAQ](https://support.claude.com/en/articles/11596036-anthropic-connectors-directory-faq)
- [MCP Specification](https://modelcontextprotocol.io)
