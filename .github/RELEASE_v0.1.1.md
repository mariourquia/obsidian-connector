```
 ___  _         _    _ _               ___
/ _ \| |__  ___(_) _| (_) __ _ _ __   / __\___  _ __  _ __   ___| |_ ___  _ __
| | | | '_ \/ __| |/ _` | |/ _` | '_ \ / /  / _ \| '_ \| '_ \ / _ \ __/ _ \| '__|
| |_| | |_) \__ \ | (_| | | (_| | | | / /__| (_) | | | | | | |  __/ || (_) | |
 \___/|_.__/|___/_|\__,_|_|\__,_|_| |_\____/\___/|_| |_|_| |_|\___|\__\___/|_|

                          v0.1.1 -- Release Hygiene
                    Turn Claude into your second brain.
```

## Highlights

- **CI pipeline**: Every PR now runs lint, tests (Python 3.11-3.13), and MCP
  launch smoke automatically via GitHub Actions.
- **Release automation**: Tagged releases build source archives with sha256
  checksums attached automatically.
- **SBOM and dependency audit**: Full software bill of materials with zero
  known vulnerabilities across 14 transitive dependencies.
- **Contributor onboarding**: CONTRIBUTING.md with dev workflow, testing guide,
  and tool addition checklist.

## What's New

### Added

| Feature | Description |
|---------|-------------|
| `.github/workflows/ci.yml` | CI pipeline: docs-lint, unit tests (3.11-3.13), MCP launch smoke |
| `.github/workflows/release.yml` | Automated source archives + sha256 checksums on tag push |
| `CONTRIBUTING.md` | Development workflow, testing guide, code style, tool checklist |
| `SECURITY.md` | Vulnerability reporting policy and security model |
| `SBOM.md` | Software bill of materials with license inventory |
| `pyyaml` optional dep | `pip install obsidian-connector[scheduling]` for schedule config |
| `__version__` | `obsidian_connector.__version__` for runtime version queries |

### No Breaking Changes

This is a hygiene release. No tool behavior, API, or CLI changes.

## Installation

```bash
# Fresh install
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
./scripts/install.sh

# Upgrade from v0.1.0
cd obsidian-connector
git pull origin main
./scripts/install.sh
```

## Dependency Audit

```
+-------------------------------+--------+
| Check                         | Status |
+-------------------------------+--------+
| pip-audit (known CVEs)        | 0      |
| Runtime dependencies          | 14     |
| All licenses OSI-approved     | YES    |
| Network-calling dependencies  | 0 used |
+-------------------------------+--------+
```

All 14 transitive dependencies are MIT, BSD, Apache-2.0, or PSF-2.0 licensed.
See `SBOM.md` for the full inventory.

## Verification

```bash
# Verify checksum (after downloading release assets)
sha256sum -c obsidian-connector-v0.1.1.sha256

# Run tests locally
source .venv/bin/activate
python3 scripts/cache_test.py
python3 scripts/audit_test.py
python3 scripts/graph_test.py

# Health check
./bin/obsx doctor
```

## Full Changelog

**Compare:** [`v0.1.0...v0.1.1`](https://github.com/mariourquia/obsidian-connector/compare/v0.1.0...v0.1.1)

---

```
+----------------------------------------------------------+
|                                                          |
|  Built with care in New York.                            |
|  100% local. Your vault never leaves your machine.       |
|                                                          |
|  github.com/mariourquia/obsidian-connector               |
|                                                          |
+----------------------------------------------------------+
```
