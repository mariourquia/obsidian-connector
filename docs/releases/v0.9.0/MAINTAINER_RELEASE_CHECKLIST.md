# Maintainer Release Checklist: obsidian-connector 0.9.0

> Base: v0.8.3 -> HEAD `099af67101645faea8ad8b48a00f8c39e387ba1c` on `main`
> Target: v0.9.0

## Pre-Release

- [x] All PRs for this release are merged to main (PRs #49, #50, #51 merged)
- [x] CI passes on main on HEAD 099af67 (ci.yml, security.yml, installer-smoke.yml)
- [x] CHANGELOG.md updated with all changes for 0.9.0 (entry exists under `[0.9.0] - 2026-04-13`)
- [x] Version bumped in manifest
  - `pyproject.toml [project] version`: `0.8.3` -> `0.9.0`
  - `mcpb.json version`: `0.8.3` -> `0.9.0`
  - `builds/claude-code/plugin.json`: synced to `0.9.0` in commit 3fd3d9a
- [x] Dependency lockfile regenerated (`requirements-lock.txt`, 37275 bytes)
- [x] No hardcoded secrets (gitleaks + manual grep: all matches benign)
- [ ] Breaking changes documented with migration path
  - No public-API breaking changes in 0.9.0.
  - `textual` moved from runtime to `[tui]` extra. Users who import TUI without
    the extra will get a clear `ModuleNotFoundError` hint (see
    `test_cli_tui_optional.py`). Documented in RELEASE_NOTES.md and
    COMPATIBILITY_MATRIX.md.
- [x] README install instructions verified for 0.9.0 (`docs/INSTALL.md`,
  `docs/INSTALL-SURFACES.md`)
- [x] Release readiness review completed (see `RELEASE_READINESS_REVIEW.md`)

## Release Artifacts

- [ ] Git tag created and signed: `git tag -s v0.9.0 -m "Release v0.9.0"`
  - Signing key: ED25519 `SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4`
  - All 23 release-branch commits confirmed `G` (valid signature) under that key.
- [ ] Release notes drafted (see `RELEASE_NOTES.md`)
- [ ] Binary artifacts built
  - [ ] Python wheel + sdist (`python -m build`)
  - [ ] MCPB archive (`mcpb` CLI)
  - [ ] Claude Code plugin bundle (`builds/claude-code/`)
  - [ ] macOS DMG (via `build-macos-dmg.yml`)
  - [ ] Windows installer (via `build-windows-installer.yml`)
- [ ] Checksums generated: `sha256sum dist/* > SHA256SUMS.txt`
- [ ] Checksums signed: `gpg --armor --detach-sign SHA256SUMS.txt`
- [ ] SBOM regenerated for 0.9.0 (current `SBOM.md` still headed v0.2.0)

## Publication

- [ ] GitHub Release created with notes and assets
  - Title: `v0.9.0`
  - Notes-file: `docs/releases/v0.9.0/RELEASE_NOTES.md`
  - Assets: wheel, sdist, MCPB, Claude Code plugin zip, DMG, MSI, SHA256SUMS
- [ ] Package published to PyPI (`twine upload dist/*`) -- OPTIONAL (this
  project has been GitHub-release-only in prior versions; confirm current
  distribution policy before publishing to PyPI)
- [ ] Publication verified: install from registry or release asset in clean venv
- [ ] Version check passes: `obsx --version` shows `0.9.0`
- [ ] `verify-release.yml` workflow runs and promotes draft to live

## Post-Release

- [ ] Announce release in any active discussion channels
- [ ] Monitor GitHub Issues for 72 hours post-release
- [ ] Update dependent project: obsidian-capture-service Task 20 pin to
  `obsidian-connector==0.9.0` (or `>=0.9.0,<0.10.0`)
- [ ] Refresh `SECURITY.md` "Supported Versions" matrix (`0.7.x` -> `0.9.x`)
- [ ] Refresh `SBOM.md` header (currently stamped v0.2.0, 2026-03-16)
- [ ] Review `builds/` untracked directories
  (`obsidian_connector/`, `skills/`, `requirements-lock.txt`, `cowork/`,
  `portable/`, `claude-desktop/`) -- either `.gitignore` them or relocate
- [ ] Confirm rollback procedure: `pip install obsidian-connector==0.8.3`
  installs cleanly from a fresh venv
- [ ] Add `[Unreleased]` section back to top of CHANGELOG.md for 0.10.0 cycle
