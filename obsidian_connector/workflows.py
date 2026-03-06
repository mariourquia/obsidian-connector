"""Higher-level workflows built on top of the core client functions."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from obsidian_connector.client import (
    ObsidianCLIError,
    log_to_daily,
    read_note,
    run_obsidian,
    search_notes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INLINE_FIELD_RE = re.compile(r"^[A-Za-z_][\w\s]*::.*$")


def _extract_note_summary(text: str) -> tuple[str, str]:
    """Extract the first heading and first paragraph from markdown.

    Skips Obsidian inline-field lines (``key:: value``) and YAML
    frontmatter (``---`` fences).

    Returns
    -------
    tuple[str, str]
        (heading_or_first_line, first_paragraph_text)
    """
    lines = text.split("\n")
    heading = ""
    paragraph_lines: list[str] = []
    in_frontmatter = False
    found_heading = False

    for i, raw in enumerate(lines):
        stripped = raw.strip()

        # Skip YAML frontmatter block.
        if i == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue

        # Skip inline-field lines (e.g. "tags:: #on/Health").
        if _INLINE_FIELD_RE.match(stripped):
            continue

        # Skip blank lines (but they terminate the first paragraph).
        if not stripped:
            if found_heading and paragraph_lines:
                break
            continue

        if not found_heading:
            if stripped.startswith("#"):
                heading = stripped.lstrip("#").strip()
            else:
                heading = stripped
            found_heading = True
            continue

        # Stop at the next heading.
        if stripped.startswith("#"):
            break

        paragraph_lines.append(stripped)

    return heading, " ".join(paragraph_lines)


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

def log_decision(
    project: str,
    summary: str,
    details: str,
    vault: str | None = None,
) -> None:
    """Append a structured decision record to today's daily note.

    The resulting markdown block looks like::

        ## Decision -- <project>
        **Time:** 2026-03-05T14:32:00+00:00
        - **Summary:** <summary>

        <details>

    Parameters
    ----------
    project:
        Project or workstream name (used in the heading).
    summary:
        One-line description of the decision.
    details:
        Longer context, rationale, or follow-up items (markdown OK).
    vault:
        Target vault name.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    block = (
        f"## Decision -- {project}\n"
        f"**Time:** {ts}\n"
        f"- **Summary:** {summary}\n"
        f"\n"
        f"{details}"
    )
    log_to_daily(block, vault=vault)


def create_research_note(
    title: str,
    template: str,
    vault: str | None = None,
) -> str:
    """Create a new note from a template and return its vault-relative path.

    Parameters
    ----------
    title:
        Note title (becomes the file name).
    template:
        Template name as shown by ``obsidian templates`` (e.g.
        ``"Template, Note"``).
    vault:
        Target vault name.

    Returns
    -------
    str
        Vault-relative path of the created note (e.g. ``"My Note.md"``).

    Raises
    ------
    ObsidianCLIError
        If the CLI reports an error (template not found, etc.).
    """
    stdout = run_obsidian(
        ["create", f"name={title}", f"template={template}", "open"],
        vault=vault,
    )
    stripped = stdout.strip()

    # The CLI returns exit 0 even on errors; detect via stdout content.
    if stripped.startswith("Error:"):
        raise ObsidianCLIError(
            command=["create"],
            returncode=0,
            stdout=stdout,
            stderr=stripped,
        )

    # Expected: "Created: <path>"
    if stripped.startswith("Created:"):
        return stripped.removeprefix("Created:").strip()

    # Fallback: search for the note by title.
    results = search_notes(title, vault=vault)
    for r in results:
        fname: str = r.get("file", "")
        if title.lower() in fname.lower():
            return fname

    return f"{title}.md"


def find_prior_work(
    topic: str,
    vault: str | None = None,
    top_n: int = 5,
) -> list[dict]:
    """Search for existing notes on *topic* and return structured summaries.

    Parameters
    ----------
    topic:
        Search query.
    vault:
        Target vault name.
    top_n:
        Maximum number of notes to return (default 5).

    Returns
    -------
    list[dict]
        Each dict contains:

        - ``file`` -- vault-relative path
        - ``heading`` -- first markdown heading (or first non-empty line)
        - ``excerpt`` -- first paragraph after the heading
        - ``match_count`` -- number of search matches in that note
    """
    hits = search_notes(topic, vault=vault)[:top_n]
    results: list[dict] = []

    for hit in hits:
        file_path: str = hit.get("file", "")
        match_count = len(hit.get("matches", []))

        try:
            content = read_note(file_path, vault=vault)
        except ObsidianCLIError:
            content = ""

        heading, excerpt = _extract_note_summary(content)
        results.append(
            {
                "file": file_path,
                "heading": heading,
                "excerpt": excerpt[:300],
                "match_count": match_count,
            }
        )

    return results
