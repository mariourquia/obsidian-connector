---
title: "Claude Desktop Debugging Guide"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-06"
review_cycle_days: 30
---

# Claude Desktop Debugging Guide

Troubleshooting guide for running obsidian-connector as an MCP server inside
Claude Desktop.

## Log locations

| Log file | Purpose |
|----------|---------|
| `~/Library/Logs/Claude/mcp-server-obsidian-connector.log` | Server-specific stdout/stderr from the MCP process |
| `~/Library/Logs/Claude/mcp.log` | General MCP lifecycle events (connect, disconnect, errors) |

Open both when diagnosing issues:

```bash
tail -f ~/Library/Logs/Claude/mcp-server-obsidian-connector.log
tail -f ~/Library/Logs/Claude/mcp.log
```

## Common failures

### "Operation not permitted"

**Cause:** macOS sandbox blocks shell scripts launched by Claude Desktop.

**Fix:** Point the Claude Desktop config at the venv Python binary directly
instead of a wrapper script:

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "/path/to/obsidian-connector/.venv/bin/python3",
      "args": ["-m", "obsidian_connector.mcp_server"]
    }
  }
}
```

Do not use `bash`, `sh`, or a shell wrapper as the command.

### "Server disconnected"

**Cause:** Either Obsidian is not running (the CLI communicates via IPC), or the
server crashed on startup (import error, missing dependency).

**Fix:**

1. Open the Obsidian desktop app.
2. Check the server log for a Python traceback:
   ```bash
   cat ~/Library/Logs/Claude/mcp-server-obsidian-connector.log
   ```
3. If the log shows an `ImportError`, reinstall the package:
   ```bash
   cd /path/to/obsidian-connector
   .venv/bin/pip install -e .
   ```

### "command not found" / ENOENT

**Cause:** The path in `claude_desktop_config.json` is wrong, or the virtualenv
was not created.

**Fix:**

1. Verify the venv exists:
   ```bash
   ls /path/to/obsidian-connector/.venv/bin/python3
   ```
2. If missing, create it:
   ```bash
   cd /path/to/obsidian-connector
   python3 -m venv .venv
   .venv/bin/pip install -e .
   ```
3. Update the config path to match the actual location.

### PATH mismatch

**Cause:** GUI apps (including Claude Desktop) do not inherit your shell PATH.
The `obsidian` binary may be on your shell PATH but invisible to Claude Desktop.

**Fix:**

1. Use an absolute path for `obsidian_bin` in your config:
   ```bash
   # Find the absolute path
   which obsidian
   ```
2. Set it in `~/.config/obsidian-connector/config.json`:
   ```json
   {
     "obsidian_bin": "/usr/local/bin/obsidian"
   }
   ```
   Or set the `OBSIDIAN_BIN` environment variable in the Claude Desktop config:
   ```json
   {
     "mcpServers": {
       "obsidian-connector": {
         "command": "/path/to/.venv/bin/python3",
         "args": ["-m", "obsidian_connector.mcp_server"],
         "env": {
           "OBSIDIAN_BIN": "/usr/local/bin/obsidian"
         }
       }
     }
   }
   ```

## How to reproduce manually

Test the exact command Claude Desktop would run:

```bash
# Start the server in stdio mode (same as Claude Desktop launches it)
/path/to/obsidian-connector/.venv/bin/python3 -m obsidian_connector.mcp_server

# Or run the automated smoke test that sends JSON-RPC via stdin
bash scripts/mcp_launch_smoke.sh
```

The smoke test sends `initialize`, `notifications/initialized`, and
`tools/list` over stdin and validates the responses.

## How to verify tools are registered

Run the doctor command with JSON output:

```bash
./bin/obsx --json doctor
```

This checks:
- `obsidian_binary` -- is the `obsidian` CLI on PATH?
- `obsidian_version` -- can we query the running Obsidian instance?
- `vault_resolution` -- is a default vault configured?
- `vault_reachable` -- can we list files in the vault via IPC?

Each failed check includes an `action` field with a specific remediation step.
