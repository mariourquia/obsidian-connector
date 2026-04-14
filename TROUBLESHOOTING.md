# Troubleshooting

Run `obsx doctor` first. It checks Python version, Obsidian binary, vault
connectivity, and MCP server health. Most issues show up in its output.

## Python 3.11+ not found

The connector requires Python 3.11 or newer.

**Windows**: The Microsoft Store Python stub intercepts `python3` and opens
the Store instead of running Python. Install Python from python.org or via
`winget install Python.Python.3.12`. After installing, verify with
`python3 --version` in a new terminal.

**macOS**: `brew install python@3.12` or download from python.org. The
system Python on older macOS versions is 3.9 and will not work.

**Linux**: `sudo apt install python3.12` (Debian/Ubuntu) or equivalent for
your distro.

## Obsidian CLI not on PATH

The connector calls the `obsidian` binary. It must be accessible from your
shell.

1. Open Obsidian > Settings > General > scroll to "CLI" section
2. Enable "Enable CLI" (or "Obsidian CLI" depending on version)
3. Close and reopen your terminal
4. Verify: `obsidian --version` should print a version number

If the binary exists but is not on PATH, the connector will try common
install locations automatically. Run `obsx doctor` to see which path it
resolves.

## MCP server not appearing in Claude Desktop

Check `~/Library/Application Support/Claude/claude_desktop_config.json` on
macOS or `%APPDATA%\Claude\claude_desktop_config.json` on Windows. It should
contain an `obsidian-connector` entry under `mcpServers`.

If the entry is missing, re-run `./scripts/install.sh` or add it manually
per the README. After editing the config, fully quit and relaunch Claude
Desktop (not just close the window).

Run `obsx doctor` to confirm the MCP server can start.

## venv activation failures

If the virtual environment is corrupted or was created with a different
Python version:

```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# or: .venv\Scripts\activate  # Windows
pip install -e '.[tui]'
```

Ensure the Python version used to create the venv matches 3.11+.
If you only need non-dashboard commands, `pip install -e .` is also valid.

## Dashboard commands require Textual

`obsx menu` and `obsx setup-wizard` use the optional Textual dashboard. If you
installed the base package only, those commands fail with a short install message.

To enable them:

```bash
pip install 'obsidian-connector[tui]'
# or from a local clone:
pip install -e '.[tui]'
```

Other CLI commands do not require Textual.

## iCloud vault path issues

On macOS, iCloud-synced vaults live under a long path with spaces:

```
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault-name>
```

When passing this path on the command line, wrap it in quotes:

```bash
obsx search "query" --vault "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/my-vault"
```

In `config.json` or environment variables, use the full expanded path (no
`~` shortcut). The connector handles tilde expansion internally, but some
shells do not expand `~` inside quotes.

## Permission errors on macOS

"Operation not permitted" usually means macOS sandboxing is blocking access.

1. System Settings > Privacy & Security > Full Disk Access
2. Add your terminal app (Terminal.app, iTerm2, etc.)
3. If running via Claude Desktop, add Claude Desktop to Full Disk Access
4. Restart the app after granting access

This is required for vaults stored outside your home directory or in
iCloud-synced locations.

## Build system issues

The build pipeline uses TypeScript tools in the `tools/` directory and
requires Node.js.

**`npx tsx` not found**: Install Node.js 18+ and run `npm ci` in the
`tools/` directory to install dependencies. Then run build commands from the
repo root:

```bash
cd tools && npm ci && cd ..
npx tsx tools/build.ts --target all
```

**Node.js version**: The build tools require Node.js 18 or newer. Check with
`node --version`.

**Validation failures**: Run `npx tsx tools/validate.ts --target all` after
building. If a target fails validation, check that source files in `src/`
have not been modified without rebuilding.

Run `npx tsx tools/doctor.ts` for a build environment health check.

## Still stuck

Open an issue at github.com/mariourquia/obsidian-connector/issues with:
- Output of `obsx doctor`
- Your OS and Python version
- The exact error message
