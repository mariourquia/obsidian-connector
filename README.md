# obsidian-connector

Give Claude (and other AI agents) access to your [Obsidian](https://obsidian.md) vault.
Search notes, read content, log decisions, and manage tasks -- all through an MCP server or CLI.

## Claude Desktop setup (MCP server)

### Requirements

- Python 3.11+
- Obsidian desktop app with CLI enabled (v1.12+)
- macOS (Linux/Windows support planned)

### 1. Clone and install

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure Claude Desktop

Add this to your `claude_desktop_config.json`:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "/ABSOLUTE/PATH/TO/obsidian-connector/.venv/bin/python3",
      "args": ["-m", "obsidian_connector.mcp_server"]
    }
  }
}
```

Replace `/ABSOLUTE/PATH/TO/` with your actual clone path (e.g. `/Users/you/Documents/GitHub/`).

To target a specific vault, add an `env` key:

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "/ABSOLUTE/PATH/TO/obsidian-connector/.venv/bin/python3",
      "args": ["-m", "obsidian_connector.mcp_server"],
      "env": {
        "OBSIDIAN_VAULT": "My Vault Name"
      }
    }
  }
}
```

### 3. Restart Claude Desktop

Quit and reopen Claude Desktop. The Obsidian tools will appear automatically.

### Available tools

| Tool | Description |
|---|---|
| `obsidian_search` | Full-text search across the vault |
| `obsidian_read` | Read a note by name or path |
| `obsidian_tasks` | List tasks (filterable by status, path, limit) |
| `obsidian_log_daily` | Append text to today's daily note |
| `obsidian_log_decision` | Log a structured decision record |
| `obsidian_find_prior_work` | Search + summarize top N matching notes |
| `obsidian_create_note` | Create a note from a template |
| `obsidian_my_world` | Full vault snapshot (recent notes, tasks, open loops) |
| `obsidian_today` | Today brief: daily note, tasks, open loops |
| `obsidian_close_day` | End-of-day reflection prompt (read-only) |
| `obsidian_open_loops` | List open loops (OL: markers and #openloop tags) |
| `obsidian_challenge_belief` | Search for counter-evidence to a belief |
| `obsidian_emerge_ideas` | Cluster related notes into idea groups |
| `obsidian_connect_domains` | Find connections between two domains |
| `obsidian_doctor` | Health check on CLI connectivity |

### Alternative: HTTP mode

If you prefer the "Add custom connector" UI in Claude Desktop (remote MCP), you
can run the server as an HTTP endpoint:

```bash
cd obsidian-connector
source .venv/bin/activate
python3 -m obsidian_connector.mcp_server --http
# Server starts on http://127.0.0.1:8000/mcp
```

Then enter `http://127.0.0.1:8000/mcp` in the custom connector URL field.
Note: this requires keeping the server process running manually. The
`claude_desktop_config.json` approach above is recommended instead.

### Troubleshooting

**Obsidian must be running.** The connector communicates with the Obsidian desktop
app via IPC. If Obsidian is closed, all tools return an `ObsidianNotRunning` error.

**"Operation not permitted" on macOS.** macOS sandboxing can block GUI apps from
executing shell scripts. The recommended config above points directly to the venv's
`python3` binary (not a shell wrapper), which avoids this. If you previously used
`bin/obsx-mcp` as the command, switch to the `.venv/bin/python3` approach shown above.

**Console script `obsx` doesn't work outside the venv.** Use `./bin/obsx` instead,
which works without venv activation. Or use `python3 main.py` from the repo root.

**Verify connectivity.** Run the health check:

```bash
./bin/obsx doctor
# or
python3 main.py doctor
```

---

## CLI usage

After installation, the CLI is available as `obsx` (or `obsidian-connector`).
From the repo directory, `./bin/obsx` works without venv activation:

```bash
# Search across the vault
./bin/obsx search "quarterly review"

# Read a specific note
./bin/obsx read "Project Alpha"

# Append to today's daily note
./bin/obsx log-daily "Meeting notes: discussed Q3 roadmap"

# List incomplete tasks
./bin/obsx tasks --status todo

# Log a structured decision
./bin/obsx log-decision \
  --project "AMOS" \
  --summary "Switched from REST to event-driven ingestion" \
  --details "Reduces latency on deal updates from 2s to 200ms."

# Find prior work on a topic
./bin/obsx find-prior-work "machine learning" --top-n 3

# Health check
./bin/obsx doctor

# JSON output (global flag, before subcommand)
./bin/obsx --json search "OKRs"
./bin/obsx --json doctor

# Dry-run (preview without writing)
./bin/obsx log-daily "test" --dry-run
```

All commands accept `--vault <name>` and `--json` as global flags.

## Python API

```python
from obsidian_connector import log_to_daily, search_notes, read_note, list_tasks
from obsidian_connector import log_decision, create_research_note, find_prior_work

# Core functions
log_to_daily("Finished deploy at 14:32")
results = search_notes("quarterly review")
content = read_note("Project Alpha")
tasks = list_tasks(filter={"todo": True, "limit": 10})

# Higher-level workflows
log_decision("AMOS", "Switched to event-driven", "Reduces latency to 200ms.")
path = create_research_note("CMBS Analysis", template="Template, Note")
prior = find_prior_work("machine learning", top_n=3)
```

## Vault configuration

The connector resolves which vault to target (highest priority wins):

1. **Explicit argument** -- `search_notes("query", vault="Work")` or `--vault Work`
2. **Environment variable** -- `export OBSIDIAN_VAULT="Work"`
3. **config.json** -- `default_vault` field in `config.json` at the project root
4. **None** -- omit `vault=` (Obsidian uses the active vault)

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `OBSIDIAN_BIN` | `obsidian` | Path to the Obsidian binary |
| `OBSIDIAN_VAULT` | *(none)* | Default vault name (overrides config.json) |
| `OBSIDIAN_TIMEOUT` | `30` | CLI command timeout in seconds |
| `OBSIDIAN_CACHE_TTL` | `0` (disabled) | In-memory cache TTL in seconds for read ops |

## Safety

Mutating commands (`log-daily`, `log-decision`, `create-research-note`)
support `--dry-run` to preview without writing. All mutating commands are
logged to `~/.obsidian-connector/logs/YYYY-MM-DD.jsonl` for auditability.

## AI agent integration

See [TOOLS_CONTRACT.md](TOOLS_CONTRACT.md) for the canonical JSON envelope
schema, typed error hierarchy, and agent-friendly command reference.

## Privacy

obsidian-connector runs entirely on your local machine. No telemetry, analytics, or external network calls. Vault access is via local IPC only. Mutations are logged to `~/.obsidian-connector/logs/` for auditability. See [PRIVACY.md](PRIVACY.md) for full details.

## Distribution

### Manual install (current)

Clone the repo, create a venv, `pip install -e .`, and configure `claude_desktop_config.json` as described in the setup section above.

### MCPB (future)

When the MCPB CLI becomes available, obsidian-connector will support one-click installation into Claude Desktop via a `.mcpb` package. The `mcpb.json` manifest is already prepared. See [docs/distribution/MCPB_RESEARCH.md](docs/distribution/MCPB_RESEARCH.md) for details.

### Anthropic MCP Directory (future)

obsidian-connector is being prepared for submission to the Anthropic MCP directory, which will make it discoverable and installable directly from Claude Desktop's UI. See [docs/distribution/DIRECTORY_CHECKLIST.md](docs/distribution/DIRECTORY_CHECKLIST.md) for submission status.

## License

MIT
