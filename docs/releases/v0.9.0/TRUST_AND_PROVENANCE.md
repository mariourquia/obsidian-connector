# Trust & Provenance: obsidian-connector 0.9.0

## Source of Truth

- Repository: https://github.com/mariourquia/obsidian-connector
- Release tag: `v0.9.0` (pending creation by coordinator; not yet present at
  the time this artifact was generated -- the preceding tag on the repo is
  `v0.8.3`)
- Commit: `099af67101645faea8ad8b48a00f8c39e387ba1c`
- Branch: `main` (at time of release)
- Tag signature: will be signed with GPG ED25519 key fingerprint
  `SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4`
- Commit signatures: all 23 release-branch commits in the `v0.8.3..HEAD`
  window are GPG-signed with the same ED25519 fingerprint. Verified via
  `git log --format='%G? %GK %s' v0.8.3..HEAD` returning `G
  SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4` on every line.

## Build Provenance

- Built by: GitHub Actions hosted runners
- Build workflows:
  - `.github/workflows/release.yml` -- release orchestrator
  - `.github/workflows/build-macos-dmg.yml` -- DMG build
  - `.github/workflows/build-windows-installer.yml` -- MSI build
  - `.github/workflows/installer-smoke.yml` -- post-install smoke checks
  - `.github/workflows/verify-release.yml` -- downloads draft assets, runs
    installers on platform-specific CI runners, promotes to live only on
    all-pass
  - `.github/workflows/ci.yml` -- test suite on ubuntu-latest +
    windows-latest + macos-latest
  - `.github/workflows/security.yml` -- `pip-audit` + gitleaks scanning
- Build environment:
  - OS: GitHub Actions hosted runners (macos-latest, ubuntu-latest,
    windows-latest)
  - Runtime: Python 3.11 / 3.12 / 3.13
  - Build tool: `hatchling` (declared in `pyproject.toml [build-system]`)
- Build reproducibility: not formally verified for this release. No SLSA
  attestation generated.

## Artifact Inventory

The following artifacts are expected on the GitHub Release after the
coordinator runs the release workflow. Checksums will be filled in after
build:

| Artifact                                         | SHA256                   | Size |
|--------------------------------------------------|--------------------------|------|
| `obsidian_connector-0.9.0-py3-none-any.whl`      | (filled in at build time) | -- |
| `obsidian_connector-0.9.0.tar.gz`                | (filled in at build time) | -- |
| `obsidian-connector-0.9.0.dmg`                   | (filled in at build time) | -- |
| `obsidian-connector-0.9.0.msi`                   | (filled in at build time) | -- |
| `obsidian-connector-0.9.0.mcpb`                  | (filled in at build time) | -- |
| `obsidian-connector-claude-code-0.9.0.zip`       | (filled in at build time) | -- |
| `SHA256SUMS.txt`                                 | --                       | -- |
| `SHA256SUMS.txt.asc` (GPG detached signature)    | --                       | -- |

After the release workflow completes, regenerate this table from:

```bash
sha256sum dist/* > SHA256SUMS.txt
gpg --armor --detach-sign SHA256SUMS.txt
```

## Verification Commands

```bash
# Verify tag signature
git verify-tag v0.9.0
# Expected output contains:
#   gpg: Good signature from "Mario Urquia ..."
#   Primary key fingerprint: ... SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4

# Verify commit signatures on the release-branch window
git log --format='%G? %GK %s' v0.8.3..v0.9.0
# Expected: every line begins with "G SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4"

# Verify artifact checksum
echo "<SHA256>  obsidian_connector-0.9.0-py3-none-any.whl" | sha256sum -c -

# Verify GPG signature on checksum file
gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt
```

## Dependency Inventory

Base runtime tree (from `pyproject.toml [project] dependencies` and
`requirements-lock.txt`):

| Dependency             | Version                 | License      | Maintainer                  |
|------------------------|-------------------------|--------------|-----------------------------|
| mcp                    | `>=1.0.0,<2.0.0`        | MIT          | Anthropic                   |
| pyyaml                 | `>=6.0.0`               | MIT          | Ingy dot Net et al.         |
| anyio                  | 4.12.1 (pinned)         | MIT          | Alex Gronholm               |
| httpx                  | 0.28.1 (pinned)         | BSD-3-Clause | Encode                      |
| httpx-sse              | 0.4.3 (pinned)          | MIT          | Florimond Manca             |
| jsonschema             | 4.26.0 (pinned)         | MIT          | Julian Berman               |
| pydantic               | 2.12.5 (pinned)         | MIT          | Samuel Colvin               |
| pydantic-settings      | 2.13.1 (pinned)         | MIT          | Samuel Colvin               |
| PyJWT                  | 2.12.1 (pinned)         | MIT          | José Padilla                |
| python-multipart       | 0.0.22 (pinned)         | Apache-2.0   | Andrew Dunham               |
| sse-starlette          | 3.3.2 (pinned)          | BSD-3-Clause | Sergey Smirnov              |
| starlette              | 0.52.1 (pinned)         | BSD-3-Clause | Encode                      |
| typing-inspection      | 0.4.2 (pinned)          | MIT          | Pydantic Services           |
| typing_extensions      | 4.15.0 (pinned)         | PSF-2.0      | Python core team            |
| uvicorn                | 0.42.0 (pinned)         | BSD-3-Clause | Encode                      |

Optional extras (top-level packages only):

| Extra       | Package                  | Version range   |
|-------------|--------------------------|-----------------|
| `scheduling`| pyyaml                   | `>=6.0,<7.0` (same as base) |
| `tui`       | textual                  | `>=1.0.0`       |
| `live`      | watchdog                 | `>=4.0,<5.0`    |
| `semantic`  | sentence-transformers    | `>=3.0,<4.0`    |
| `graphify`  | networkx                 | `>=3.0,<4.0`    |
| `dev`       | pytest                   | `>=8.0,<9.0`    |

## SBOM Guidance

The repo ships `SBOM.md` at the root. For 0.9.0 the header metadata is stale
(still stamped v0.2.0 / 2026-03-16); the table contents for the base runtime
tree remain accurate. Regenerate with:

```bash
source .venv/bin/activate
pip install pip-audit pip-licenses
pip-audit                                      # CVE scan
pip-licenses --format=markdown --with-urls     # license table
```

Consumers who need a CycloneDX or SPDX SBOM should generate one locally:

```bash
pip install cyclonedx-bom
cyclonedx-py environment -o obsidian-connector-0.9.0-sbom.json
```

No SLSA provenance statement is shipped for 0.9.0. Future releases may add
SLSA attestation via `actions/attest-build-provenance` in the release
workflow.

## Maintainer Identity

- Maintainer: Mario Urquia
- GitHub: [@mariourquia](https://github.com/mariourquia)
- GPG key: ED25519, fingerprint
  `SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4`
  (signing via 1Password SSH / `op-ssh-sign`)
- Contact: `60152193+mariourquia@users.noreply.github.com`

## How to Report Issues

- Security vulnerabilities: email
  `60152193+mariourquia@users.noreply.github.com`. Do not open a public
  GitHub issue for security problems. See `SECURITY.md`.
- Bugs: https://github.com/mariourquia/obsidian-connector/issues
- Questions: GitHub Discussions on the repo (if enabled) or the issue
  tracker as a `question` label.

## Release History Reference

Prior tags relevant to this release family:

- v0.7.0 (2026-04-02)
- v0.7.1 (2026-04-02)
- v0.8.0 through v0.8.3 (2026-04-02 through 2026-04-13)
- v0.9.0 (2026-04-13, this release)

All tags are GPG-signed under the same ED25519 fingerprint above.
