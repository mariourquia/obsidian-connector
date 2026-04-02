# Claude Code Plugin Marketplace Submission Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure obsidian-connector into a standards-compliant Claude Code plugin and submit to the official Anthropic marketplace.

**Architecture:** The plugin wraps a Python MCP server (29 tools) with Claude Code skills (4), hooks (SessionStart), and a setup script for Python venv creation. The MCP server requires Python 3.11+ and the Obsidian desktop CLI, so the plugin includes a post-install setup step. Skills are restructured from flat `skills/*.md` to `skills/<name>/SKILL.md` directory format. Hooks move from `.claude/settings.json` to `hooks/hooks.json` using `${CLAUDE_PLUGIN_ROOT}`.

**Tech Stack:** Python 3.11+, FastMCP, Claude Code plugin system, bash

**Current State:** plugin.json and marketplace.json exist but the directory structure has 6 gaps vs. plugin spec (see Gap Analysis below).

---

## Strategy: Why a Plugin

obsidian-connector already ships as a Python package, CLI (`obsx`), MCP server, and macOS DMG. The Claude Code plugin is a **fourth distribution surface** -- not a replacement for the others. The strategic value is:

1. **Discoverability.** The official Anthropic marketplace is where Claude Code users browse for extensions. Being listed there puts obsidian-connector in front of every Claude Code user who searches "obsidian", "notes", "productivity", or "knowledge management". No other distribution channel reaches this audience.

2. **Zero-friction install.** `claude plugin install obsidian-connector` is one command. Compare to the current flow: clone repo, run installer, configure Claude Desktop, restart. The plugin system handles skill registration, hook activation, and MCP server startup automatically.

3. **Community and contributors.** Marketplace presence signals legitimacy and invites contributions. Users who discover the plugin may file issues, submit PRs, or build on the skills/agents. This is the leverage needed to continue developing without doing everything solo.

4. **Anthropic validation.** Being accepted into the official marketplace is a credibility signal. It means the plugin passed Anthropic's review and meets their quality bar. This matters for adoption, especially in professional/enterprise contexts.

5. **Dual-mode architecture.** The plugin doesn't replace the existing installer or CLI. Users who want the full setup (scheduled briefings, launchd timers, Claude Desktop config) still use `install.sh`. The plugin is a lighter-weight entry point that gives immediate access to skills and MCP tools, with `setup.sh` for the Python venv. Power users graduate to the full install.

**Success criteria:** Plugin accepted into official marketplace. Users can `claude plugin install obsidian-connector`, run setup, and immediately use `/obsidian-connector:morning` and the 29 MCP tools.

---

## Gap Analysis

| # | Gap | Current | Required | Effort |
|---|-----|---------|----------|--------|
| 1 | Skills directory format | `skills/morning.md` (flat) | `skills/morning/SKILL.md` (nested) | S |
| 2 | No hooks.json | Hook config in `.claude/settings.json` | `hooks/hooks.json` with `${CLAUDE_PLUGIN_ROOT}` | S |
| 3 | No .mcp.json | MCP server exists but no plugin config | `.mcp.json` at plugin root | S |
| 4 | No setup mechanism | Installer creates venv manually | `scripts/setup.sh` for post-install bootstrap | M |
| 5 | No plugin-facing README | General repo README | Plugin-specific installation/usage docs | M |
| 6 | Duplicate commands/ | `.claude/commands/*.md` mirrors skills/ | Remove; plugin namespace handles routing | S |
| 7 | No CHANGELOG | Version history only in git | `CHANGELOG.md` for plugin versioning | S |
| 8 | install.sh hooks | Writes to `.claude/settings.json` | Should detect plugin mode and skip | S |

## Agent Team

| Role | Agent | Responsibility |
|------|-------|----------------|
| Scaffolder | Agent 1 | Restructure skills/, create hooks.json, .mcp.json, settings.json |
| Plumber | Agent 2 | Wire up setup.sh, update installer for plugin mode detection |
| Scribe | Agent 3 | README (plugin-facing), CHANGELOG.md, submission checklist |
| Validator | Agent 4 | Test with `claude --plugin-dir`, verify all components load |

