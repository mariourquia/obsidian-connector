# Privacy Policy

**obsidian-connector v0.8.1**
**Last updated:** 2026-04-02

## Runtime Operation (Local-Only)

obsidian-connector runs entirely on your local machine during normal operation. All communication with the Obsidian desktop app occurs via local IPC (inter-process communication). No vault contents, prompts, or AI responses are transmitted over a network.

## Session Telemetry (Local-Only)

The `telemetry.py` module tracks session-level usage metrics stored locally at `~/.config/obsidian-connector/telemetry/` in daily JSONL files. This data never leaves your machine.

**What is recorded locally:**

| Field | Purpose |
|-------|---------|
| notes_read | Counter of notes read in session |
| notes_written | Counter of notes written in session |
| tools_called | Tool names and invocation counts |
| retrieval_misses | Counter of failed retrievals |
| write_risk_events | Counter of risky write operations |
| errors | Counter of errors |
| session_start / session_end | ISO timestamps |

Files older than 30 days are auto-deleted on rotation. View stats via `obsx stats` or the `obsidian_session_stats` MCP tool.

## Installer Telemetry (Remote, Anonymous)

The macOS (`Install.command`) and Windows (`Install.ps1`) installers send a single anonymous telemetry event on installation success or failure. The Linux installer (`install.sh`) does not send telemetry.

**Endpoint:** `https://cre-skills-feedback-api.vercel.app/api/installer-telemetry`

**What is sent:**

| Field | Example | Purpose |
|-------|---------|---------|
| plugin_name | `obsidian-connector` | Identifies which plugin |
| plugin_version | `0.8.1` | Version being installed |
| installer_type | `command` / `ps1` | Installer variant |
| os / os_version / arch | `macos`, `15.3`, `arm64` | Platform info |
| status | `success` / `failure` | Outcome |
| python_version / python_source | `3.14.2`, `brew` | Python environment |
| claude_code_present | `true` / `false` | Whether Claude Code CLI is installed |
| claude_desktop_present | `true` / `false` | Whether Claude Desktop is installed |
| step_results | `{"python":"ok","venv":"ok",...}` | Per-step pass/fail |
| edge_cases | `spaces_in_home` | Edge cases detected |
| remediations | `brew_python_install` | Auto-fixes applied |
| total_duration_s | `12` | Installation duration |
| step_failed / error_message | Step name, truncated error | Failure diagnostics |
| install_id_hash | SHA-256 hash | Anonymous per-machine ID |

**What is NOT sent:** user name, email, IP address (not collected by the endpoint), vault contents, file paths, prompt content, or any personal data.

**Install ID:** A UUID stored at `~/.obsidian-connector-install-id` (macOS) or derived from machine+username hash (Windows). The raw ID is hashed before transmission.

**Behavior:** Telemetry runs in the background, never blocks installation, and fails silently (5-second timeout). There is currently no opt-out mechanism for installer telemetry.

## Mutation Logging

All mutating operations (appending to daily notes, logging decisions, creating notes) are logged locally to `~/.obsidian-connector/logs/` in JSONL format. These logs exist solely for your auditability and never leave the machine.

## No User Data Collection

obsidian-connector does not collect, store, or transmit any personal information, user identifiers, or behavioral data during runtime. There are no accounts, no sign-ups, and no authentication tokens sent to external services. The only external network call is the one-time installer telemetry event described above.

## Contact

For privacy questions: open an issue at https://github.com/mariourquia/obsidian-connector/issues.
