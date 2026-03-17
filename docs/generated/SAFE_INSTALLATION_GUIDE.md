---
title: "Safe Installation Guide: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Safe Installation Guide

This guide covers installing obsidian-connector from scratch, verifying each step, and troubleshooting common problems. All three installation methods are documented with security notes explaining what each step does and why.

## 1. Prerequisites checklist

Complete every item before starting installation.

### macOS, Linux, or Windows

All three platforms are supported as of v0.2.0.

### Python 3.11+

```bash
python3 --version
```

Expected output: `Python 3.11.x` or higher (3.12, 3.13 all work). Python 3.14 is not tested.

If Python is missing or too old, download from <https://www.python.org/downloads/>. The installer adds `python3` to your PATH automatically. After installing, close and reopen your terminal, then re-run the version check.

### Obsidian desktop app (v1.4+) with CLI plugin

1. Confirm Obsidian is installed and running.
2. Verify the CLI is available:

```bash
obsidian version
```

Expected output: a version string like `1.4.0` or higher.

If the `obsidian` command is not found, open Obsidian, go to **Settings > General**, and enable **"Allow CLI commands"** (available in v1.4+). You may need to restart your terminal after enabling it.

### Git (for Option C only)

```bash
git --version
```

Any recent version works. Git ships with Xcode Command Line Tools on macOS:

```bash
xcode-select --install
```

### Claude Desktop (for MCP integration)

Download from <https://claude.ai/download> if not already installed.

---

## 2. Installation method comparison

| Criteria | Option A: DMG | Option B: ZIP | Option C: Terminal |
|---|---|---|---|
| Target audience | Non-technical users | Users without git | Developers |
| Terminal required | No | No (double-click) | Yes |
| Git required | No | No | Yes |
| Auto-updates | No (re-download) | No (re-download) | `git pull` |
| Claude Desktop config | Automatic | Automatic | Automatic (or manual) |
| Custom venv control | No | No | Yes |
| Editable install (`-e`) | No | No | Yes |
| Best for | Fastest first install | Quick install from browser | Full control, contributing |

All three methods run the same installer logic under the hood. Platform-specific installers:

