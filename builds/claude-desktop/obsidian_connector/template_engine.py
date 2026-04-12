"""Template loading, variable substitution, and inheritance for obsidian-connector.

Provides a template engine that loads templates from a vault's ``_templates/``
folder, supports ``{{variable}}`` substitution (including built-in date/time
variables), template inheritance via ``extends:`` frontmatter, and versioning.

Built-in templates are embedded in this module and can be exported to a vault
with :func:`init_templates`.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from obsidian_connector.errors import ObsidianCLIError


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TemplateNotFoundError(ObsidianCLIError):
    """Requested template does not exist."""

    def __init__(self, message: str = "template not found") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=1,
            stdout="",
            stderr=message,
        )


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class TemplateInfo:
    """Metadata about a single template."""

    name: str
    path: str
    version: str
    extends: str | None
    description: str
    variables: list[str]


# ---------------------------------------------------------------------------
# Frontmatter parsing (stdlib-only, no pyyaml)
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract a flat key-value dict from YAML-style frontmatter."""
    m = _FM_RE.match(text)
    if not m:
        return {}
    result: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":", 1)
        if len(parts) == 2:
            key = parts[0].strip()
            val = parts[1].strip().strip('"').strip("'")
            result[key] = val
    return result


def _strip_frontmatter(text: str) -> str:
    """Return template content without frontmatter block."""
    return _FM_RE.sub("", text)


def _extract_variables(text: str) -> list[str]:
    """Return sorted unique list of ``{{var}}`` names in *text*."""
    return sorted(set(_VAR_RE.findall(text)))


# ---------------------------------------------------------------------------
# Built-in variables
# ---------------------------------------------------------------------------


def _builtin_variables(vault_name: str = "", now: datetime | None = None) -> dict[str, str]:
    """Return the map of auto-populated variables."""
    now = now or datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "datetime": now.isoformat(timespec="seconds"),
        "time": now.strftime("%H:%M"),
        "vault_name": vault_name,
        "year": now.strftime("%Y"),
        "month": now.strftime("%m"),
        "day": now.strftime("%d"),
        "weekday": now.strftime("%A"),
    }


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATES: dict[str, str] = {
    "daily-note": (
        "---\n"
        "template: daily-note\n"
        "version: 1.0.0\n"
        "description: Configurable daily note with morning and evening sections\n"
        "---\n"
        "# {{date}} -- {{weekday}}\n"
        "\n"
        "## Morning Ritual\n"
        "\n"
        "- [ ] Review today's calendar\n"
        "- [ ] Set top 3 priorities\n"
        "- [ ] Check in on open loops\n"
        "\n"
        "### Intentions\n"
        "\n"
        "1. \n"
        "2. \n"
        "3. \n"
        "\n"
        "## Work Log\n"
        "\n"
        "\n"
        "## Evening Reflection\n"
        "\n"
        "- What went well today?\n"
        "- What could improve?\n"
        "- Anything to carry forward?\n"
    ),
    "meeting-note": (
        "---\n"
        "template: meeting-note\n"
        "version: 1.0.0\n"
        "description: Meeting note with attendees, agenda, decisions, and action items\n"
        "---\n"
        "# Meeting -- {{date}}\n"
        "\n"
        "## Attendees\n"
        "\n"
        "- \n"
        "\n"
        "## Agenda\n"
        "\n"
        "1. \n"
        "\n"
        "## Discussion\n"
        "\n"
        "\n"
        "## Decisions\n"
        "\n"
        "- \n"
        "\n"
        "## Action Items\n"
        "\n"
        "- [ ] \n"
    ),
    "research-note": (
        "---\n"
        "template: research-note\n"
        "version: 1.0.0\n"
        "description: Research note with topic, sources, key findings, and questions\n"
        "---\n"
        "# Research -- {{title}}\n"
        "\n"
        "**Date:** {{date}}\n"
        "\n"
        "## Topic\n"
        "\n"
        "\n"
        "## Sources\n"
        "\n"
        "- \n"
        "\n"
        "## Key Findings\n"
        "\n"
        "1. \n"
        "\n"
        "## Open Questions\n"
        "\n"
        "- \n"
        "\n"
        "## Connections\n"
        "\n"
        "- \n"
    ),
    "decision-log": (
        "---\n"
        "template: decision-log\n"
        "version: 1.0.0\n"
        "description: Decision log with context, options, decision, and rationale\n"
        "---\n"
        "# Decision -- {{title}}\n"
        "\n"
        "**Date:** {{date}}\n"
        "\n"
        "## Context\n"
        "\n"
        "\n"
        "## Options Considered\n"
        "\n"
        "1. \n"
        "2. \n"
        "3. \n"
        "\n"
        "## Decision\n"
        "\n"
        "\n"
        "## Rationale\n"
        "\n"
        "\n"
        "## Consequences\n"
        "\n"
        "- \n"
    ),
    "project-idea": (
        "---\n"
        "template: project-idea\n"
        "version: 1.0.0\n"
        "description: Project idea with problem, solution, effort estimate, and next steps\n"
        "---\n"
        "# Idea -- {{title}}\n"
        "\n"
        "**Date:** {{date}}\n"
        "\n"
        "## Problem\n"
        "\n"
        "\n"
        "## Proposed Solution\n"
        "\n"
        "\n"
        "## Effort Estimate\n"
        "\n"
        "- Complexity: \n"
        "- Time: \n"
        "- Dependencies: \n"
        "\n"
        "## Next Steps\n"
        "\n"
        "- [ ] \n"
    ),
}


