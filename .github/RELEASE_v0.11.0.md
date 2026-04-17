```
  ___  _         _    _ _                ___
 / _ \| |__  ___(_) _| (_) __ _ _ __    / __\___  _ __  _ __   ___| |_ ___  _ __
| | | | '_ \/ __| |/ _` | |/ _` | '_ \ / /  / _ \| '_ \| '_ \ / _ \ __/ _ \| '__|
| |_| | |_) \__ \ | (_| | | (_| | | | / /__| (_) | | | | | | |  __/ || (_) | |
 \___/|_.__/|___/_|\__,_|_|\__,_|_| |_\____/\___/|_| |_|_| |_|\___|\__\___/|_|

                v0.11.0 -- Cross-Device Sync + Shared Vaults + CI Health
                         Turn Claude into your second brain.
```

## Highlights

- **Cross-device management (Task 42).** Two new HTTP wrappers, MCP tools, and CLI
  subcommands (`obsx mobile-devices`, `obsx forget-mobile-device`) over the new
  capture-service `/api/v1/mobile/devices` and `/forget` endpoints. The admin
  dashboard now lists every registered device with label / platform / app version /
  last-sync / pending-ops / first-seen.
- **Shared / collaborative vault foundation (Task 37).** Pure `detect_vault_conflicts`
  scanner surfaces iCloud / Dropbox / OneDrive / Obsidian Sync conflict-file patterns.
  New `docs/implementation/shared_vault.md` documents single-user multi-device setup.
  Strictly single-user; team collaboration stays out of scope per the product spec.
- **CI restored to green (Task 45).** Connector CI had been red since Task 41 merge
  due to a stale `AGENTS.md` cap, broken CI-only relative links, a Windows BOM bug
  in the installer smoke tests, and 18 shipped-but-undocumented MCP tools. Fixed
  all of them. Lint + manifest + integrity + smoke-windows all pass.
- **112 MCP tools.** Previously documented as 62. Inventory drift fixed.
- **632 tests passing.** Up from 611 at v0.9.0 (+22 for Task 42, +17 for Task 37 =
  633 added minus relocations = 632 net).

## What's New

### Features

| Feature | Description | Environment |
|---------|-------------|-------------|
| `obsidian_mobile_devices` | List every registered mobile sync device (Task 42) | CLI / MCP |
| `obsidian_forget_mobile_device` | Atomically drop a device row + cancel its pending ops | CLI / MCP |
| `detect_vault_conflicts` | Scan vault root for iCloud / Dropbox / OneDrive / Obsidian Sync conflict files | Python API |
| `obsx mobile-devices` | Human-readable device listing; `--json` for scripts | CLI |
| `obsx forget-mobile-device` | Confirms before dropping unless `--yes` / `--json` | CLI |

### Improvements

- **AGENTS.md trimmed from 196 -> 116 lines**, respecting its own 120-line hard
  limit. Per-task detail consolidated in CLAUDE.md (no loss of content).
- **TOOLS_CONTRACT.md** now documents all 112 MCP tools (was 94). Newly
  documented: 4 delegation tools (Task 38), 2 coaching tools (Task 40),
  5 bulk-action tools (Task 41), 2 cross-device tools (Task 42), 5 Ix
  code-investigation tools.
- **ARCHITECTURE.md** gains 13 previously-missing module rows (smart_triage,
  commitment_notes, commitment_ops, commitment_dashboards, entity_notes,
  admin_ops, approval_ops, analytics_ops, coaching_ops, import_tools,
  onboarding, recipes, vault_conflicts).
- **Admin dashboard** stale-sync-devices table now prefixes `device_label`
  when available so operators can disambiguate iPhone from Watch at a glance.

### Bug Fixes

- **Windows smoke test** no longer chokes on UTF-8 BOM in
  `installed_plugins.json` / `settings.json` / Claude Desktop config.
  `installer_smoke_test.py`, `Install.ps1`'s generated config-update script,
  and the `installer-smoke.yml` workflow all read JSON with `utf-8-sig`
  (BOM-tolerant) and write JSON with plain `utf-8` (no BOM propagation).
- **`docs/ONBOARDING.md`** sibling-repo link replaced with absolute GitHub
  URL. The old relative path (`../../obsidian-capture-service/...`) only
  resolved on the user's local checkout; CI boxes would break it.
