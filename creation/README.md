# Creation registry (`sync_config.json`)

The Creation Vault's repo registry is the **single source of truth** shared by
both engines that project repo state into the vault:

- the Python/MCP engine (`obsidian_connector.project_sync.load_sync_config`,
  the `obsx creation` dashboard read-layer), and
- the bash nightly engine (`~/.local/bin/sync-creation-vault`).

Both read the same `sync_config.json`. It lists every tracked repo, its display
name, status, group, and tags; the group display-name map; and `github_root`.

## Where it lives (resolution order)

Most specific first:

1. `$OBSIDIAN_SYNC_CONFIG` (explicit path; used by tests / power users)
2. `<vault root>/sync_config.json` (per-vault override)
3. `$XDG_CONFIG_HOME/obsidian-connector/sync_config.json`, else
   `~/.config/obsidian-connector/sync_config.json` (**canonical home**)

The canonical home is intentionally **not** the iCloud vault (avoids file
eviction) and **not** this public repo (the real registry lists private repos).
`sync_config.example.json` here is a sanitized schema reference only.

## Schema

| Field | Type | Notes |
|-------|------|-------|
| `github_root` | string | Directory containing the repos (e.g. `~/dev`). `~` is expanded. |
| `vault_subdir` | string | Sync output subdir within the vault. `""` = vault root. |
| `groups` | object | `slug -> display name`. Layered over the built-in `GROUP_DISPLAY` map. |
| `repos[].dir_name` | string | Folder name under `github_root` (no path separators). |
| `repos[].display_name` | string | Human label. |
| `repos[].guidance_file` | string | `CLAUDE.md` / `AGENTS.md` / `README.md`. |
| `repos[].status` | string | `active` \| `paused` \| `dormant` \| `archived`. |
| `repos[].group` | string | Group slug. Non-`standalone` repos sharing a slug collapse into one Project. |
| `repos[].tags` | string[] | Tags surfaced on the project hub note and `Project.tags`. |

## Requirements

The bash engine reads the JSON via `jq` (`brew install jq`). Missing `jq`, a
missing/invalid registry, or an empty `repos` list fails the nightly run with a
clear error rather than silently syncing nothing.
