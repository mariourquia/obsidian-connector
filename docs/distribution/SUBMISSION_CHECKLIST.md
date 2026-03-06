---
title: "Submission Checklist"
status: draft
owner: "mariourquia"
last_reviewed: "2026-03-06"
---

# Submission Checklist

Pre-submission checklists for both distribution paths.
See [MARKETPLACE_STRATEGY.md](./MARKETPLACE_STRATEGY.md) for context on each path.

## Anthropic MCP Connectors Directory (Local Server)

Based on the [Local MCP Server Submission Guide](https://support.claude.com/en/articles/12922832-local-mcp-server-submission-guide).

### Required artifacts

- [x] README with clear setup instructions
- [x] Privacy policy (PRIVACY.md at repo root)
- [x] Privacy policy section in README.md
- [ ] Privacy policy HTTPS URL in manifest (`privacy_policies` array, manifest v0.3+)
- [x] Tool annotations on all MCP tools (readOnlyHint, destructiveHint, title)
- [x] Structured error handling (typed exception hierarchy)
- [x] Health check tool (doctor)
- [x] 3+ documentation examples (README has 10+)
- [ ] Screenshots of tools in Claude Desktop (minimum: search, daily log, doctor, today)
- [ ] Published package (npm or pip) -- or git clone instructions
- [x] MIT license declared in pyproject.toml
- [ ] LICENSE file at repo root
- [ ] Icon (512x512 PNG, recommended)
- [x] mcpb.json manifest
- [x] Category tags (productivity, notes, knowledge-management)
- [x] Version number (0.2.0 in mcpb.json)

### Testing

- [x] Works on macOS
- [ ] Works on Linux
- [ ] Works on Windows
- [ ] Works without development tools installed (clean-environment test)
- [ ] Dependencies bundled and current
- [x] Error messages are helpful (typed error hierarchy)
- [x] Graceful failure when Obsidian is not running (ObsidianNotRunning error)

### Submission

- [ ] MCPB CLI available (`mcpb pack` to package)
- [ ] Package validated (`mcpb info`)
- [ ] Submission form completed ([Google Form](https://forms.gle/tyiAZvch1kDADKoP9))
- [ ] Server details, docs links, examples, contact info provided

### Top rejection reasons to avoid

1. Missing tool annotations -- DONE, all 16 tools annotated
2. Portability issues -- TODO, macOS only currently
3. Missing privacy policy -- DONE in README and PRIVACY.md; TODO HTTPS URL in manifest
4. Incomplete documentation -- DONE, 10+ examples

## Claude Code Plugin Marketplace

Based on [Claude Code Plugin Docs](https://code.claude.com/docs/en/plugins) and
[Plugins Reference](https://code.claude.com/docs/en/plugins-reference).

### Self-hosted marketplace (Phase 1)

- [ ] `.claude-plugin/plugin.json` manifest at repo root
- [ ] `.mcp.json` with MCP server configuration at repo root
- [ ] `.claude-plugin/marketplace.json` catalog
- [ ] Test with `claude --plugin-dir .`
- [ ] Validate with `claude plugin validate .`
- [ ] README documents plugin installation (`/plugin marketplace add`)
- [ ] Test install from marketplace (`/plugin install obsidian-connector@...`)

### Official directory submission (Phase 2)

- [ ] All Phase 1 items complete
- [ ] Skills definitions (optional but recommended)
  - [ ] `/obsidian-connector:search` skill
  - [ ] `/obsidian-connector:today` skill
  - [ ] `/obsidian-connector:log` skill
- [ ] Slash commands (optional)
- [ ] Testing with Claude Code plugin loader
- [ ] README for plugin-specific setup
- [ ] Submit via [clau.de/plugin-directory-submission](https://clau.de/plugin-directory-submission)
  or [claude.ai/settings/plugins/submit](https://claude.ai/settings/plugins/submit)

### Plugin manifest requirements

| Field         | Value                              | Status |
|---------------|------------------------------------|--------|
| `name`        | `obsidian-connector`               | Ready  |
| `version`     | `0.2.0`                           | Ready  |
| `description` | Access your Obsidian vault...      | Ready  |
| `author`      | Mario Urquia                       | Ready  |
| `repository`  | GitHub URL                         | Ready  |
| `license`     | MIT                                | Ready  |
| `keywords`    | obsidian, notes, productivity, mcp | Ready  |
| `mcpServers`  | .mcp.json config                   | TODO   |

## Action items (priority order)

1. **Create plugin.json and .mcp.json** -- enables self-hosted marketplace immediately
2. **Create LICENSE file** -- needed for both paths
3. **Create icon** -- 512x512 PNG for directory listing
4. **Capture screenshots** -- Claude Desktop showing tools in action
5. **Test cross-platform** -- Linux and Windows
6. **Submit to official plugin directory** -- when Phase 1 is validated
7. **Package with MCPB** -- when CLI is released