**Dependency graph:**
```
Task 1 (branch) ─────────────────────────────────────────┐
Task 2 (skills restructure) ──┐                          │
Task 3 (hooks.json) ──────────┤                          │
Task 4 (.mcp.json) ───────────┼── Task 7 (installer) ───┤
Task 5 (setup.sh) ────────────┤                          ├── Task 10 (validate)
Task 6 (settings.json) ───────┘                          │           │
Task 8 (README + CHANGELOG) ─────────────────────────────┤  Task 11 (submit)
Task 9 (cleanup .claude/commands) ────────────────────────┘
```

**Parallel streams after Task 1:**
- Stream A (Scaffolder): Tasks 2, 3, 4, 6 -- all independent
- Stream B (Plumber): Task 5 (depends on nothing), Task 7 (depends on 2-6)
- Stream C (Scribe): Task 8 (independent)
- Stream D: Task 9 (independent)

---

## File Structure

### Files to create
- `skills/morning/SKILL.md` -- restructured from `skills/morning.md`
- `skills/evening/SKILL.md` -- restructured from `skills/evening.md`
- `skills/idea/SKILL.md` -- restructured from `skills/idea.md`
- `skills/weekly/SKILL.md` -- restructured from `skills/weekly.md`
- `hooks/hooks.json` -- SessionStart hook config for plugin system
- `.mcp.json` -- MCP server config at plugin root
- `settings.json` -- plugin default settings (root level)
- `scripts/setup.sh` -- post-install Python venv bootstrap
- `CHANGELOG.md` -- version history

### Files to modify
- `.claude-plugin/plugin.json` -- add component paths if non-default
- `scripts/install.sh` -- detect plugin mode, skip hook injection
- `scripts/install-linux.sh` -- same as above
- `AGENTS.md` -- update module map to reflect plugin structure

### Files to delete
- `skills/morning.md` -- replaced by `skills/morning/SKILL.md`
- `skills/evening.md` -- replaced by `skills/evening/SKILL.md`
- `skills/idea.md` -- replaced by `skills/idea/SKILL.md`
- `skills/weekly.md` -- replaced by `skills/weekly/SKILL.md`
- `.claude/commands/morning.md` -- plugin namespace replaces this
- `.claude/commands/evening.md` -- same
- `.claude/commands/idea.md` -- same
- `.claude/commands/weekly.md` -- same

---

## Tasks

### Task 1: Create feature branch

**Files:** None (git operation)

- [ ] **Step 1: Create branch from current HEAD**

```bash
git checkout -b feature/plugin-marketplace
```

- [ ] **Step 2: Verify branch**

```bash
git branch --show-current
```
Expected: `feature/plugin-marketplace`

---

### Task 2: Restructure skills to plugin format

**Files:**
- Create: `skills/morning/SKILL.md`, `skills/evening/SKILL.md`, `skills/idea/SKILL.md`, `skills/weekly/SKILL.md`
- Delete: `skills/morning.md`, `skills/evening.md`, `skills/idea.md`, `skills/weekly.md`

The Claude Code plugin system expects skills in `skills/<name>/SKILL.md` format, not flat `skills/<name>.md`. The content is identical -- only the directory structure changes.

- [ ] **Step 1: Create skill subdirectories**

```bash
mkdir -p skills/morning skills/evening skills/idea skills/weekly
```

- [ ] **Step 2: Move each skill into its subdirectory**

```bash
mv skills/morning.md skills/morning/SKILL.md
mv skills/evening.md skills/evening/SKILL.md
mv skills/idea.md skills/idea/SKILL.md
mv skills/weekly.md skills/weekly/SKILL.md
```

- [ ] **Step 3: Verify structure**

```bash
find skills -name "SKILL.md" | sort
```
Expected:
```
skills/evening/SKILL.md
skills/idea/SKILL.md
skills/morning/SKILL.md
skills/weekly/SKILL.md
```

- [ ] **Step 4: Verify frontmatter is intact**

Each SKILL.md must have `name` and `description` in YAML frontmatter. Spot-check:

```bash
head -4 skills/morning/SKILL.md
```
Expected:
```
---
name: morning
description: Run your morning briefing. Reads daily note, surfaces open loops and delegations, writes a briefing to your vault.
---
```

- [ ] **Step 5: Commit**

```bash
git add skills/
git commit -m "refactor: restructure skills to plugin SKILL.md format

Move skills/X.md -> skills/X/SKILL.md to match Claude Code plugin
directory convention."
```

---

### Task 3: Create hooks/hooks.json

