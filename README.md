# obsidian-connector

Give Claude (and other AI agents) full access to your [Obsidian](https://obsidian.md) vault --
search, read, write, analyze the graph, surface ideas, and manage your knowledge base.

27 MCP tools. 26 CLI commands. Full Python API. Runs 100% locally.

## Quick start

### Requirements

- [Obsidian](https://obsidian.md) desktop app (v1.12+) with CLI enabled
- Python 3.11+ ([download](https://www.python.org/downloads/))
- macOS (Linux/Windows support planned)

### Option A: Download and double-click (easiest)

1. Go to [Releases](https://github.com/mariourquia/obsidian-connector/releases)
   and download the `.dmg` file
2. Open the DMG
3. Double-click **`Install.command`**
4. Restart Claude Desktop

That's it. No terminal, no commands.

> If macOS says the file can't be opened: right-click `Install.command`,
> select **Open**, then click **Open** in the dialog.

### Option B: Download ZIP from GitHub

1. Click the green **Code** button on this page, then **Download ZIP**
2. Unzip the folder
3. Open the folder and double-click **`Install.command`**
4. Restart Claude Desktop

### Option C: Terminal (for developers)

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
./scripts/install.sh
```

The install script creates the Python environment, installs the package, and
configures Claude Desktop automatically. Restart Claude Desktop and the
Obsidian tools appear.

<details>
<summary>Manual setup (full control)</summary>

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Then add this to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Replace `/ABSOLUTE/PATH/TO/` with the actual clone path.

To target a specific vault, add an `env` key:

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "/ABSOLUTE/PATH/TO/obsidian-connector/.venv/bin/python3",
      "args": ["-m", "obsidian_connector.mcp_server"],
      "env": { "OBSIDIAN_VAULT": "My Vault Name" }
    }
  }
}
```

Restart Claude Desktop after saving.

</details>

## What you get: 27 tools for Claude

### Core vault operations

| Tool | What it does |
|---|---|
| `obsidian_search` | Full-text search across all notes |
| `obsidian_read` | Read a note by name or path |
| `obsidian_tasks` | List tasks (filter by status, path, limit) |
| `obsidian_log_daily` | Append text to today's daily note |
| `obsidian_log_decision` | Log a structured decision record |
| `obsidian_create_note` | Create a note from a template |
| `obsidian_doctor` | Health check on CLI connectivity |

### Research and discovery

| Tool | What it does |
|---|---|
| `obsidian_find_prior_work` | Search + summarize top N matching notes |
| `obsidian_challenge_belief` | Find counter-evidence to a belief in your vault |
| `obsidian_emerge_ideas` | Cluster related notes into idea groups |
| `obsidian_connect_domains` | Find connections between two domains |

### Graph intelligence

These tools read your vault's link structure directly -- backlinks, forward links,
tags, orphan notes, dead ends -- without relying on the Obsidian CLI.

| Tool | What it does |
|---|---|
| `obsidian_neighborhood` | Graph neighborhood: backlinks, forward links, shared tags, N-hop neighbors |
| `obsidian_vault_structure` | Vault topology: orphans, dead ends, unresolved links, tag cloud, most-connected |
| `obsidian_backlinks` | All notes linking to a given note, with context lines |
| `obsidian_rebuild_index` | Force-rebuild the vault graph index |

### Thinking tools

Deep analysis of your notes and writing patterns.

| Tool | What it does |
|---|---|
| `obsidian_ghost` | Analyze your writing voice from recent notes |
| `obsidian_drift` | Detect drift between stated intentions and actual behavior |
| `obsidian_trace` | Trace an idea's evolution across vault notes over time |
| `obsidian_ideas` | Surface latent ideas from vault graph structure (orphans, clusters) |

### Workflow OS

Daily workflow, open loop tracking, idea graduation, and delegation management.

| Tool | What it does |
|---|---|
| `obsidian_my_world` | Full vault snapshot: recent notes, tasks, open loops, context |
| `obsidian_today` | Today brief: daily note, tasks, open loops |
| `obsidian_close_day` | End-of-day reflection prompt |
| `obsidian_open_loops` | List open loops (`OL:` markers and `#openloop` tags) |
| `obsidian_graduate_candidates` | Scan daily notes for ideas worth promoting to standalone notes |
| `obsidian_graduate_execute` | Create an agent draft note from a graduated idea |
| `obsidian_delegations` | Scan for `@agent:`/`@claude:` delegation instructions |
| `obsidian_context_load` | Load full context bundle for agent session start |

### HTTP mode (alternative)

If you prefer running the server as a standalone HTTP endpoint:

```bash
cd obsidian-connector
source .venv/bin/activate
python3 -m obsidian_connector.mcp_server --http
# Server starts on http://127.0.0.1:8000/mcp
```

Then use `http://127.0.0.1:8000/mcp` in Claude Desktop's "Add custom connector" UI.
The `claude_desktop_config.json` approach (used by the installer) is recommended instead.

## CLI usage

26 commands available as `./bin/obsx` (works without venv activation) or `obsx`
(after `pip install -e .`).

```bash
# ── Core ──
./bin/obsx search "quarterly review"
./bin/obsx read "Project Alpha"
./bin/obsx tasks --status todo
./bin/obsx log-daily "Meeting notes: discussed Q3 roadmap"
./bin/obsx log-decision --project "AMOS" --summary "Switched to event-driven" --details "200ms latency."
./bin/obsx create-research-note --title "CMBS Analysis" --template "Template, Note"
./bin/obsx doctor

# ── Research ──
./bin/obsx find-prior-work "machine learning" --top-n 3
./bin/obsx challenge "note-taking improves memory"
./bin/obsx emerge "project"
./bin/obsx connect "real estate" "machine learning"

# ── Graph ──
./bin/obsx neighborhood "Home" --depth 2
./bin/obsx vault-structure
./bin/obsx backlinks "Project Alpha"
./bin/obsx rebuild-index

# ── Thinking ──
./bin/obsx ghost --lookback-days 14
./bin/obsx drift --intention "write daily" --lookback-days 30
./bin/obsx trace "factor model"
./bin/obsx ideas

# ── Workflow ──
./bin/obsx my-world
./bin/obsx today
./bin/obsx close
./bin/obsx open-loops
./bin/obsx graduate list --lookback-days 7
./bin/obsx graduate execute --title "Factor Model" --content "Analysis of..." --confirm
./bin/obsx delegations --lookback-days 7
./bin/obsx context-load

# ── Global flags (before subcommand) ──
./bin/obsx --json search "OKRs"        # JSON envelope output
./bin/obsx --vault "Work" search "q3"  # target specific vault
./bin/obsx log-daily "test" --dry-run  # preview without writing
```

## Python API

```python
from obsidian_connector import (
    # Core
    search_notes, read_note, list_tasks, log_to_daily,
    log_decision, create_research_note, run_doctor,
    # Research
    find_prior_work, challenge_belief, emerge_ideas, connect_domains,
    # Graph
    build_note_index, load_or_build_index,
    # Thinking
    deep_ideas, drift_analysis, ghost_voice_profile, trace_idea,
    # Workflows
    today_brief, my_world_snapshot, close_day_reflection,
    list_open_loops, graduate_candidates, graduate_execute,
    detect_delegations, context_load_full,
)

# Search and read
results = search_notes("quarterly review")
content = read_note("Project Alpha")
tasks = list_tasks(filter={"todo": True, "limit": 10})

# Write
log_to_daily("Finished deploy at 14:32")
log_decision("AMOS", "Switched to event-driven", "Reduces latency to 200ms.")

# Graph
index = load_or_build_index()
if index:
    neighbors = index.neighborhood("Home.md", depth=2)
    orphans = index.orphans()

# Thinking
profile = ghost_voice_profile(lookback_days=14)
drift = drift_analysis(intention="write daily notes", lookback_days=30)

# Workflows
brief = today_brief()
candidates = graduate_candidates(lookback_days=7)
```

## Configuration

### Vault resolution (highest priority wins)

1. Explicit argument -- `search_notes("query", vault="Work")` or `--vault Work`
2. Environment variable -- `OBSIDIAN_VAULT_PATH` (directory) or `OBSIDIAN_VAULT` (name)
3. `config.json` -- `vault_path` or `default_vault` field
4. Obsidian's registered vaults -- auto-detected from `~/Library/Application Support/obsidian/obsidian.json`

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `OBSIDIAN_VAULT_PATH` | *(none)* | Direct path to vault directory |
| `OBSIDIAN_VAULT` | *(none)* | Vault name (matched against Obsidian's registry) |
| `OBSIDIAN_BIN` | `obsidian` | Path to the Obsidian binary |
| `OBSIDIAN_TIMEOUT` | `30` | CLI command timeout in seconds |
| `OBSIDIAN_CACHE_TTL` | `0` (off) | In-memory cache TTL for read-only commands |

## Safety

- **Dry-run mode**: All mutating commands support `--dry-run` to preview without writing.
- **Audit log**: Every mutation is logged to `~/.obsidian-connector/logs/YYYY-MM-DD.jsonl`.
- **Agent drafts**: `graduate_execute` writes to `Inbox/Agent Drafts/` with provenance frontmatter (`source: agent`, `status: draft`). Agents read, humans approve.
- **Path traversal protection**: Direct vault reads validate paths stay within the vault root.
- **No network calls**: Everything runs locally via IPC. No telemetry, no analytics.

See [PRIVACY.md](PRIVACY.md) for the full privacy policy.

## Troubleshooting

**Obsidian must be running.** The connector communicates with the Obsidian app via IPC.
If Obsidian is closed, all CLI-based tools return an `ObsidianNotRunning` error.
(Graph tools like `neighborhood`, `vault-structure`, and `backlinks` read files directly
and work without Obsidian running.)

**"Operation not permitted" on macOS.** The installer points Claude Desktop directly at
the venv's `python3` binary, which avoids macOS sandbox restrictions on shell scripts.
If you previously used `bin/obsx-mcp` as the command, re-run `./scripts/install.sh` to
update the config.

**Verify connectivity:**

```bash
./bin/obsx doctor
```

## AI agent integration

See [TOOLS_CONTRACT.md](TOOLS_CONTRACT.md) for the canonical JSON envelope schema,
typed error hierarchy, and full command reference.

## License

MIT