- **macOS**: `scripts/install.sh` (or `Install.command` in DMG)
- **Linux**: `scripts/install-linux.sh` (creates venv, configures XDG Claude Desktop path, optionally installs systemd timers)
- **Windows**: `scripts/Install.ps1` (creates venv, configures `%APPDATA%\Claude\` path)

---

## 3. Step-by-step installation

### Option A: DMG download (easiest)

**Step 1.** Go to the [Releases page](https://github.com/mariourquia/obsidian-connector/releases) and download the latest `.dmg` file.

**Step 2.** Open the DMG. Double-click `Install.command`.

If macOS blocks it with "cannot be opened because it is from an unidentified developer":
- Right-click `Install.command` and select **Open**.
- Click **Open** in the confirmation dialog.
- This only needs to be done once.

**Step 3.** The installer prints progress to a terminal window. Watch for:
- `[1/4] Checking Python...` -- confirms Python 3.11+ is found
- `[2/4] Setting up Python environment...` -- creates `.venv` and installs the package
- `[3/4] Configuring Claude Desktop...` -- writes MCP config
- `[4/4] Verifying installation...` -- imports the package

**Step 4.** Verify the script completed with `Installation complete!` and no red ERROR lines.

**Step 5.** Restart Claude Desktop. The Obsidian tools should now appear.

### Option B: ZIP download

**Step 1.** On the [repository page](https://github.com/mariourquia/obsidian-connector), click the green **Code** button, then **Download ZIP**.

**Step 2.** Unzip the downloaded file. Open the resulting folder.

**Step 3.** Double-click `Install.command`. Follow the same macOS Gatekeeper steps as Option A if the file is blocked.

**Step 4.** Verify the same four-step output as Option A above.

**Step 5.** Restart Claude Desktop.

### Option C: Terminal (for developers)

**Step 1.** Clone the repository.

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
```

Verify the clone:

```bash
ls pyproject.toml scripts/install.sh
```

Both files should be listed without errors.

**Step 2.** Run the installer.

```bash
./scripts/install.sh
```

The script does the following (see Section 7 for security details):
1. Finds the highest available Python 3.11+ on your system
2. Creates a `.venv` virtual environment in the repo directory
3. Installs `obsidian-connector` as an editable package into that venv
4. Writes the MCP server entry into Claude Desktop's config file
5. Verifies the package imports correctly

**Step 3.** Verify each component:

```bash
# Confirm the venv exists
ls .venv/bin/python3

# Confirm the package is installed
.venv/bin/python3 -c "import obsidian_connector; print('OK')"

# Confirm the CLI works
./bin/obsx --help
```

**Step 4.** Restart Claude Desktop.

#### Manual setup (alternative to install.sh)

If you prefer full control over each step:

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package (editable mode)
pip install -e .

# Optional: install scheduling support
pip install -e ".[scheduling]"
```

Then manually add the MCP server entry to the Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json` (XDG)
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "/ABSOLUTE/PATH/TO/obsidian-connector/.venv/bin/python3",
      "args": ["-u", "-m", "obsidian_connector.mcp_server"],
      "cwd": "/ABSOLUTE/PATH/TO/obsidian-connector",
      "env": {
        "PYTHONPATH": "/ABSOLUTE/PATH/TO/obsidian-connector"
      }
    }
  }
}
```

Replace `/ABSOLUTE/PATH/TO/` with the actual path to your clone (e.g., `/Users/you/obsidian-connector`). Use the absolute path -- do not use `~` or `$HOME`.

If `claude_desktop_config.json` already exists with other MCP servers, add the `"obsidian-connector"` entry inside the existing `"mcpServers"` object. Do not overwrite the file.

Restart Claude Desktop after saving.

---

## 4. Post-install verification checklist

Run these checks after installation to confirm everything works.

### Health check

```bash
./bin/obsx doctor
```

Expected: all four checks pass (`obsidian_binary`, `obsidian_version`, `vault_resolution`, `vault_reachable`). Obsidian must be running for `vault_reachable` to pass.

### Package import

```bash
.venv/bin/python3 -c "from obsidian_connector import search_notes, read_note; print('imports OK')"
```

### CLI responds

```bash
./bin/obsx search "test"
```

Should return search results or an empty list (not a Python traceback).

### MCP server starts

```bash
.venv/bin/python3 -m obsidian_connector.mcp_server --help 2>&1 | head -5
```

Should print usage information, not an import error.

### Claude Desktop sees the tools

1. Open Claude Desktop.
2. Start a new conversation.
3. The Obsidian tools (e.g., `obsidian_search`, `obsidian_read`) should appear in the tool list. If they do not appear, check **Settings > MCP Servers** and confirm `obsidian-connector` is listed and not showing errors.

---

## 5. Common issues and fixes

### PYTHONPATH not set

**Symptom**: Claude Desktop shows `ModuleNotFoundError: No module named 'obsidian_connector'`.

**Cause**: The MCP server config is missing the `PYTHONPATH` environment variable, so the Python interpreter cannot find the package.

**Fix**: Ensure your `claude_desktop_config.json` includes the `env` block:

```json
"env": {
  "PYTHONPATH": "/ABSOLUTE/PATH/TO/obsidian-connector"
}
```

Alternatively, re-run `./scripts/install.sh`, which sets this automatically.

### macOS sandbox restrictions ("Operation not permitted")

**Symptom**: Claude Desktop logs show `Operation not permitted` when invoking Obsidian tools.

**Cause**: macOS sandboxes applications launched via shell scripts. The default sandbox policy may block file access needed by the Obsidian CLI.

**Fix**: The install script configures Claude Desktop to invoke the venv's `python3` binary directly (`command` points to `.venv/bin/python3`) rather than running a shell script. This sidesteps the sandbox restriction.

If you previously configured Claude Desktop with `bin/obsx-mcp` as the command, update the config or re-run `./scripts/install.sh` to apply the correct binary path.

### Obsidian not running

**Symptom**: `obsx doctor` shows `vault_reachable: FAIL` or tools return `ObsidianNotRunning` errors.

**Cause**: The Obsidian desktop app communicates with the CLI via IPC (inter-process communication). If Obsidian is not running, the CLI cannot reach any vault.

**Fix**: Open the Obsidian desktop app. It must be running whenever you use CLI-based tools. Graph tools (`neighborhood`, `vault-structure`, `backlinks`) read vault files directly and work without Obsidian running.

### `obsidian` command not found

**Symptom**: `obsx doctor` shows `obsidian_binary: FAIL`.

**Fix**:
1. Open Obsidian desktop app.
2. Go to **Settings > General** and enable CLI access (requires v1.4+).
3. Close and reopen your terminal.
4. Run `obsidian version` to confirm.

If the binary is installed at a non-standard path, set `OBSIDIAN_BIN`:

```bash
export OBSIDIAN_BIN="/path/to/obsidian"
```

Or add `"obsidian_bin": "/path/to/obsidian"` to `config.json` in the repo root.

### Python version too old

**Symptom**: Install script exits with `Python 3.11+ is required but not found`.

**Fix**: Install Python 3.11+ from <https://www.python.org/downloads/>. The installer searches for `python3.13`, `python3.12`, `python3.11`, and `python3` in order, picking the first one that meets the version requirement.

### Claude Desktop config parse error

**Symptom**: Claude Desktop fails to load MCP servers after install.

**Fix**: Validate the JSON (adjust path for your OS):

```bash
# macOS
python3 -c "import json; json.load(open('$HOME/Library/Application Support/Claude/claude_desktop_config.json'))"
# Linux
python3 -c "import json; json.load(open('$HOME/.config/Claude/claude_desktop_config.json'))"
# Windows (PowerShell)
python -c "import json; json.load(open(r'%APPDATA%\Claude\claude_desktop_config.json'))"
```

If this raises a `JSONDecodeError`, the file has a syntax error (often a missing comma or trailing comma). Fix the JSON manually or delete the file and re-run the installer.

---

## 6. Security considerations

### What the install script does

The install script (`scripts/install.sh`) performs these actions:

1. **Scans for Python binaries** on your PATH. It does not download or install Python. It checks `python3.13`, `python3.12`, `python3.11`, and `python3` in that order, selecting the first that is version 3.11+.

2. **Creates a virtual environment** at `.venv/` inside the repo directory. This is an isolated Python environment that does not modify your system Python.

3. **Installs the package** using `pip install -e .` (editable mode). Dependencies are defined in `pyproject.toml` -- the only required dependency is `mcp>=1.0.0,<2.0.0` (the MCP protocol library).

4. **Reads and writes `claude_desktop_config.json`** at the platform-appropriate location (`~/Library/Application Support/Claude/` on macOS, `~/.config/Claude/` on Linux, `%APPDATA%\Claude\` on Windows). If the file exists, the script parses it as JSON, adds or updates the `obsidian-connector` entry under `mcpServers`, and writes it back. It does not delete other MCP server entries. If the file does not exist, it creates it with only the `obsidian-connector` entry.

5. **Verifies the install** by importing `obsidian_connector` in Python.

6. **Optionally installs skills, hooks, and scheduling** -- each behind a yes/no prompt. These write to `.claude/commands/`, `.claude/settings.json`, and `~/Library/LaunchAgents/` respectively.

### What permissions it needs

- **Read/write to the repo directory**: creating `.venv/`, installing packages, writing `.claude/` config files.
- **Read/write to Claude Desktop config directory**: `~/Library/Application Support/Claude/` (macOS), `~/.config/Claude/` (Linux), `%APPDATA%\Claude\` (Windows).
- **Read/write to scheduling directory**: `~/Library/LaunchAgents/` (macOS launchd), `~/.config/systemd/user/` (Linux systemd), or Task Scheduler (Windows). Only if you opt in to scheduled automation.
- **No network calls at runtime**: the connector runs entirely locally via IPC with Obsidian. The only network access is during `pip install`, which downloads the `mcp` package from PyPI.
- **No elevated privileges**: the script never uses `sudo`. If it asks for a password, something is wrong -- cancel and investigate.

### What to audit before running

If you want to inspect before trusting:

```bash
# Read the install script
cat scripts/install.sh

