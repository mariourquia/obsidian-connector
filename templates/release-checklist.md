# Release Checklist -- obsidian-connector vX.Y.Z

Use this checklist when cutting a new release. Copy this file into the
release PR description or a tracking issue.

## Pre-release

- [ ] Version bump in all canonical locations:
  - [ ] `pyproject.toml` (`version = "X.Y.Z"`)
  - [ ] `obsidian_connector/__init__.py` (`__version__ = "X.Y.Z"`)
  - [ ] `marketplace.json` (plugin `version` field)
  - [ ] `mcpb.json` (`version` field)
  - [ ] `plugin.json` (`version` field, if present)
- [ ] Run `python3 scripts/manifest_check.py` -- all counts and versions match
- [ ] Run `python3 scripts/generate_compat_matrix.py` -- matrix regenerated

## Documentation

- [ ] Update `CHANGELOG.md` with new version section
- [ ] Update `TOOLS_CONTRACT.md` with any new or changed tools
- [ ] Update `ARCHITECTURE.md` with any new modules
- [ ] Update `CLAUDE.md` with new tool/skill/preset counts
- [ ] Update `README.md` with new counts if they changed

## Testing

- [ ] Run all test scripts (`scripts/*_test.py`)
- [ ] Run smoke tests (`python3 scripts/smoke_test.py`)
- [ ] Run MCP launch smoke test (`bash scripts/mcp_launch_smoke.sh`)
- [ ] Run import cycle test (`python3 scripts/import_cycle_test.py`)
- [ ] Run CLI parse test (`python3 scripts/cli_parse_test.py`)
- [ ] Manual test: MCP tools in Claude Desktop
- [ ] Manual test: CLI commands via `obsx`
- [ ] Manual test: Skills in Claude Code plugin mode

## Release

- [ ] Tag release (`git tag vX.Y.Z`)
- [ ] Build DMG (`bash scripts/create-dmg.sh`)
- [ ] Sign release assets (cosign)
- [ ] Create GitHub release with changelog excerpt
- [ ] Upload DMG and any other artifacts to release

## Post-release

- [ ] Verify DMG install on clean macOS machine
- [ ] Verify plugin install via `claude plugin install`
- [ ] Update downstream references (if any)