- **`mcpb.json.tools_count`** 62 -> 112 to match `mcp_server.py`.
- **`scripts/integrity_check.py`** now skips `node_modules/`, `builds/`,
  `.tmp-graphify/`, `obsidian_connector/ix_engine/`, and `tools/` so
  third-party package.json versions and local Finder dupes don't trip CI.

## Installation

```bash
# Fresh install
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
./scripts/install.sh

# Upgrade from v0.9.0
git pull --ff-only
pip install -e . --upgrade
./bin/obsx doctor
```

The CLI surface (`obsx`) has added five subcommands since v0.9.0 but removed
none. Plugin manifest (`.claude-plugin/plugin.json`), marketplace manifest
(`mcpb.json`), and package metadata (`pyproject.toml`) are all at 0.11.0.

## Upgrade Notes

- **No breaking changes.** All v0.9.0 tool signatures, CLI flags, MCP schemas,
  and Python APIs are preserved. New fields on `SyncAckRequest`
  (`device_label`, `platform`, `app_version`) are optional; pre-v0.11.0
  payloads continue to work.
- **Capture-service requirement**: this version talks to obsidian-capture-service
  v0.11.0. For the new `obsidian_mobile_devices` / `obsidian_forget_mobile_device`
  tools to return real data, the service side must have Task 42 deployed
  (migration v010 applied).
- **Dashboards auto-pick-up**: the admin dashboard's new "Mobile devices"
  section renders automatically on the next
  `obsx review-dashboards` / `update_all_dashboards()` call. No manual
  re-init needed.

## Known Limitations

- **Single-user only.** Multi-user / team mode is deferred to a future wave
  (see `docs/exec-plans/active/wave-5-triage.md`). Task 37 is strictly
  single-user multi-device, not multi-user.
- **Conflict-file detection** returns results for operator reconciliation.
  It does not auto-resolve conflicts, auto-delete conflict copies, or surface
  via CLI / MCP in this release (all planned second-pass items).
- **`lockfile-check` CI step** remains advisory (`continue-on-error: true`).
  `requirements-lock.txt` will show drift vs a fresh `pip-compile` run;
  regeneration is deferred.

## Tests

- 632 passing (1 skipped) as of merge `ce9aec8`.
- CI green across macOS / Ubuntu / Windows on Python 3.11 / 3.12 / 3.13.
- All seven smoke and integrity checks green: lint, manifest_check,
  integrity_check, smoke-macos, smoke-windows, mcp-launch (macOS + Ubuntu),
  CodeQL.
- Test counts by module (connector-side only):
  - vault_conflicts (new): 17
  - devices_ops (Task 42): 22
  - bulk_actions (Task 41): 36
  - coaching_ops (Task 40): 34
  - delegation_connector (Task 38): 39
  - analytics_helpers (Task 39): 29
  - import_tools (Task 43): 61

## Security Posture

- No new network endpoints exposed by the connector; every new wrapper calls
  back to the user-controlled `OBSIDIAN_CAPTURE_SERVICE_URL`.
- No hardcoded secrets. Tokens are read from
  `OBSIDIAN_CAPTURE_SERVICE_TOKEN` env var only.
- `forget_mobile_device` accepts a device id and URL-quotes it before
  building the path -- no path traversal surface.
- Install.ps1 no longer hangs on BOM in the generated config-update script;
  the read path explicitly tolerates BOM, the write path explicitly does not
  emit one.

## Breaking Changes

None.

## Migration Guide

Direct upgrade path from v0.9.0. No code changes required on the user's side.

## Contributors

- Mario Urquia ([@mariourquia](https://github.com/mariourquia))

## What's Next

- **Task 15.B / 15.C**: embeddings similarity + LLM wiki body generator
  (Semantic memory layer phase 2+3).
- **Task 37 phase 2**: CLI (`obsx vault-conflicts`) + MCP tool
  (`obsidian_vault_conflicts`) + `Dashboards/Admin.md` "Vault conflicts"
  section.
- **Wave 6 (speculative)**: team mode, if and when there is a concrete
  multi-user signal. See `docs/exec-plans/active/wave-5-triage.md` for the
  explicit posture on what we are NOT building.

## Links

- Service companion: `obsidian-capture-service` v0.11.0 (same release wave)
- Documentation: [README.md](../README.md), [AGENTS.md](../AGENTS.md),
  [CLAUDE.md](../CLAUDE.md), [ARCHITECTURE.md](../ARCHITECTURE.md)
- Security: [SECURITY.md](../SECURITY.md)
- Privacy: [PRIVACY.md](../PRIVACY.md)
- SBOM: [SBOM.md](../SBOM.md)
