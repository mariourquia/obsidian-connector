# Safe Installation Guide: obsidian-connector 0.9.0

## Before You Install

1. **Read the source.** The full source code is available at
   https://github.com/mariourquia/obsidian-connector. Review the code before
   installing, especially if you plan to connect it to a vault containing
   sensitive notes. This project:
   - Reads and writes files under your configured vault root.
   - Executes your Obsidian binary via `subprocess` when MCP tools invoke the
     desktop app (`obsidian_bin` config is validated against shell metachars).
   - Does not make outbound network calls in the base install.
   - Opens a local MCP server over stdio for the client (Claude Desktop,
     Claude Code, or MCPB host) to connect to.

2. **Check the version.** Confirm you are installing 0.9.0:
   ```bash
   git log --oneline v0.9.0 -1
   # Expected commit: 099af67101645faea8ad8b48a00f8c39e387ba1c
   ```

3. **Verify the tag signature.** All release-branch commits and the `v0.9.0`
   tag are signed with GPG ED25519 fingerprint
   `SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4`:
   ```bash
   git verify-tag v0.9.0
   ```

4. **Inspect dependencies.** Before installing, review what will be pulled in:
   ```bash
   pip download obsidian-connector==0.9.0 --no-deps -d /tmp/inspect
   # or, for the full transitive tree:
   pip download obsidian-connector==0.9.0 -d /tmp/inspect-full
   ls /tmp/inspect-full
   ```
   Cross-check against `requirements-lock.txt` at the `v0.9.0` tag.

## Install

### pip (base install)

```bash
pip install obsidian-connector==0.9.0
```

Base install pulls `mcp>=1.0.0,<2.0.0` and `pyyaml>=6.0.0` plus the `mcp`
transitive tree (anyio, httpx, pydantic, starlette, uvicorn, etc.; see
`SBOM.md`).

### pip with optional extras

```bash
# Textual TUI dashboard (new in 0.9.0)
pip install 'obsidian-connector[tui]==0.9.0'

# Knowledge-graph builder (new in 0.9.0)
pip install 'obsidian-connector[graphify]==0.9.0'

# Filesystem watcher
pip install 'obsidian-connector[live]==0.9.0'

# Embedding-backed retrieval
pip install 'obsidian-connector[semantic]==0.9.0'

# All optional runtime extras at once
pip install 'obsidian-connector[tui,graphify,live,semantic,scheduling]==0.9.0'
```

### macOS DMG

Download `obsidian-connector-0.9.0.dmg` from the GitHub Release page, verify
the checksum, then double-click to mount and run `Install.command`. The DMG
bootstrap creates a `.venv` and installs the package inside it.

### Windows MSI

Download `obsidian-connector-0.9.0.msi` from the GitHub Release page and run
the installer. `installer-smoke.yml` runs a subset of smoke tests on every
installer-touching PR, but the click-through install flow is not fully
automated; manual verification is recommended.

### MCPB

Use your MCPB-compatible host's install command against the `v0.9.0` MCPB
archive. The `mcpb.json` manifest ships with `version: "0.9.0"` and
`tools_count: 62`.

### Claude Code plugin

The `builds/claude-code/plugin.json` was synced to `0.9.0` in commit 3fd3d9a.
Install via your Claude Code plugin marketplace once the release is published,
or side-load from a local clone of the repo at the `v0.9.0` tag.

## Verify Installation

```bash
obsx --version
# Expected: 0.9.0

obsidian-connector --version
# Same; both entrypoints resolve to obsidian_connector.cli:main.
```

## Verify Integrity

```bash
# Download the checksum file
curl -LO https://github.com/mariourquia/obsidian-connector/releases/download/v0.9.0/SHA256SUMS.txt

# Verify
sha256sum -c SHA256SUMS.txt
```

If a signed checksum file is attached:

```bash
curl -LO https://github.com/mariourquia/obsidian-connector/releases/download/v0.9.0/SHA256SUMS.txt.asc
gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt
```

## Test Before Trusting

Run the project's test suite locally at the release tag:

```bash
git clone https://github.com/mariourquia/obsidian-connector
cd obsidian-connector
git checkout v0.9.0
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
.venv/bin/python -m pytest -q
# Expected: 137 passed
```

Smoke-test the `smart_triage` consumer contract:

```bash
.venv/bin/python -c "from obsidian_connector.smart_triage import smart_triage, ClassificationResult, LLMClient, Kind, Source; from obsidian_connector.classifiers.rule_based import RuleBasedClassifier; print('ok')"
```

Try in an isolated environment first:

```bash
python3.11 -m venv /tmp/test-env
source /tmp/test-env/bin/activate
pip install obsidian-connector==0.9.0
obsx --version
deactivate
rm -rf /tmp/test-env
```

## Uninstall

```bash
pip uninstall obsidian-connector
```

See `ROLLBACK_OR_UNINSTALL.md` for full rollback and cleanup steps across all
install surfaces (pip, DMG, MSI, MCPB, Claude Code plugin).
