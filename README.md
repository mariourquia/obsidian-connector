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
| `obsidian_doctor` | Health check on CLI connectivity |

### Important

Obsidian must be running for the tools to work. The connector communicates
with the Obsidian desktop app via IPC -- if Obsidian is closed, all tools
will return an error.

---

## CLI usage

After installation, the CLI is available as `obsx` (or `obsidian-connector`):

```bash
# Search across the vault
obsx search "quarterly review"

# Read a specific note
obsx read "Project Alpha"

# Append to today's daily note
obsx log-daily "Meeting notes: discussed Q3 roadmap"

# List incomplete tasks
obsx tasks --status todo

# Log a structured decision
obsx log-decision \
  --project "AMOS" \
  --summary "Switched from REST to event-driven ingestion" \
  --details "Reduces latency on deal updates from 2s to 200ms."

# Find prior work on a topic
obsx find-prior-work "machine learning" --top-n 3

# Health check
obsx doctor

# JSON output (global flag, before subcommand)
obsx --json search "OKRs"
obsx --json doctor

# Dry-run (preview without writing)
obsx log-daily "test" --dry-run
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

## License

MIT
