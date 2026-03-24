---
name: sync-vault
description: Sync project state to the Obsidian vault, write session logs with structured tags, and update the running TODO list. Run at end of sessions to capture where you left off.
---

# Sync Vault

Sync all tracked git repositories into the Obsidian vault, then write a
conversation-aware session log with structured tags for time-series analysis.

## Steps

### 1. Run the project sync

Call `obsidian_sync_projects` to sync git state for all tracked projects.

This generates:
- Per-project Markdown files with branch, commits, modified files
- A Dashboard with project table and quick links
- Active Threads showing repos with uncommitted work
- Running TODO aggregated from all vault `- [ ]` items

### 2. Identify projects touched in this session

Look at the conversation context to determine which projects were worked on.
For each project, classify the work type using one or more of these tags:
- `feature-dev` -- new features or capabilities
- `bugfix` -- bug fixes
- `refactor` -- code restructuring
- `research` -- exploration, reading, analysis
- `ops` -- infrastructure, CI/CD, deployment
- `docs` -- documentation
- `testing` -- tests
- `review` -- code review
- `planning` -- design, architecture, specs
- `setup` -- initial setup, configuration

### 3. Write the session log

Call `obsidian_log_session` with:
- **projects**: pipe-separated list of projects worked on
- **work_types**: pipe-separated work type tags
- **completed**: pipe-separated list of what was accomplished
- **next_steps**: pipe-separated list of what to pick up next
- **decisions**: pipe-separated list of decisions made or open questions
- **session_context**: free-text summary that a future conversation can
  use to immediately understand where to pick up

Example:
```
obsidian_log_session(
  projects="obsidian-connector|site",
  work_types="feature-dev|integration",
  completed="Built project sync module|Added 6 MCP tools|Created vault init wizard",
  next_steps="Write tests|Update TOOLS_CONTRACT|Publish to marketplace",
  decisions="Used Python subprocess instead of bash for cross-platform support",
  session_context="Integrated the sync-vault functionality into the obsidian-connector plugin..."
)
```

### 4. Check the Running TODO

Call `obsidian_running_todo` to surface the current open items.

Report the `total_open` count and mention any items in the
`recent_completed` field so the user knows the list is being maintained.

If the tool returns an error (e.g., vault not found), tell the user
and suggest running `/init-vault` first.

### 5. Report

Tell the user:
- How many projects were synced
- How many active threads detected
- What was logged to the session file
- Running TODO item count (open vs completed)
- Remind them that session logs have structured tags for Obsidian Bases queries

## When to use

- End of any work session
- After completing a significant piece of work
- Before switching to a different project
- When the user says "sync", "save state", "where did I leave off"
