# Creation registry — single canonical source

**Status**: shipped
**Owner**: obsidian-connector
**Related**: `creation-dashboard.md`, `creation-vault-schema.md`

## Context

Two engines project repo state into the Creation Vault:

- the **bash nightly engine** `~/.local/bin/sync-creation-vault` (LaunchAgent +
  on-demand `/sync-vault`), which writes per-repo `projects/<repo>/{sync,index,todo}.md`
  and group hub notes; and
- the **Python/MCP engine** (`obsidian_connector.project_sync` +
  `creation_projects`), which powers the Phase 4 `obsx creation` dashboard
  read-layer and collapses repo groups into Projects.

Each had its own notion of "the repo registry". The bash engine hard-coded a
`REPOS` array, a `group_display()` map, and a `project_tags()` map. The Python
engine looked for `sync_config.json` in the vault root and, finding none, fell
back to `discover_repos()` — which labels **every** repo `group="standalone"`.
Result: the dashboard showed 57 standalone projects instead of grouping (MCMC's
9 repos, CRE Skills' 5, etc.), and the two engines could drift.

## Decision

Make **`sync_config.json` the single canonical source of truth**, read by both
engines. (Chosen over "generate JSON from bash" and "hand-seed once" — the user
selected JSON-canonical to end the drift permanently.)

### Where it lives

`sync_config.json` resolves (most specific first):

1. `$OBSIDIAN_SYNC_CONFIG` (explicit path; tests / power users)
2. `<vault root>/sync_config.json` (per-vault override)
3. `$XDG_CONFIG_HOME/obsidian-connector/sync_config.json`, else
   `~/.config/obsidian-connector/sync_config.json` — the **canonical home**

The canonical home is deliberately **not** the iCloud vault (the vault is not
git-tracked and large files there get evicted — the reason `~/dev` exists) and
**not** this public repo (the real registry lists private repos). The committed
`creation/sync_config.example.json` is a sanitized schema reference only.

### Schema additions

`SyncConfig` gains `group_display_names: dict[str, str]`, populated from a
top-level `groups` map. `creation_projects.list_projects` prefers it over the
built-in `GROUP_DISPLAY`, so groups absent from package code (e.g. `wine`,
`obsidian`, `signalforge`) still render proper Project names.

### Engine changes

- **Python** (`project_sync.py`): `resolve_sync_config_path()` +
  `xdg_sync_config_path()` implement the order above; `load_sync_config()` reads
  the resolved file and parses `groups`. Back-compatible — a vault-root config
  still wins, and absent everything falls back to `discover_repos()`.
- **bash** (`sync-creation-vault`): `REPOS`, `group_display()`, and
  `project_tags()` now read the same `sync_config.json` via `jq`; `github_root`
  too. A startup guard fails the run with a clear error if `jq` is missing or the
  registry is absent / invalid / empty — never a silent groupless sync.

### Creation vault default

`obsx creation` and the creation MCP tools now default to the vault named
`creation` (was the user's primary `default_vault`), so the dashboard targets
the Creation Vault and `~/dev` without an explicit `--vault`.

## Consequences

- The dashboard groups correctly: 57 → 19 Projects (MCMC = 9 repos, CRE Skills =
  5, Keiki/Obsidian = 3, AMOS/Research/SignalForge = 2).
- Editing the registry in one place updates both engines.
- New runtime dependency for the bash engine: `jq` (system-provided on macOS).
- Test hermeticity: an autouse `_isolate_user_config` fixture points
  `XDG_CONFIG_HOME` at a temp dir so tests never read the real canonical file.

## Migration

The initial canonical `~/.config/obsidian-connector/sync_config.json` was
exported faithfully from the bash engine's then-current `REPOS` / `group_display`
/ `project_tags` definitions (38 repos, 9 groups), preserving display names,
statuses, groups, and tags. Repos that previously relied on the `project_tags`
default have `["project", "<group>"]` baked in so the JSON is self-contained.
