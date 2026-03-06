---
title: "Design Doc: Team/Shared Vault Pattern"
status: draft
owner: "mariourquia"
last_reviewed: "2026-03-05"
review_cycle_days: 90
sources_of_truth:
  - "config.json"
  - "obsidian_connector/config.py"
related_docs:
  - "docs/exec-plans/active/graph-aware-roadmap.md"
tags:
  - multi-vault
  - privacy
  - team-access
---

# Design Doc: Team/Shared Vault Pattern

## Context

As obsidian-connector gains graph-aware capabilities and agent-driven workflows,
vaults will increasingly serve as shared knowledge spaces where multiple humans
and agents operate concurrently. This document defines conventions for vault
structure, access control, privacy boundaries, and conflict resolution in that
setting.

This is a design-only artifact. No code changes are proposed here.

## Goals

- Define folder conventions for shared vs. personal content
- Establish privacy boundaries that agents respect by default
- Specify where agents write drafts in a shared context
- Address conflict resolution for concurrent agent and human writes
- Document sync strategy recommendations for team vaults

## Non-goals

- Implementing RBAC or file-level permissions (Obsidian has no ACL layer)
- Building a multi-tenant server (obsidian-connector is local-first)
- Replacing Obsidian Sync or git-based sync with a custom solution

## Background

Obsidian vaults are local folders. There is no built-in access control, user
identity, or permission model. Privacy is achieved through convention (folder
names, tags) and sync configuration (selective sync, `.gitignore`). Agents
access vaults through obsidian-connector, which can enforce read/write
boundaries in software even though the filesystem does not.

---

## 1. Vault Structure Conventions

### Recommended layout

```
Vault Root/
  Shared/                    # Readable by all humans and agents
    Projects/                # Active project notes
    References/              # Permanent reference material
    Meeting Notes/           # Shared meeting records
    Agent Drafts/            # Agent-generated content (see section 4)
      mario/                 # Per-user subfolder
      agent-a/               # Per-agent subfolder (if named)
    Templates/               # Shared templates
  Personal/                  # Per-user, excluded from agent reads
    mario/                   # One subfolder per person
      Journal/
      Scratch/
      Drafts/
  Context/                   # Identity and preference files
    Life Context.md          # Read by agents for personalization
    Work Context.md          # Project inventory for agent awareness
    Voice Profile.md         # Writing style guidance for agents
  Archive/                   # Completed/inactive material
  Inbox/                     # Quick capture, triage target
```

### Naming rules

- Top-level folders use Title Case.
- No spaces in programmatic paths where avoidable; spaces are acceptable in
  human-facing folder names (Obsidian handles them).
- `Personal/` and `Shared/` are reserved prefixes with semantic meaning
  (see section 2).

### Single-user simplification

For solo vaults, `Shared/` is unnecessary. The entire vault is implicitly
"shared" with the user's agents. `Personal/` still functions as the agent
exclusion zone.

---

## 2. Access Control Model

Obsidian has no file-level permissions. Access control is enforced by
obsidian-connector at the application layer.

### Folder-based privacy (primary model)

| Folder prefix | Human access | Agent read | Agent write |
|---------------|-------------|------------|-------------|
| `Personal/`   | Owner only  | Blocked    | Blocked     |
| `Shared/`     | All         | Allowed    | Allowed (Agent Drafts only) |
| `Context/`    | All         | Allowed    | Blocked     |
| `Archive/`    | All         | Allowed    | Blocked     |
| `Inbox/`      | All         | Allowed    | Allowed     |
| (other)       | All         | Allowed    | Config-dependent |

Agent write access is restricted to designated folders (`Inbox/`,
`Shared/Agent Drafts/`) by default. This prevents agents from modifying
human-authored notes without explicit intent.

### Tag-based privacy (alternative model)

For vaults where folder reorganization is impractical:

- `#private` tag on any note excludes it from agent reads.
- `#agent-visible` tag explicitly opts a note into agent access.
- Default: all notes without `#private` are readable.

Tag-based control requires the graph module to parse frontmatter tags
before passing content to agents. It is more flexible but harder to audit
than folder-based control.

### Configuration

Privacy boundaries are specified in `config.json`:

```json
{
  "privacy": {
    "excluded_prefixes": ["Personal/"],
    "excluded_tags": ["private"],
    "agent_write_folders": ["Inbox", "Shared/Agent Drafts"],
    "read_only_prefixes": ["Context/", "Archive/"]
  }
}
```

---

## 3. Privacy Boundaries for Agent Reads

### Default behavior

Agents can read everything except paths matching `excluded_prefixes` or
notes tagged with `excluded_tags`. The default exclusion list is:

- `Personal/` (any depth)
- Notes with `#private` in frontmatter tags

### Enforcement points

1. **Graph index** (`graph.py`): Skip excluded paths during indexing.
   Excluded notes do not appear in link graphs, tag counts, or search
   results returned to agents.
2. **MCP tools**: Every tool that reads note content checks the exclusion
   list before returning data. If a tool is asked to read an excluded note,
   it returns an error envelope with `"code": "PRIVACY_EXCLUDED"`.
3. **CLI**: The `obsx` CLI does not enforce privacy (it is a human tool).
   Privacy is an agent-facing concern only.

### Context files exception

Files in `Context/` are read-only but explicitly agent-readable. They
exist to give agents background knowledge (identity, projects, voice).
They should not contain sensitive data (credentials, financial details,
health records).

