"""MCP server exposing obsidian-connector tools for Claude Desktop."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

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
    create_research_note,
    find_prior_work,
    log_decision,
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


@mcp.tool()
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


@mcp.tool()
def obsidian_read(name_or_path: str, vault: str | None = None) -> str:
    """Read the full content of a note from the Obsidian vault.

    Accepts either a wikilink-style name (e.g. "Project Alpha") or a
    vault-relative path (e.g. "Cards/Project Alpha.md").
    """
    try:
        return read_note(name_or_path, vault=vault)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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