**Files:**
- Create: `hooks/hooks.json`

The plugin hook system reads from `hooks/hooks.json`, not `.claude/settings.json`. The hook must use `${CLAUDE_PLUGIN_ROOT}` for portable paths.

- [ ] **Step 1: Write hooks.json**

Create `hooks/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/session_start.sh"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
python3 -c "import json; json.load(open('hooks/hooks.json')); print('valid')"
```
Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add hooks/hooks.json
git commit -m "feat: add plugin hooks.json for SessionStart hook

Uses \${CLAUDE_PLUGIN_ROOT} for portable path resolution."
```

---

### Task 4: Create .mcp.json

**Files:**
- Create: `.mcp.json`

The plugin MCP server config tells Claude Code how to start the MCP server. This requires the venv to exist (created by setup.sh in Task 5).

- [ ] **Step 1: Write .mcp.json**

Create `.mcp.json` at repo root:

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "${CLAUDE_PLUGIN_ROOT}/.venv/bin/python3",
      "args": ["-u", "-m", "obsidian_connector.mcp_server"],
      "cwd": "${CLAUDE_PLUGIN_ROOT}",
      "env": {
        "PYTHONPATH": "${CLAUDE_PLUGIN_ROOT}"
      }
    }
  }
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
python3 -c "import json; json.load(open('.mcp.json')); print('valid')"
```
Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add .mcp.json
git commit -m "feat: add .mcp.json for plugin MCP server config

