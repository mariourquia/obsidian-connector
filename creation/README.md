# Creation registry (`sync_config.json`)

The Creation Vault's repo registry is the **single source of truth** shared by
both engines that project repo state into the vault:

- the Python/MCP engine (`obsidian_connector.project_sync.load_sync_config`,
  the `obsx creation` dashboard read-layer), and
- the bash nightly engine (`~/.local/bin/sync-creation-vault`).

Both consume the `sync_config.json` registry format. It lists every tracked
repo, its display name, status, group, and tags; the group display-name map;
and `github_root`. They select the same file when configured with the same
existing explicit path, or when both use the same canonical home without a
Python per-vault override.

## Where it lives (engine-specific resolution)

The Python/MCP engine selects the first existing file:

1. `$OBSIDIAN_SYNC_CONFIG` (explicit path; used by tests / power users)
2. `<vault root>/sync_config.json` (per-vault override)
3. `$XDG_CONFIG_HOME/obsidian-connector/sync_config.json`, else
   `~/.config/obsidian-connector/sync_config.json` (**canonical home**)

A missing explicit path is ignored. If no registry is found, or the parsed
configuration contains no repos, Python falls back to repository discovery.

The bash nightly engine selects `$OBSIDIAN_SYNC_CONFIG` when nonempty;
otherwise it uses `$XDG_CONFIG_HOME/obsidian-connector/sync_config.json`, or
`~/.config/obsidian-connector/sync_config.json` when XDG is unset or empty.
It does not check the vault-root override. Missing, invalid, or empty registry
input fails the run; it does not fall back to discovery.

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