# Check what pip will install
cat pyproject.toml

# Review the single runtime dependency
pip show mcp
```

### Binary path sanitization

The `OBSIDIAN_BIN` configuration value is validated at runtime. Characters that could enable shell injection (`;|&\`$(){}!`) are rejected, and the value falls back to `obsidian`.

---

## 7. Updating an existing installation

### If installed via git clone (Option C)

```bash
cd /path/to/obsidian-connector
git pull
source .venv/bin/activate
pip install -e .
```

Then restart Claude Desktop to pick up any new or changed MCP tools.

If the update includes dependency changes, pip handles them automatically during `pip install -e .`.

### If installed via DMG or ZIP (Options A/B)

1. Download the latest release or ZIP.
2. Replace the existing folder with the new one (or unzip over it).
3. Re-run `Install.command` (or `scripts/install.sh`).
4. Restart Claude Desktop.

The installer is idempotent -- running it again on an existing installation updates the venv and config without duplicating entries.

### Verifying the update

```bash
# Check installed version
.venv/bin/python3 -c "import obsidian_connector; print(obsidian_connector.__version__)"

# Run health check
./bin/obsx doctor
```

---

## 8. Multi-vault configuration

### How vault resolution works

The connector resolves which vault to use in this priority order:

1. **Explicit argument** -- `search_notes("query", vault="Work")` or `./bin/obsx --vault Work search "query"`
2. **`OBSIDIAN_VAULT_PATH` environment variable** -- absolute path to the vault directory
3. **`OBSIDIAN_VAULT` environment variable** -- vault name (matched against Obsidian's registry)
4. **`config.json` fields** -- `vault_path` (directory) or `default_vault` (name)
5. **Obsidian's registered vaults** -- auto-detected from `~/Library/Application Support/obsidian/obsidian.json`; if no name matches, the first registered vault that exists on disk is used

### Setting a default vault

Create a `config.json` in the repo root:

```json
{
  "default_vault": "My Vault Name"
}
```

Or use the path directly:

```json
{
  "vault_path": "/Users/you/Documents/My Vault"
}
```

### Targeting a specific vault per command

CLI:

```bash
./bin/obsx --vault "Work" search "project status"
./bin/obsx --vault "Personal" today
```

Python API:

```python
from obsidian_connector import search_notes
results = search_notes("project status", vault="Work")
```

### Configuring Claude Desktop for a specific vault

Add the `OBSIDIAN_VAULT` environment variable to the MCP server config in your Claude Desktop config file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `~/.config/Claude/claude_desktop_config.json` on Linux, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "/path/to/obsidian-connector/.venv/bin/python3",
      "args": ["-u", "-m", "obsidian_connector.mcp_server"],
      "cwd": "/path/to/obsidian-connector",
      "env": {
        "PYTHONPATH": "/path/to/obsidian-connector",
        "OBSIDIAN_VAULT": "Work"
      }
    }
  }
}
```

### Running multiple MCP server instances (one per vault)

To give Claude Desktop access to multiple vaults simultaneously, register separate MCP server entries:

```json
{
  "mcpServers": {
    "obsidian-work": {
      "command": "/path/to/obsidian-connector/.venv/bin/python3",
      "args": ["-u", "-m", "obsidian_connector.mcp_server"],
      "cwd": "/path/to/obsidian-connector",
      "env": {
        "PYTHONPATH": "/path/to/obsidian-connector",
        "OBSIDIAN_VAULT": "Work"
      }
    },
    "obsidian-personal": {
      "command": "/path/to/obsidian-connector/.venv/bin/python3",
      "args": ["-u", "-m", "obsidian_connector.mcp_server"],
      "cwd": "/path/to/obsidian-connector",
      "env": {
        "PYTHONPATH": "/path/to/obsidian-connector",
        "OBSIDIAN_VAULT": "Personal"
      }
    }
  }
}
```

Each instance runs independently and targets one vault. Tool names will be prefixed by the server name in Claude Desktop.
