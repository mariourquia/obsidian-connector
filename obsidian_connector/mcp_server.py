"""MCP server exposing obsidian-connector tools for Claude Desktop."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from obsidian_connector.client import (
    ObsidianCLIError,
    list_tasks,
    log_to_daily,
    read_note,
    search_notes,
)
from obsidian_connector.doctor import run_doctor
from obsidian_connector.errors import (
    CommandTimeout,
    MalformedCLIOutput,
    ObsidianNotFound,
    ObsidianNotRunning,
    VaultNotFound,
)
from obsidian_connector.workflows import (
    challenge_belief,
    close_day_reflection,
    connect_domains,
    create_research_note,
    emerge_ideas,
    find_prior_work,
    list_open_loops,
    log_decision,
    my_world_snapshot,
    today_brief,
)


# ---------------------------------------------------------------------------
# Error-mapping helper
# ---------------------------------------------------------------------------

_ERROR_TYPE_MAP: dict[type, str] = {
    ObsidianNotFound: "ObsidianNotFound",
    ObsidianNotRunning: "ObsidianNotRunning",
    VaultNotFound: "VaultNotFound",
    CommandTimeout: "CommandTimeout",
    MalformedCLIOutput: "MalformedCLIOutput",
}


def _error_envelope(exc: ObsidianCLIError) -> str:
    """Return a canonical JSON error envelope for an ObsidianCLIError."""
    error_type = _ERROR_TYPE_MAP.get(type(exc), "ObsidianCLIError")
    return json.dumps(
        {"ok": False, "error": {"type": error_type, "message": str(exc)}}
    )

mcp = FastMCP(
    "Obsidian Connector",
    json_response=True,
)


@mcp.tool(
    title="Search Obsidian Vault",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_search(query: str, vault: str | None = None) -> str:
    """Search across all notes in the Obsidian vault.

    Returns matching files with line numbers and text excerpts.
    Use this to find notes on a topic, locate prior work, or check
    if something already exists in the vault.
    """
    try:
        results = search_notes(query, vault=vault)
        return json.dumps(results, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Read Obsidian Note",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_read(name_or_path: str, vault: str | None = None) -> str:
    """Read the full content of a note from the Obsidian vault.

    Accepts either a wikilink-style name (e.g. "Project Alpha") or a
    vault-relative path (e.g. "Cards/Project Alpha.md").
    """
    try:
        return read_note(name_or_path, vault=vault)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="List Obsidian Tasks",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_tasks(
    status: str | None = None,
    path_prefix: str | None = None,
    limit: int | None = None,
    vault: str | None = None,
) -> str:
    """List tasks from the Obsidian vault.

    Args:
        status: Filter by "todo" or "done". Omit for all tasks.
        path_prefix: Only include tasks from files under this path.
        limit: Maximum number of tasks to return.
        vault: Target vault name (uses default if omitted).
    """
    try:
        f: dict = {}
        if status == "todo":
            f["todo"] = True
        elif status == "done":
            f["done"] = True
        if path_prefix:
            f["path"] = path_prefix
        if limit is not None:
            f["limit"] = limit
        results = list_tasks(filter=f or None, vault=vault)
        return json.dumps(results, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Log to Daily Note",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_log_daily(content: str, vault: str | None = None) -> str:
    """Append text to today's daily note in Obsidian.

    Use this to log meetings, decisions, ideas, or any timestamped entry.
    Supports full markdown (headings, bullets, links, etc.).
    """
    try:
        log_to_daily(content, vault=vault)
        return "Appended to daily note."
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Log Decision Record",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_log_decision(
    project: str,
    summary: str,
    details: str,
    vault: str | None = None,
) -> str:
    """Log a structured decision record to today's daily note.

    Creates a formatted block with project name, timestamp, summary,
    and detailed rationale. Use this for architectural decisions,
    strategy choices, or any decision worth recording.
    """
    try:
        log_decision(project, summary, details, vault=vault)
        return f"Decision logged for project: {project}"
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Find Prior Work",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_find_prior_work(
    topic: str,
    top_n: int = 5,
    vault: str | None = None,
) -> str:
    """Search for existing notes on a topic and return structured summaries.

    Returns the top N matching notes with their heading, first paragraph
    excerpt, and match count. Use this before creating new content to
    check what already exists.
    """
    try:
        results = find_prior_work(topic, vault=vault, top_n=top_n)
        return json.dumps(results, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Create Note from Template",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_create_note(
    title: str,
    template: str,
    vault: str | None = None,
) -> str:
    """Create a new note from a template in Obsidian.

    The template name must match exactly as shown by `obsidian templates`
    (e.g. "Template, Note"). The note is created and opened in Obsidian.
    """
    try:
        path = create_research_note(title, template, vault=vault)
        return f"Created: {path}"
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="My World Snapshot",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_my_world(
    vault: str | None = None,
    lookback_days: int = 14,
) -> str:
    """Get a snapshot of the entire vault state.

    Returns recent daily notes, open tasks, open loops, vault file count,
    and a hint about what to focus on next. Use this as a starting point
    when beginning a work session.

    Args:
        vault: Target vault name (uses default if omitted).
        lookback_days: Days to look back for daily notes (default 14).
    """
    try:
        result = my_world_snapshot(vault=vault, lookback_days=lookback_days)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Today Brief",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_today(vault: str | None = None) -> str:
    """Get a brief for today: daily note content, open tasks, open loops.

    Use this to see what is on the plate for the current day.

    Args:
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = today_brief(vault=vault)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Close Day Reflection",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_close_day(vault: str | None = None) -> str:
    """Generate an end-of-day reflection prompt (read-only).

    Returns completed tasks, remaining tasks, reflection questions, and
    suggested actions for tomorrow. Does NOT write to the vault.

    Args:
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = close_day_reflection(vault=vault)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Open Loops",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_open_loops(
    vault: str | None = None,
    lookback_days: int = 30,
) -> str:
    """List open loops in the vault.

    Finds lines starting with "OL:" and notes tagged with #openloop.
    Use this to review unresolved items that need attention.

    Args:
        vault: Target vault name (uses default if omitted).
        lookback_days: Lookback window in days (default 30).
    """
    try:
        result = list_open_loops(vault=vault, lookback_days=lookback_days)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Challenge Belief",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_challenge_belief(
    belief: str,
    vault: str | None = None,
    max_evidence: int = 10,
) -> str:
    """Challenge a belief by searching the vault for counter-evidence.

    Searches for contradicting and supporting evidence in your notes.
    Use this to stress-test assumptions, validate hypotheses, or play
    devil's advocate against a stated belief.

    Args:
        belief: The belief or assumption to challenge.
        vault: Target vault name (uses default if omitted).
        max_evidence: Maximum evidence items to return (default 10).
    """
    try:
        result = challenge_belief(belief, vault=vault, max_evidence=max_evidence)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Emerge Ideas",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_emerge_ideas(
    topic: str,
    vault: str | None = None,
    max_clusters: int = 5,
) -> str:
    """Cluster related notes into idea groups around a topic.

    Searches the vault for the topic, groups results by folder, and
    returns summaries for each cluster. Use this to discover how a topic
    is spread across your vault and find emergent patterns.

    Args:
        topic: Topic to explore.
        vault: Target vault name (uses default if omitted).
        max_clusters: Maximum number of clusters to return (default 5).
    """
    try:
        result = emerge_ideas(topic, vault=vault, max_clusters=max_clusters)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Connect Domains",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_connect_domains(
    domain_a: str,
    domain_b: str,
    vault: str | None = None,
    max_connections: int = 10,
) -> str:
    """Find connections between two domains in the vault.

    Searches for each domain separately, then finds notes that appear
    in both result sets. Use this to discover interdisciplinary links,
    bridge concepts, or find notes that span multiple topics.

    Args:
        domain_a: First domain to search.
        domain_b: Second domain to search.
        vault: Target vault name (uses default if omitted).
        max_connections: Maximum connecting notes to return (default 10).
    """
    try:
        result = connect_domains(
            domain_a, domain_b, vault=vault, max_connections=max_connections
        )
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Doctor Health Check",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_doctor(vault: str | None = None) -> str:
    """Run health checks on the Obsidian CLI connection.

    Checks: binary presence, version, vault resolution, and reachability.
    Use this to diagnose connectivity issues.
    """
    try:
        checks = run_doctor(vault=vault)
        return json.dumps(checks, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


def main() -> None:
    """Run the MCP server.

    Default transport is stdio (for claude_desktop_config.json).
    Pass ``--http`` to start a Streamable HTTP server on port 8000
    (for the Claude Desktop "Add custom connector" UI).
    """
    import sys

    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