# ---------------------------------------------------------------------------
# Template Engine
# ---------------------------------------------------------------------------


class TemplateEngine:
    """Load, list, render, and manage vault templates.

    Parameters
    ----------
    vault_path:
        Absolute path to the Obsidian vault root.
    templates_folder:
        Name of the templates folder inside the vault (default ``_templates``).
    """

    def __init__(self, vault_path: str | Path, templates_folder: str = "_templates") -> None:
        self.vault_path = Path(vault_path)
        self.templates_folder = templates_folder
        self._templates_dir = self.vault_path / templates_folder
        self._cache: dict[str, str] = {}
        self._load_all()

    # -- Loading -------------------------------------------------------------

    def _load_all(self) -> None:
        """Scan the templates directory and populate the internal cache."""
        self._cache.clear()
        if not self._templates_dir.is_dir():
            return
        for fp in sorted(self._templates_dir.iterdir()):
            if fp.suffix == ".md" and fp.is_file():
                name = fp.stem
                self._cache[name] = fp.read_text(encoding="utf-8")

    # -- Public API ----------------------------------------------------------

    def list_templates(self) -> list[TemplateInfo]:
        """Return metadata for every loaded template."""
        result: list[TemplateInfo] = []
        for name, content in sorted(self._cache.items()):
            fm = _parse_frontmatter(content)
            result.append(
                TemplateInfo(
                    name=name,
                    path=str(self._templates_dir / f"{name}.md"),
                    version=fm.get("version", "0.0.0"),
                    extends=fm.get("extends") or None,
                    description=fm.get("description", ""),
                    variables=_extract_variables(content),
                )
            )
        return result

    def get_template(self, name: str) -> str:
        """Return raw template content, including frontmatter.

        Raises
        ------
        TemplateNotFoundError
            If *name* is not in the loaded templates.
        """
        if name not in self._cache:
            raise TemplateNotFoundError(f"template not found: {name}")
        return self._cache[name]

    def render(
        self,
        name: str,
        variables: dict[str, str] | None = None,
        *,
        now: datetime | None = None,
    ) -> str:
        """Render a template with variable substitution.

        Built-in variables (``{{date}}``, ``{{vault_name}}``, etc.) are
        auto-populated.  Caller-supplied *variables* override built-ins.
        Unknown ``{{placeholders}}`` are left as-is.

        Parameters
        ----------
        name:
            Template name (stem of the ``.md`` file).
        variables:
            Optional mapping of variable names to values.
        now:
            Override for the current time (testing convenience).
        """
        raw = self.get_template(name)
        content = _strip_frontmatter(raw)

        vault_name = self.vault_path.name
        merged = _builtin_variables(vault_name=vault_name, now=now)
        if variables:
            merged.update(variables)

        def _replace(m: re.Match) -> str:
            key = m.group(1)
            return merged.get(key, m.group(0))

        return _VAR_RE.sub(_replace, content)

    def render_with_inheritance(
        self,
        name: str,
        variables: dict[str, str] | None = None,
        *,
        now: datetime | None = None,
    ) -> str:
        """Render a template, merging with its base if ``extends:`` is set.

        Inheritance rule: the base template is rendered first, then sections
        (identified by ``## Heading``) from the child template replace the
        corresponding sections in the base.  Sections in the base that are
        not overridden by the child are preserved.
        """
        raw = self.get_template(name)
        fm = _parse_frontmatter(raw)
        base_name = fm.get("extends")

        if not base_name:
            return self.render(name, variables, now=now)

        base_rendered = self.render(base_name, variables, now=now)
        child_rendered = self.render(name, variables, now=now)

        base_sections = _split_sections(base_rendered)
        child_sections = _split_sections(child_rendered)

        # Overlay child sections onto base
        merged_sections: dict[str, str] = dict(base_sections)
        for heading, body in child_sections.items():
            merged_sections[heading] = body

        # Rebuild in base order, then append new child-only sections
        lines: list[str] = []
        seen: set[str] = set()

        # Preserve leading content before first section from base
        if "" in base_sections:
            lines.append(base_sections[""])
            seen.add("")

        for heading in base_sections:
            if heading in seen:
                continue
            seen.add(heading)
            content = merged_sections.get(heading, base_sections[heading])
            if heading:
                lines.append(heading)
            lines.append(content)

        # Add child-only sections not present in base
        for heading in child_sections:
            if heading not in seen:
                seen.add(heading)
                if heading:
                    lines.append(heading)
                lines.append(child_sections[heading])

        return "\n".join(lines)

    def check_updates(self) -> list[dict[str, str]]:
        """Compare vault templates against built-in versions.

        Returns a list of dicts with ``name``, ``vault_version``,
        ``builtin_version`` for templates that are outdated.
        """
        outdated: list[dict[str, str]] = []
        for name, builtin_content in BUILTIN_TEMPLATES.items():
            if name not in self._cache:
                continue
            vault_fm = _parse_frontmatter(self._cache[name])
            builtin_fm = _parse_frontmatter(builtin_content)
            vault_ver = vault_fm.get("version", "0.0.0")
            builtin_ver = builtin_fm.get("version", "0.0.0")
            if _version_lt(vault_ver, builtin_ver):
                outdated.append(
                    {
                        "name": name,
                        "vault_version": vault_ver,
                        "builtin_version": builtin_ver,
                    }
                )
        return outdated


