---
title: Windows platform notes
status: verified
owner: mariourquia
last_reviewed: 2026-04-16
---

# Windows platform notes

Issues and workarounds specific to running `obsidian-connector` on Windows.

## MCP log path: colons in timestamps

**Symptom:** Claude Desktop's MCP server log, written under
`%APPDATA%\Claude\logs\mcp-<id>.log` (path varies by Claude version),
occasionally fails to open because the filename contains `:` separators
from an ISO timestamp. Windows NTFS rejects `<>:"/\|?*` in filenames.

**Root cause:** This is an upstream bug in the Claude Desktop /
Claude Code runtime, not in `obsidian-connector`. Our own code emits
only date-shaped filenames (`YYYY-MM-DD.jsonl`) via
`obsidian_connector/audit.py` and `obsidian_connector/telemetry.py`.

**Workaround:** Update Claude Desktop to the latest version. Recent
builds sanitize MCP server log filenames. If you still hit this on an
older build, delete the stray log file and restart Claude Desktop.

**If you notice it in our code:** `obsidian_connector.platform.safe_filename_fragment(value)`
is the canonical NTFS-safe scrubber. Any new filename fragment that
includes a user-controlled or timestamp-like string should route through
it. Example:

```python
from datetime import datetime, timezone
from obsidian_connector.platform import safe_filename_fragment

ts = datetime.now(timezone.utc).isoformat()   # "2026-04-16T19:30:00+00:00"
fname = f"log-{safe_filename_fragment(ts)}.jsonl"
# fname == "log-2026-04-16T19-30-00+00-00.jsonl"
```

## Microsoft Store Python stub

**Symptom:** Running `python --version` on a fresh Windows install prints
nothing, or opens the Microsoft Store instead of launching the interpreter.
`obsx doctor` surfaces this explicitly:

```
python_runtime  FAIL  Python 3.12.0 (Microsoft Store stub detected)
  action: The Microsoft Store python.exe is a redirector stub, not a real
  interpreter. Install Python 3.11+ from https://python.org or via winget:
  `winget install Python.Python.3.12`.
```

**Fix:** Install Python from
[python.org](https://www.python.org/downloads/windows/) or via
`winget install Python.Python.3.12`. Make sure to check "Add Python to
PATH" during installation. After that:

```powershell
python --version   # should print something like "Python 3.12.x"
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## Plugin not showing up in Claude Desktop after install

**Symptom:** Install.ps1 finished cleanly, but Claude Desktop's
hammer icon does not show the `obsidian_*` tools.

**Checks:**

1. Restart Claude Desktop. The MCP server list is read on startup.
2. Verify the config file was written:
   ```powershell
   cat "$env:APPDATA\Claude\claude_desktop_config.json"
   ```
   The `mcpServers.obsidian-connector` entry should exist. If the file
   has a UTF-8 BOM, open it in an editor that preserves encoding (VS Code)
   and save as "UTF-8 (without BOM)". Claude Desktop and our
   `Install.ps1` both handle BOM via `utf-8-sig`, but some third-party
   tools round-trip it badly.
3. Run `obsx doctor` and look for `claude_config: FAIL` or
   `python_runtime: FAIL`.
4. Confirm Windows Defender or Controlled Folder Access isn't blocking
   the plugin directory at `%USERPROFILE%\.claude\plugins\...`.

## venv creation failures

**Symptom:** `python -m venv .venv` fails with
`PermissionError: [WinError 5]` or `subprocess.CalledProcessError`.

**Causes + fixes:**

- **Long path limit:** Windows filesystem APIs cap at 260 chars unless
  long paths are enabled. If the repo is checked out deep under
  `C:\Users\<long name>\Documents\GitHub\...`, move it to `C:\dev\` or
  enable long paths:
  ```powershell
  reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" `
    /v LongPathsEnabled /t REG_DWORD /d 1 /f
  ```
  Reboot after setting.
- **Antivirus blocking:** Windows Defender real-time scanning sometimes
  blocks the `ensurepip` step. Add the repo directory to exclusions.
- **Python Store stub:** see above.

## Obsidian CLI on Windows

Obsidian on Windows does not ship a CLI binary. The connector falls
back to the file-reading mode automatically (`client_fallback.py`) for
read operations. CLI-dependent write operations surface a clear error:

```
ObsidianNotFound: obsidian binary not found at 'Obsidian.exe'.
Hint: install Obsidian (https://obsidian.md) or set OBSIDIAN_BIN to the
absolute path of the `obsidian` CLI.
```

For the feature matrix, see `obsx doctor` -> `platform_features` row.