Points to venv python. Requires scripts/setup.sh to run first."
```

---

### Task 5: Create setup.sh for post-install bootstrap

**Files:**
- Create: `scripts/setup.sh`

Users who install the plugin via `claude plugin install` still need a Python venv. This script creates it. It is referenced in the README and can be called manually or by a SessionStart hook that detects missing setup.

- [ ] **Step 1: Write setup.sh**

Create `scripts/setup.sh`:

```bash
#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# obsidian-connector plugin setup
#
# Creates the Python venv and installs dependencies.
# Run this after installing the plugin via `claude plugin install`.
#
# Usage:
#   bash <plugin-dir>/scripts/setup.sh
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
red()   { printf '\033[1;31m%s\033[0m\n' "$*"; }
dim()   { printf '\033[2m%s\033[0m\n' "$*"; }
die()   { red "ERROR: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

bold "obsidian-connector plugin setup"
dim  "plugin root: $PLUGIN_ROOT"
echo ""

# ── Check Python ────────────────────────────────────────────────────
bold "[1/3] Checking Python..."

PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    die "Python 3.11+ is required. Install from https://www.python.org/downloads/"
fi
green "  Found $PYTHON ($($PYTHON --version))"

# ── Create venv ─────────────────────────────────────────────────────
bold "[2/3] Setting up Python environment..."

if [ ! -d "$PLUGIN_ROOT/.venv" ]; then
    "$PYTHON" -m venv "$PLUGIN_ROOT/.venv"
    dim "  Created .venv"
else
    dim "  .venv already exists"
fi

"$PLUGIN_ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$PLUGIN_ROOT/.venv/bin/pip" install --quiet -e "$PLUGIN_ROOT"

green "  Installed obsidian-connector"

# ── Verify ──────────────────────────────────────────────────────────
bold "[3/3] Verifying..."

if "$PLUGIN_ROOT/.venv/bin/python3" -c "import obsidian_connector; print('  Package OK')" 2>/dev/null; then
    green "  Setup complete!"
else
    die "Package import failed."
fi

echo ""
bold "Next steps:"
echo "  1. Make sure Obsidian is running"
echo "  2. Restart Claude Code"
echo "  3. The obsidian-connector MCP tools and skills will be available"
echo ""
dim "Health check: $PLUGIN_ROOT/bin/obsx doctor"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/setup.sh
```

- [ ] **Step 3: Test setup.sh**

```bash
bash scripts/setup.sh
```
Expected: completes successfully (venv already exists from prior install)

- [ ] **Step 4: Commit**

```bash
git add scripts/setup.sh
git commit -m "feat: add plugin setup.sh for post-install venv bootstrap"
```

---

### Task 6: Create root settings.json (optional)

**Files:**
- Create: `settings.json` (at plugin root)

This is optional but useful if we want to set default plugin behavior. Currently no agent to activate, so this can be a placeholder or skipped.

- [ ] **Step 1: Evaluate need**

If no default `agent` setting is needed, **skip this task**. The plugin works without `settings.json`.

If we want a default agent later, create:

```json
{
  "agent": "obsidian-assistant"
}
```

This would require an agent definition in `agents/obsidian-assistant.md`.

- [ ] **Step 2: Decision -- skip for v0.2.0, revisit when agents are added**

---

### Task 7: Update installers for plugin mode detection

**Files:**
- Modify: `scripts/install.sh`
- Modify: `scripts/install-linux.sh`

The installer currently writes hooks to `.claude/settings.json`. When the user installs as a plugin, the hooks come from `hooks/hooks.json` instead. The installer should detect plugin mode and skip hook injection.

- [ ] **Step 1: Add plugin detection to install.sh**

After the "Optional: Second Brain Assistant" section header (line 237), add a plugin mode check before the skills and hook sections:

```bash
# ── Plugin mode detection ────────────────────────────────────────
# If installed as a Claude Code plugin, skills and hooks are handled
# by the plugin system. Only offer these for standalone installs.

PLUGIN_MODE=false
if [ -f "$REPO_ROOT/.claude-plugin/plugin.json" ] && \
   [ -f "$REPO_ROOT/hooks/hooks.json" ] && \
   [ -d "$REPO_ROOT/skills/morning" ]; then
    bold "Plugin mode detected"
    dim  "Skills and hooks are managed by the plugin system."
    dim  "Install via: claude --plugin-dir $REPO_ROOT"
    dim  "Or submit to a marketplace for: claude plugin install obsidian-connector"
    PLUGIN_MODE=true
fi
```

- [ ] **Step 2: Guard skills section with plugin mode check**

Wrap the skills install prompt (lines 245-262) with:

```bash
if [ "$PLUGIN_MODE" = false ]; then
    # ... existing skills install code ...
fi
```

- [ ] **Step 3: Guard hook section with plugin mode check**

Wrap the SessionStart hook prompt (lines 266-316) with:

```bash
if [ "$PLUGIN_MODE" = false ]; then
    # ... existing hook install code ...
fi
```

- [ ] **Step 4: Apply same changes to install-linux.sh**

Mirror the plugin mode detection and guards in the Linux installer.

- [ ] **Step 5: Test installer in plugin mode**

```bash
bash scripts/install.sh
```
Expected: Should show "Plugin mode detected" and skip skills/hook prompts.

- [ ] **Step 6: Commit**

```bash
git add scripts/install.sh scripts/install-linux.sh
git commit -m "feat: installer detects plugin mode, skips manual hook/skill setup"
```

---

### Task 8: Create CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write CHANGELOG.md**

```markdown
# Changelog

All notable changes to obsidian-connector will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-17

### Added
- Claude Code plugin structure (.claude-plugin/plugin.json)
- Plugin skills: /morning, /evening, /idea, /weekly
- Plugin hooks: SessionStart (proactive suggestions)
- Plugin MCP server config (.mcp.json)
- Plugin setup script (scripts/setup.sh)
- 29 MCP tools for Obsidian vault access
- Cross-platform installers (macOS DMG, Linux, manual)
- Graph-aware tools (neighborhood, backlinks, vault_structure)
- Thinking tools (ghost, drift, trace, ideas)
- Graduation pipeline (candidates, execute)
- Delegation system (@claude: instructions in vault)
- Check-in workflow with ritual detection
- Audit logging for mutations

### Fixed
- SessionStart hook format (nested {matcher, hooks} structure)

## [0.1.0] - 2026-02-19

### Added
- Initial release
- 8 core MCP tools (search, read, tasks, log_daily, log_decision, find_prior_work, create_note, doctor)
- 8 CLI commands
- Python API
- Claude Desktop installer
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG.md for plugin versioning"
```

---

### Task 9: Clean up .claude/commands/ duplicates

**Files:**
- Delete: `.claude/commands/morning.md`, `.claude/commands/evening.md`, `.claude/commands/idea.md`, `.claude/commands/weekly.md`

These are copies of the skills that were installed by the installer. With the plugin structure, skills are served via the plugin namespace (`/obsidian-connector:morning`).

**Note:** Keep `.claude/commands/harness-init.md` -- it is not part of the plugin.

- [ ] **Step 1: Remove duplicate skill files**

```bash
rm .claude/commands/morning.md
rm .claude/commands/evening.md
rm .claude/commands/idea.md
rm .claude/commands/weekly.md
```

- [ ] **Step 2: Verify harness-init.md is kept**

```bash
ls .claude/commands/
```
Expected: `harness-init.md` and `.gitkeep` remain.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/
git commit -m "chore: remove duplicate skill files from .claude/commands/

Plugin namespace handles skill routing now."
```

---

### Task 10: Validate plugin with --plugin-dir

**Files:** None (testing only)

- [ ] **Step 1: Run Claude Code with plugin loaded**

```bash
claude --plugin-dir ./path/to/obsidian-connector
```

- [ ] **Step 2: Verify skills load**

Inside Claude Code, run:
```
/help
```
Expected: skills listed under `obsidian-connector` namespace:
- `/obsidian-connector:morning`
- `/obsidian-connector:evening`
- `/obsidian-connector:idea`
- `/obsidian-connector:weekly`

- [ ] **Step 3: Verify hooks fire**

Start a new session. Expected: SessionStart hook outputs suggestions (if Obsidian is running and vault has data).

- [ ] **Step 4: Verify MCP server starts**

Check that MCP tools appear. Run:
```
/debug
```
Look for `obsidian-connector` MCP server initialization.

- [ ] **Step 5: Test a skill**

```
/obsidian-connector:idea test plugin validation
```
Expected: Idea logged to vault.

- [ ] **Step 6: Run existing tests**

```bash
python3 scripts/smoke_test.py
python3 scripts/mcp_tool_contract_test.py
bash scripts/mcp_launch_smoke.sh
```
Expected: All pass.

---

### Task 11: Prepare and submit to marketplace

**Files:** None (external action)

- [ ] **Step 1: Verify plugin.json is complete**

Check that `.claude-plugin/plugin.json` has all recommended fields:
- name, version, description, author, homepage, repository, license, keywords

All present already. Verify version matches CHANGELOG:

```bash
python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])"
```
Expected: `0.2.0`

- [ ] **Step 2: Verify directory structure**

```bash
echo "=== Plugin structure ===" && \
ls .claude-plugin/plugin.json && \
ls .mcp.json && \
ls hooks/hooks.json && \
find skills -name SKILL.md | sort && \
ls scripts/setup.sh && \
ls CHANGELOG.md && \
echo "=== All present ==="
```

- [ ] **Step 3: Push branch and open PR**

```bash
git push -u origin feature/plugin-marketplace
```

Then open PR for review.

- [ ] **Step 4: After merge, submit to Anthropic marketplace**

Go to one of:
- https://claude.ai/settings/plugins/submit
- https://platform.claude.com/plugins/submit

Fill in the submission form with:
- **Repository URL:** https://github.com/mariourquia/obsidian-connector
- **Plugin name:** obsidian-connector
- **Description:** Access your Obsidian vault from Claude. Search notes, read content, log decisions, manage tasks, and think with your notes -- 29 MCP tools plus morning/evening/weekly workflow skills.
- **Category:** productivity

- [ ] **Step 5: Document setup requirement**

The marketplace listing or README should note:
> After installing, run `bash <plugin-dir>/scripts/setup.sh` to set up the Python environment. Requires Python 3.11+ and the Obsidian desktop app.

---

## Open Questions

1. **Venv in plugin cache:** When installed from marketplace, plugins are cached to `~/.claude/plugins/cache/`. The `.mcp.json` points to `${CLAUDE_PLUGIN_ROOT}/.venv/bin/python3`. Does the setup.sh need to create the venv inside the cache directory? Test this during Task 10.

2. **SessionStart hook portability:** The hook script calls `$REPO_ROOT/bin/obsx`. In plugin mode, this should be `${CLAUDE_PLUGIN_ROOT}/bin/obsx`. The hook script uses `SCRIPT_DIR` to derive the path, which should work regardless. Verify during Task 10.

3. **marketplace.json necessity:** The `.claude-plugin/marketplace.json` is for self-hosted marketplaces. For the official Anthropic marketplace, it may not be needed. Keep it for now as it doesn't interfere. Can remove after submission if Anthropic confirms it's unnecessary.

4. **Agents directory:** No agents defined yet. This is fine for v0.2.0. Future versions could add an `agents/obsidian-assistant.md` for a dedicated vault-aware agent.
