---
title: "Trust and Provenance: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Trust & Provenance: obsidian-connector v0.2.0

## Source of Truth

- Repository: https://github.com/mariourquia/obsidian-connector
- Release tag: v0.2.0
- Branch: `feature/uninstaller` -> `main` (PR #13)
- Tag signature: unsigned (git tag not GPG-signed)
- Artifact signing: Sigstore cosign keyless (OIDC via GitHub Actions `id-token: write`)

## Build Provenance

- Built by: GitHub Actions (`.github/workflows/release.yml`)
- Build trigger: `git push origin v0.2.0` (tag push)
- Build environment:
  - Source archives: ubuntu-latest, Python 3.11
  - macOS .dmg: macos-latest
- Build reproducibility: not independently verified. Source archives are `git archive` outputs and should be reproducible from the same commit.

## Artifact Inventory

12 release assets total (4 artifacts + 4 `.sig` signatures + 4 `.cert` certificates):

| Artifact                              | Format    | Platform | Built On      |
|---------------------------------------|-----------|----------|---------------|
| `obsidian-connector-v0.2.0.tar.gz`   | tar.gz    | All      | ubuntu-latest |
| `obsidian-connector-v0.2.0.zip`      | zip       | All      | ubuntu-latest |
| `obsidian-connector-v0.2.0.dmg`      | macOS DMG | macOS    | macos-latest  |
| `obsidian-connector-v0.2.0.sha256`   | checksums | All      | ubuntu-latest |
| `*.sig`                               | Sigstore signature | -- | ubuntu-latest |
| `*.cert`                              | Sigstore certificate | -- | ubuntu-latest |

SHA256 checksums are generated in the release workflow and attached to the GitHub Release. Each of the 4 primary artifacts is signed with Sigstore cosign (keyless OIDC), producing a `.sig` and `.cert` pair.

## Verification Commands

### SHA256 checksum verification

```bash
# Download checksums
curl -LO https://github.com/mariourquia/obsidian-connector/releases/download/v0.2.0/obsidian-connector-v0.2.0.sha256

# Verify downloaded artifacts
sha256sum -c obsidian-connector-v0.2.0.sha256
```

### Sigstore cosign signature verification

```bash
# Install cosign: https://docs.sigstore.dev/cosign/system_config/installation/

# Verify any artifact (example: tar.gz)
cosign verify-blob \
  --signature obsidian-connector-v0.2.0.tar.gz.sig \
  --certificate obsidian-connector-v0.2.0.tar.gz.cert \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp "github.com/mariourquia/obsidian-connector" \
  obsidian-connector-v0.2.0.tar.gz
```

Replace the filename to verify the `.zip`, `.dmg`, or `.sha256` file. Each artifact has a matching `.sig` + `.cert` pair.

### Git tag verification

```bash
git fetch --tags
git log --oneline v0.2.0 -1
```

## Dependency Inventory

Total dependencies: 1 direct (`mcp` 1.26.0), 21 transitive (pinned with SHA256 hashes in `requirements-lock.txt`)

### Direct

| Dependency | Version         | License | Purpose            |
|------------|-----------------|---------|--------------------|
| mcp        | >=1.0.0,<2.0.0 (locked at 1.26.0) | MIT     | MCP server protocol |

### Optional

| Dependency | Version       | License | Purpose                   | Install Extra  |
|------------|---------------|---------|---------------------------|----------------|
| pyyaml     | >=6.0,<7.0    | MIT     | Schedule config parsing   | `scheduling`   |

### Transitive (via mcp)

| Dependency          | Pinned At | License       |
|---------------------|-----------|---------------|
| anyio               | 4.12.1    | MIT           |
| httpx               | 0.28.1    | BSD           |
| httpx-sse           | 0.4.3     | MIT           |
| jsonschema          | 4.26.0    | MIT           |
| pydantic            | 2.12.5    | MIT           |
| pydantic-settings   | 2.13.1    | MIT           |
| PyJWT               | 2.12.1    | MIT           |
| python-multipart    | 0.0.22    | Apache-2.0    |
| sse-starlette       | 3.3.2     | BSD-3-Clause  |
| starlette           | 0.52.1    | BSD-3-Clause  |
| typing-inspection   | 0.4.2     | MIT           |
| typing_extensions   | 4.15.0    | PSF-2.0       |
| uvicorn             | 0.42.0    | BSD-3-Clause  |

Full SBOM: `SBOM.md` in repository root.

All licenses are permissive (MIT, BSD, Apache-2.0, PSF-2.0). No copyleft dependencies.

## Standard Library Only Modules

These modules have zero external dependencies:

- `client.py`, `graph.py`, `index_store.py`, `audit.py`, `config.py`
- `thinking.py`, `workflows.py`, `platform.py`, `file_backend.py`, `uninstall.py`

Only `mcp_server.py` imports the `mcp` package.

## Maintainer Identity

- Maintainer: Mario Urquia
- GitHub: [@mariourquia](https://github.com/mariourquia)
- Contact: 60152193+mariourquia@users.noreply.github.com
- GPG key: not published (git commits are SSH-signed via 1Password; release artifacts are Sigstore cosign-signed)

## How to Report Issues

- Security vulnerabilities: email 60152193+mariourquia@users.noreply.github.com (see `SECURITY.md`)
- Bugs: https://github.com/mariourquia/obsidian-connector/issues
- Questions: https://github.com/mariourquia/obsidian-connector/issues