# ---------------------------------------------------------------------------
# Section splitting for inheritance
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^(## .+)$", re.MULTILINE)


def _split_sections(text: str) -> dict[str, str]:
    """Split rendered text into ``{heading: body}`` pairs.

    The key ``""`` (empty string) holds content before the first ``##``
    heading.  Heading lines themselves are the keys; the body is everything
    between one heading and the next.
    """
    parts = _SECTION_RE.split(text)
    sections: dict[str, str] = {}
    if parts and parts[0].strip():
        sections[""] = parts[0].rstrip("\n")
    i = 1
    while i < len(parts) - 1:
        heading = parts[i]
        body = parts[i + 1].strip("\n")
        sections[heading] = body
        i += 2
    # Handle trailing heading with no body
    if i < len(parts) and parts[i].startswith("## "):
        sections[parts[i]] = ""
    return sections


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def _version_lt(a: str, b: str) -> bool:
    """Return True if version string *a* is strictly less than *b*.

    Compares dot-separated numeric segments (e.g. ``"1.0.0"`` < ``"1.1.0"``).
    Non-numeric segments compare as 0.
    """

    def _parts(v: str) -> list[int]:
        result: list[int] = []
        for seg in v.split("."):
            try:
                result.append(int(seg))
            except ValueError:
                result.append(0)
        return result

    return _parts(a) < _parts(b)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def init_templates(vault_path: str | Path) -> list[str]:
    """Copy all built-in templates to the vault's ``_templates/`` folder.

    Creates the directory if it does not exist.  Does **not** overwrite
    existing files.

    Returns the list of template names that were written.
    """
    vault = Path(vault_path)
    templates_dir = vault / "_templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for name, content in sorted(BUILTIN_TEMPLATES.items()):
        dest = templates_dir / f"{name}.md"
        if not dest.exists():
            dest.write_text(content, encoding="utf-8")
            written.append(name)
    return written


def format_daily_note_path(
    config: Any,
    date: datetime | None = None,
) -> str:
    """Compute the daily note file path from config settings.

    Uses ``config.daily_note_path`` (default ``"daily/{{date}}.md"``) and
    ``config.daily_note_format`` (default ``"YYYY-MM-DD"``) to produce the
    path string.

    Parameters
    ----------
    config:
        A config-like object (or dict-like) with optional ``daily_note_path``
        and ``daily_note_format`` attributes.
    date:
        The date to format.  Defaults to today.
    """
    date = date or datetime.now()

    # Read config values with attribute or dict access
    if hasattr(config, "daily_note_path"):
        path_template = getattr(config, "daily_note_path", None) or "daily/{{date}}.md"
    elif isinstance(config, dict):
        path_template = config.get("daily_note_path", "daily/{{date}}.md")
    else:
        path_template = "daily/{{date}}.md"

    if hasattr(config, "daily_note_format"):
        fmt = getattr(config, "daily_note_format", None) or "YYYY-MM-DD"
    elif isinstance(config, dict):
        fmt = config.get("daily_note_format", "YYYY-MM-DD")
    else:
        fmt = "YYYY-MM-DD"

    # Convert YYYY-MM-DD format spec to strftime
    strfmt = fmt.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
    date_str = date.strftime(strfmt)

    # Substitute {{date}} and other variables in the path template
    vars_map = _builtin_variables(now=date)
    vars_map["date"] = date_str

    def _replace(m: re.Match) -> str:
        key = m.group(1)
        return vars_map.get(key, m.group(0))

    return _VAR_RE.sub(_replace, path_template)


_DEFAULT_SENTINELS: dict[str, str] = {
    "morning_ritual": "## Morning Ritual",
    "evening_ritual": "## Evening Reflection",
    "work_log": "## Work Log",
    "intentions": "### Intentions",
    "action_items": "## Action Items",
    "decisions": "## Decisions",
}


def get_sentinels(config: Any) -> dict[str, str]:
    """Return the sentinel heading map from config.

    Looks for a ``sentinels`` key on *config*.  Returns the default map when
    the key is absent or ``None``.

    Parameters
    ----------
    config:
        A config-like object or dict with an optional ``sentinels`` attribute.
    """
    sentinels = None
    if hasattr(config, "sentinels"):
        sentinels = getattr(config, "sentinels", None)
    elif isinstance(config, dict):
        sentinels = config.get("sentinels")

    if sentinels and isinstance(sentinels, dict):
        return dict(sentinels)
    return dict(_DEFAULT_SENTINELS)
