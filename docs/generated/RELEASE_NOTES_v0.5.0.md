```
  ___  _         _    _ _                ___
 / _ \| |__  ___(_) _| (_) __ _ _ __    / __\___  _ __  _ __   ___| |_ ___  _ __
| | | | '_ \/ __| |/ _` | |/ _` | '_ \ / /  / _ \| '_ \| '_ \ / _ \ __/ _ \| '__|
| |_| | |_) \__ \ | (_| | | (_| | | | / /__| (_) | | | | | | |  __/ || (_) | |
 \___/|_.__/|___/_|\__,_|_|\__,_|_| |_\____/\___/|_| |_|_| |_|\___|\__\___/|_|

   v0.5.0 -- Idea Routing, Vault Factory, Auto-Detect, 13 Presets
                    Turn Claude into your second brain.
```

## Highlights

- **Ideas captured automatically.** A `UserPromptSubmit` hook detects tangential ideas
  ("what if we...", "we should eventually...") and routes them to the right project's
  idea file -- no slash command needed. The user thinks at the speed of thought.
- **Vault factory.** Create a new Obsidian vault for any topic alongside your existing
  vaults. Seeds with research stubs. Discard if not useful.
- **13 vault presets** (was 11). New: `poetry` and `songwriting` with craft notes at
  foundations/intermediate/advanced levels.
- **Vault guardian.** Auto-generated files marked with "do not edit" callouts.
  Unorganized notes in vault root detected and placed into the correct folder.
- **Existing vault safety.** Sync output isolated in `Project Tracking/` subdirectory
  when connecting to an existing vault with user content.
- **47 MCP tools. 13 skills. 13 presets.**

## What's New

### Auto-Detect Ideas (No Skill Invocation Needed)

The plugin's `UserPromptSubmit` hook injects context that tells Claude to detect
idea patterns in conversation and silently capture them:

- "I had an idea about..." -> routed to the matching project
- "What if we built a flight tracker?" -> inception card in `Inbox/Project Ideas/`
- "Someday we should add push notifications to keiki" -> `Inbox/Ideas/keiki.md`

The user never invokes `/float`. Claude just captures it and says "Captured to {project}."

### Vault Factory

```bash
obsx create-vault --name "Aviation Research" --preset research
```

Auto-detects where existing vaults live and creates the new one alongside them.
Seeds with research stubs for each topic. Available as MCP tool or `/explore` skill.

### 13 Vault Presets

| Preset | New? | Description |
|--------|:----:|-------------|
| journaling | | Daily prompts, gratitude, reflection |
| mental-health | | CBT thought records, mood tracking, coping toolkit |
| business-ideas | | Idea evaluation, market analysis, pitch templates |
| research | | Literature notes, reading lists, methodology |
| project-management | | Sprint planning, retros, decision logs |
| second-brain | | Zettelkasten: fleeting, literature, permanent, MOCs |
| vacation-planning | | Itineraries, budgets, packing, bookings |
| life-planning | | Goals, values, quarterly reviews, vision |
| budgeting | | Expense tracking, financial goals, debt payoff |
| creative-writing | | Story structure, POV, dialogue, revision, publishing |
| self-expression | | Free writing, manifestos, mood boards |
| **poetry** | Yes | Forms (haiku/sonnet/free verse), meter, imagery, chapbook building |
| **songwriting** | Yes | Song structure, chord progressions, hooks, AI production, sync licensing |

### Vault Guardian

- Auto-generated files (Dashboard, projects/*.md) marked with Obsidian callouts
- Unorganized notes in vault root detected and placed into correct folders
- User content never overwritten or moved from subfolders

### Existing Vault Safety

When connecting to an existing vault with user content, all sync output goes
into `Project Tracking/` subdirectory. User notes are untouched.

### New MCP Tools

| Tool | What it does |
|------|-------------|
| `obsidian_float_idea` | Auto-route an idea to the right project |
| `obsidian_incubate_project` | Create an inception card for a future project |
| `obsidian_incubating` | List all incubating project ideas |
| `obsidian_idea_files` | List idea routing files with counts |
| `obsidian_create_vault` | Create a vault with preset template |
| `obsidian_seed_vault` | Add research notes to a vault |
| `obsidian_vault_presets` | List available preset templates |
| `obsidian_list_vaults` | List all registered Obsidian vaults |
| `obsidian_discard_vault` | Remove an unwanted vault (requires confirm) |
| `obsidian_mark_auto_generated` | Mark sync-overwritten files |
| `obsidian_detect_unorganized` | Find misplaced notes |
| `obsidian_organize_file` | Move notes to correct folder |

### New Hooks

| Hook | Event | What it does |
|------|-------|-------------|
| `idea_detect.md` | UserPromptSubmit | Auto-detects ideas and captures them |
| `session_stop.sh` | Stop | Auto-syncs vault (debounced, background) |

## Testing

- 56 assertions in `project_sync_test.py`, 8 in `smoke_test.py`
- 17 test files total (6300+ lines)
- CI: 9 matrix combinations (3 OS x 3 Python)
- 0 regressions on existing suite
- **Known gap**: `idea_router.py`, `vault_guardian.py`, `vault_factory.py`, `vault_presets.py` have no dedicated test scripts (tested via import and MCP registration checks only)

## Compatibility

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| Obsidian | 1.12+ (with CLI enabled) |
| OS | macOS, Linux, Windows |
| MCP | 1.0.x |
| Node.js | 18+ (optional, for defuddle skill) |

## Breaking Changes

None. This release is purely additive.

## Assets

Built by GitHub Actions CI on clean runners. Cosign keyless OIDC signatures.

| File | Description |
|------|-------------|
| `obsidian-connector-v0.5.0.dmg` | macOS installer |
| `obsidian-connector-v0.5.0-setup.exe` | Windows installer |
| `obsidian-connector-v0.5.0.tar.gz` | Source archive |
| `obsidian-connector-v0.5.0.zip` | Source archive |
| `obsidian-connector-v0.5.0.sha256` | SHA-256 checksums |
| `.sig` + `.cert` files | Cosign keyless OIDC signatures |

## Verify

```bash
shasum -a 256 -c obsidian-connector-v0.5.0.sha256
cosign verify-blob --signature obsidian-connector-v0.5.0.tar.gz.sig \
  --certificate obsidian-connector-v0.5.0.tar.gz.cert \
  obsidian-connector-v0.5.0.tar.gz
```

## Full Changelog

**[v0.4.0...v0.5.0](https://github.com/mariourquia/obsidian-connector/compare/v0.4.0...v0.5.0)**
