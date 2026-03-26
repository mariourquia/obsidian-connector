---
title: "Maintainer Release Checklist: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Maintainer Release Checklist: obsidian-connector v0.2.0

Release: **obsidian-connector v0.2.0**
Branch: `feature/uninstaller` -> `main` (PR #13)
Tag: `v0.2.0`
Commits since v0.1.1: 38
Files changed: 59 (+11,796 / -135 lines)

---

## 1. Pre-Release

- [ ] Version string matches in all three locations:
  - `obsidian_connector/__init__.py` (`__version__ = "0.2.0"`)
  - `pyproject.toml` (`version = "0.2.0"`)
  - `mcpb.json` (`"version": "0.2.0"`)
  - `CHANGELOG.md` (`## [0.2.0] - 2026-03-16`)
- [ ] All CI-safe tests pass locally:
  ```bash
  make ci-local
  ```
- [ ] Docs lint passes:
  ```bash
  make docs-lint
  ```
- [ ] CHANGELOG.md has complete v0.2.0 entry (Added, Fixed, Changed, Documentation)
- [ ] README.md updated (35 tools, 35 commands, cross-platform install paths)
- [ ] TOOLS_CONTRACT.md updated (`obsidian_uninstall` name)
- [ ] ARCHITECTURE.md updated (platform.py, file_backend.py, uninstall.py in module table)
- [ ] SECURITY.md updated (v0.2.x supported, v0.1.x security-fixes-only)
- [ ] SBOM.md updated (v0.2.0, new stdlib-only modules listed)
- [ ] Release readiness review completed: `docs/generated/RELEASE_READINESS.md`
- [ ] No hardcoded secrets in codebase

---

## 2. Release Process

### 2a. Merge to main

```bash
# Push branch
git push -u origin feature/uninstaller

# Open PR
gh pr create \
  --base main \
  --head feature/uninstaller \
  --title "v0.2.0: Cross-platform support + security hardening" \
  --body "See .github/RELEASE_v0.2.0.md for full release notes."
```

- [ ] PR #13 opened: `feature/uninstaller` -> `main`
- [ ] CI passes (lint + test matrix: 3 OS x 3 Python + MCP launch smoke)
- [ ] PR reviewed
- [ ] PR merged

### 2b. Tag the release

```bash
git checkout main
git pull origin main
git tag -s v0.2.0 -m "v0.2.0: Cross-platform support + security hardening"
git push origin v0.2.0
```

- [ ] Tag `v0.2.0` created (signed via 1Password SSH / `op-ssh-sign`)
- [ ] Tag pushed to origin (triggers `.github/workflows/release.yml`)

### 2c. Release workflow builds artifacts

The release workflow (`.github/workflows/release.yml`) runs automatically on tag push:

1. `build-artifacts` (ubuntu-latest): source archives (tar.gz, zip) + checksums
2. `build-macos-dmg` (macos-latest): macOS .dmg installer
3. `create-release`: combines artifacts, generates final SHA256 file, creates draft GitHub Release

- [ ] Release workflow completes without errors
- [ ] All 4 artifacts attached to draft release:
  - `obsidian-connector-v0.2.0.tar.gz`
  - `obsidian-connector-v0.2.0.zip`
  - `obsidian-connector-v0.2.0.dmg`
  - `obsidian-connector-v0.2.0.sha256`

### 2d. Finalize GitHub Release

- [ ] Review the draft release on GitHub
- [ ] Copy release body from `.github/RELEASE_v0.2.0.md`
- [ ] Verify artifact download links work
- [ ] Verify checksums: `sha256sum -c obsidian-connector-v0.2.0.sha256`
- [ ] Publish the release (undraft)

---

## 3. Post-Release

- [ ] GitHub Release page renders correctly
- [ ] Compare link resolves: https://github.com/mariourquia/obsidian-connector/compare/v0.1.3...v0.2.0
- [ ] ROADMAP.md updated with completed v0.2.0 items
- [ ] Delete the `feature/uninstaller` branch after merge:
  ```bash
  git branch -d feature/uninstaller
  git push origin --delete feature/uninstaller
  ```
- [ ] Verify rollback procedure:
  ```bash
  git checkout v0.1.1
  rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -e .
  .venv/bin/python3 -c "import obsidian_connector; print('OK')"
  git checkout main
  ```
- [ ] Monitor GitHub Issues for immediate bug reports

---

## 4. Future: PyPI Publication

> Not yet active. Tracked as Roadmap item.

When PyPI publication is enabled, add:

```bash
python3 -m build
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ obsidian-connector==0.2.0
twine upload dist/*
```

Prerequisites:
- [ ] PyPI account and API token
- [ ] `twine` in dev dependencies
- [ ] TestPyPI dry run completed