---

## 4. Agent Draft Location in Shared Context

### Convention

All agent-generated content lands in `Shared/Agent Drafts/` with per-user
subfolders:

```
Shared/Agent Drafts/
  mario/
    2026-03-05-research-summary.md
    2026-03-05-meeting-prep.md
  scheduled/
    weekly-review-template.md
```

### Rules

- Agents never overwrite existing files. They create new files only.
- Filenames include ISO date prefix for sortability: `YYYY-MM-DD-slug.md`.
- Drafts are explicitly labeled as agent-generated in frontmatter:
  ```yaml
  ---
  generated_by: "obsidian-connector"
  created: "2026-03-05T14:30:00Z"
  status: draft
  ---
  ```
- Humans promote drafts by moving them out of `Agent Drafts/` into the
  appropriate project folder. This is a deliberate acceptance step.
- The `agent_drafts` folder is configurable in `config.json` under
  `default_folders.agent_drafts`.

### Daily notes

Daily note appends (`log_to_daily`) are the exception. They write to the
daily note location (typically `Daily/YYYY-MM-DD.md`), not to Agent Drafts.
This is acceptable because appends do not overwrite content.

---

## 5. Conflict Resolution for Concurrent Writes

### File-level conflicts (sync layer)

Obsidian Sync handles file-level conflicts with last-write-wins and a
conflict file mechanism. Git-based sync uses standard merge conflict
resolution. Neither is controlled by obsidian-connector.

### Agent write conflicts

obsidian-connector mitigates conflicts through these rules:

1. **Atomic create, never overwrite.** Agent writes use `create_note()`
   which fails if the target file already exists. This eliminates
   write-write conflicts.
2. **Timestamp in filename.** When uniqueness is uncertain, include
   ISO timestamp: `2026-03-05T143000-slug.md`.
3. **Append-only for daily notes.** `log_to_daily()` appends to the end
   of the daily note. Concurrent appends may interleave lines but will not
   lose data.
4. **Audit trail.** All agent writes are logged via `audit.py` with
   timestamp, tool name, vault, and target path. This enables post-hoc
   conflict diagnosis.

### Recommendations for teams

- Assign each agent a unique subfolder under `Agent Drafts/`.
- Avoid having multiple agents write to the same file simultaneously.
- Use Obsidian Sync's selective sync to partition write zones if needed.

---

## 6. Integration with Sync

### Obsidian Sync (recommended for teams)

- End-to-end encrypted, proprietary protocol.
- Selective sync: exclude `Personal/` folders per-device.
- Conflict resolution: creates duplicate files with timestamp suffix.
- Limitation: no merge, no diff, no history beyond version snapshots.
- Cost: per-user subscription.

### Git-based sync (obsidian-git, LiveSync)

- Full version history, branching, merge conflict resolution.
- Requires all team members to understand git basics.
- `.gitignore` enforces `Personal/` exclusion at the repo level.
- LiveSync (CouchDB) offers real-time sync without git complexity.
- Risk: large binary files (images, PDFs) bloat the repo.

### iCloud / Dropbox / OneDrive

- Simple setup, no configuration.
- No conflict resolution beyond last-write-wins.
- Not recommended for team vaults due to sync race conditions.
- Acceptable for single-user vaults with agent access.

### Sync + privacy matrix

| Sync method    | Personal/ exclusion | Conflict handling | Team suitability |
|----------------|--------------------|--------------------|------------------|
| Obsidian Sync  | Selective sync     | Duplicate file     | High             |
| Git (obsidian-git) | .gitignore    | Merge conflict     | Medium           |
| LiveSync       | Filter rules       | CouchDB conflict   | Medium           |
| iCloud/Dropbox | Not enforceable    | Last-write-wins    | Low              |

---

## 7. Impact on Existing Tools

### Multi-vault support

Currently, `config.json` has a single `default_vault`. For team use with
multiple vaults, the config needs vault profiles:

```json
{
  "vaults": {
    "personal": {
      "name": "My Vault",
      "privacy": { "excluded_prefixes": [] }
    },
    "team": {
      "name": "Team Vault",
      "privacy": { "excluded_prefixes": ["Personal/"] }
    }
  },
  "default_vault": "team"
}
```

The `--vault` CLI flag and `vault` MCP tool parameter already exist. The
change is in config resolution: look up the vault profile by alias, then
resolve the Obsidian vault name from the profile.

### Tool changes required

| Tool / Module   | Change needed |
|-----------------|---------------|
| `config.py`     | Parse vault profiles from config.json |
| `client.py`     | Pass privacy config to all read operations |
| `graph.py`      | Exclude private paths during indexing |
| `mcp_server.py` | Return `PRIVACY_EXCLUDED` error for blocked reads |
| `cli.py`        | No change (CLI is human-facing, no privacy enforcement) |
| `audit.py`      | Log vault profile alias alongside vault name |

### Migration path

1. Current single-vault config continues to work unchanged.
2. If `vaults` key is present in config.json, it takes precedence.
3. `default_vault` can be either a vault name (legacy) or a profile
   alias (new).

---

## Open Questions

- [ ] Should `Context/` files be synced to all devices, or only to
      agent-running devices?
- [ ] Is tag-based privacy worth implementing in M1, or defer to M2?
- [ ] Should agent drafts auto-expire (delete after N days if not promoted)?
- [ ] How should vault profiles interact with the MCP server's vault
      parameter (pass alias or Obsidian vault name)?
