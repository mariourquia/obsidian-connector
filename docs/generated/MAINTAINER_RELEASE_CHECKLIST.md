---
title: "Maintainer Release Checklist"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Maintainer Release Checklist -- v0.1.3

Release: **obsidian-connector v0.1.3**
Branch: `feature/uninstaller` -> `main`
Tag: `v0.1.3`

---

## 1. Pre-Release

- [ ] Version string matches in all three locations:
  - `obsidian_connector/__init__.py` (`__version__ = "0.1.3"`)
  - `pyproject.toml` (`version = "0.1.3"`)
  - `CHANGELOG.md` (`## [0.1.3] - YYYY-MM-DD` with correct date)
- [ ] All tests pass:
  ```bash
  python3 scripts/smoke_test.py
  python3 scripts/cache_test.py
  bash scripts/mcp_launch_smoke.sh
  ```
- [ ] Docs lint passes:
  ```bash
  make docs-lint
  ```
- [ ] `CHANGELOG.md` has a complete entry for v0.1.3 with Added, Security sections and a compare link at the bottom (`[0.1.3]: https://github.com/mariourquia/obsidian-connector/compare/v0.1.2...v0.1.3`)
- [ ] `README.md` updated if any user-facing behavior changed (new commands, new install steps, removed features)
- [ ] `TOOLS_CONTRACT.md` updated if MCP tool signatures or envelope schema changed
- [ ] No `TODO`, `FIXME`, or `HACK` comments related to release-blocking items

---

## 2. Release Process

### 2a. Merge to main

Do not commit directly to `main`. Use a pull request.

```bash
# Push branch if not already pushed
git push -u origin feature/uninstaller

# Open PR
gh pr create \
  --base main \
  --head feature/uninstaller \
  --title "v0.1.3: Safe uninstaller" \
  --body "Adds two-mode uninstaller (CLI + MCP tool) with 52 tests. See CHANGELOG.md for details."
```

- [ ] PR opened: `feature/uninstaller` -> `main`
- [ ] CI passes (lint, test matrix Python 3.11-3.13, MCP launch smoke)
- [ ] PR reviewed and approved
- [ ] PR merged via GitHub UI (squash or merge commit, per preference)

### 2b. Tag the release

After merge, pull `main` and create a signed tag.

```bash
git checkout main
git pull origin main
git tag -s v0.1.3 -m "v0.1.3: Safe uninstaller"
git push origin v0.1.3
```

- [ ] Tag `v0.1.3` created (GPG-signed via 1Password SSH / `op-ssh-sign`)
- [ ] Tag pushed to origin

### 2c. Build artifacts

```bash
# Clean previous builds
rm -rf dist/

# Build sdist and wheel
python3 -m build
```

- [ ] `dist/obsidian_connector-0.1.3.tar.gz` exists (sdist)
- [ ] `dist/obsidian_connector-0.1.3-py3-none-any.whl` exists (wheel)

### 2d. Generate checksums

```bash
cd dist
shasum -a 256 obsidian_connector-0.1.3.tar.gz > obsidian_connector-0.1.3.tar.gz.sha256
shasum -a 256 obsidian_connector-0.1.3-py3-none-any.whl > obsidian_connector-0.1.3-py3-none-any.whl.sha256
cd ..
```

- [ ] SHA-256 checksum files generated for each artifact

### 2e. Create GitHub Release

```bash
gh release create v0.1.3 \
  --title "v0.1.3: Safe uninstaller" \
  --notes-file docs/generated/RELEASE_NOTES_v0.1.3.md \
  dist/obsidian_connector-0.1.3.tar.gz \
  dist/obsidian_connector-0.1.3-py3-none-any.whl \
  dist/obsidian_connector-0.1.3.tar.gz.sha256 \
  dist/obsidian_connector-0.1.3-py3-none-any.whl.sha256
```

- [ ] GitHub Release created with tag `v0.1.3`
- [ ] Release notes attached (from `docs/generated/RELEASE_NOTES_v0.1.3.md`)
- [ ] sdist, wheel, and sha256 checksum files attached as release assets

---

## 3. Post-Release

- [ ] GitHub Release page renders correctly: https://github.com/mariourquia/obsidian-connector/releases/tag/v0.1.3
- [ ] Compare link in `CHANGELOG.md` resolves: https://github.com/mariourquia/obsidian-connector/compare/v0.1.2...v0.1.3
- [ ] `ROADMAP.md` Completed section includes v0.1.3 items
- [ ] Delete the `feature/uninstaller` branch after merge:
  ```bash
  git branch -d feature/uninstaller
  git push origin --delete feature/uninstaller
  ```
- [ ] Announce release (if applicable): GitHub Discussions, README badge update, etc.

---

## 4. Future: PyPI Publication

> Not yet active. Tracked as Roadmap item #18.

When PyPI publication is enabled, add these steps after 2e:

```bash
# Upload to TestPyPI first
python3 -m twine upload --repository testpypi dist/*

# Verify install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ obsidian-connector==0.1.3

# Upload to PyPI
python3 -m twine upload dist/*

# Verify install from PyPI
pip install obsidian-connector==0.1.3
```

Prerequisites before enabling:
- [ ] PyPI account created and API token stored securely
- [ ] `twine` added to dev dependencies
- [ ] `python3 -m build` added to CI for artifact validation
- [ ] TestPyPI dry run completed successfully at least once
- [ ] `pyproject.toml` classifiers and metadata reviewed for PyPI listing
