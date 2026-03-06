# obsidian-connector

Python wrapper for the [Obsidian](https://obsidian.md) CLI.
Read, search, and manage your vault from scripts and automation.

## Requirements

- Python 3.11+
- Obsidian desktop app with CLI enabled (v1.12+)
- macOS (Linux/Windows support planned)

## Installation

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
pip install -e .
```

After installation, the CLI is available as both `obsidian-connector` and `obsx`.

## Quick start

### CLI

```bash
# Append to today's daily note
obsidian-connector log-daily "Meeting notes: discussed Q3 roadmap"

# Search across the vault (human-readable)
obsidian-connector search "quarterly review"

# Search with JSON output for scripting
obsidian-connector search "quarterly review" --json

# Read a specific note by name or path
obsidian-connector read "Project Alpha"
obsidian-connector read "Cards/Project Alpha.md"

# List incomplete tasks
obsidian-connector tasks --status todo

# List tasks as JSON, limited to 10
obsidian-connector tasks --status todo --limit 10 --json

# Log a structured decision record to the daily note
obsidian-connector log-decision \
  --project "AMOS" \
  --summary "Switched from REST to event-driven ingestion" \
  --details "Reduces latency on deal updates from 2s to 200ms."

# Create a new note from a template
obsidian-connector create-research-note \
  --title "CMBS Spread Analysis" \
  --template "Template, Note"

# Find prior work on a topic (top 3 hits with excerpts)
obsidian-connector find-prior-work "machine learning" --top-n 3

# Run health checks
obsidian-connector doctor

# Dry-run: see what would happen without mutating
obsidian-connector log-daily "test" --dry-run

# Canonical JSON envelope for any command (global flag)
obsidian-connector --json search "OKRs"
obsidian-connector --json doctor

# Search with context and deduplication
obsidian-connector search "quarterly" --max-results 5 --context-lines 2 --dedupe
```

All commands accept `--vault <name>` and `--json` as global flags:

```bash
obsidian-connector --vault "Work" --json search "OKRs"
```

### Python API

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

The connector resolves which vault to target using this priority (highest wins):

1. **Explicit argument** -- `search_notes("query", vault="Work")` or `--vault Work`
2. **Environment variable** -- `export OBSIDIAN_VAULT="Work"`
3. **config.json** -- `default_vault` field in `config.json` at the project root
4. **None** -- omit `vault=` from the CLI call (Obsidian uses the active vault)

### config.json

Place a `config.json` in the project root (or CWD when running):

```json
{
  "default_vault": "Obsidian Vault",
  "daily_note_behavior": "append",
  "default_folders": {
    "inbox": "Inbox",
    "projects": "Projects",
    "archive": "Archive"
  }
}
```

### Example: targeting a specific vault

```bash
# Via CLI flag
obsidian-connector --vault "Work" search "meeting notes"

# Via env var
OBSIDIAN_VAULT="Work" obsidian-connector tasks --todo

# Via Python API
from obsidian_connector import search_notes
search_notes("meeting notes", vault="Work")
```

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
