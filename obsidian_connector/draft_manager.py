"""Draft lifecycle manager for agent-generated content.

Manages drafts in ``Inbox/Agent Drafts/``: listing, approving,
rejecting, stale-draft cleanup, and summary reporting.  All move
operations are audit-logged and path-traversal-safe.

Milestone A3 of the v0.6.0 PRD.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class DraftInfo:
    """Metadata for a single agent-generated draft file."""

    path: str
    title: str
    created_at: str
    age_days: int
    source_tool: str
    status: str  # pending_review | approved | rejected | stale


# ---------------------------------------------------------------------------
# Frontmatter helpers (regex-based, no pyyaml dependency)
# ---------------------------------------------------------------------------

_FM_FENCE = re.compile(r"^---\s*\n", re.MULTILINE)


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML frontmatter key-value pairs from file content.

    Returns a flat dict of string keys to string values.  Only handles
    simple ``key: value`` lines (no nested structures).  Returns ``{}``
    when the file has no frontmatter.
    """
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}

    result: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kv = line.split(":", 1)
        if len(kv) == 2:
            key = kv[0].strip()
            val = kv[1].strip().strip('"').strip("'")
            result[key] = val
    return result


def _strip_generated_by(content: str) -> str:
    """Remove the ``generated_by`` line from YAML frontmatter.

    Preserves the rest of the frontmatter and the body.  If there is no
    frontmatter or no ``generated_by`` key, returns content unchanged.
    If removing the key leaves the frontmatter empty, the fences are
    also removed.
    """
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return content

    fm_block = m.group(1)
    body = content[m.end():]

    new_lines = []
    for line in fm_block.splitlines():
        stripped = line.strip()
        if stripped.startswith("generated_by"):
            kv = stripped.split(":", 1)
            if len(kv) == 2 and kv[0].strip() == "generated_by":
                continue  # drop this line
        new_lines.append(line)

    # If no frontmatter keys remain, drop the fences entirely.
    if all(not ln.strip() for ln in new_lines):
        return body.lstrip("\n")

    return "---\n" + "\n".join(new_lines) + "\n---" + body


def _add_datestamp_suffix(filename: str) -> str:
    """Append an ISO-date suffix before the file extension.

    ``"my-note.md"`` becomes ``"my-note_2026-03-30.md"``.
    """
    base, ext = os.path.splitext(filename)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{base}_{stamp}{ext}"


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def _validate_inside_vault(vault_path: Path, target: Path) -> None:
    """Raise ``ValueError`` if *target* escapes the vault root."""
    try:
        target.resolve().relative_to(vault_path.resolve())
    except ValueError:
        raise ValueError(
            f"Path traversal rejected: {target} is outside vault {vault_path}"
        )


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def list_drafts(
    vault_path: str | Path,
    drafts_folder: str = "Inbox/Agent Drafts",
) -> list[DraftInfo]:
    """Scan *drafts_folder* for files with ``generated_by`` frontmatter.

    Returns a list of :class:`DraftInfo` sorted by age descending
    (oldest first).
    """
    vault = Path(vault_path)
    folder = vault / drafts_folder

    if not folder.is_dir():
        return []

    from obsidian_connector.config import load_config

    cfg_data = _load_config_raw()
    max_age = int(cfg_data.get("draft_max_age_days", 14))

    drafts: list[DraftInfo] = []
    now = datetime.now(timezone.utc)

    for md_file in sorted(folder.rglob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        fm = _parse_frontmatter(content)
        if "generated_by" not in fm:
            continue

        # Determine creation time from frontmatter or file mtime.
        created_str = fm.get("created", "")
        if created_str:
            try:
                created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                created_dt = datetime.fromtimestamp(
                    md_file.stat().st_mtime, tz=timezone.utc
                )
        else:
            created_dt = datetime.fromtimestamp(
                md_file.stat().st_mtime, tz=timezone.utc
            )

        age = (now - created_dt).days
        status = "stale" if age >= max_age else "pending_review"

        rel_path = str(md_file.relative_to(vault))
        title = fm.get("title", md_file.stem)
        source_tool = fm.get("generated_by", "unknown")

        drafts.append(
            DraftInfo(
                path=rel_path,
                title=title,
                created_at=created_dt.isoformat(),
                age_days=age,
                source_tool=source_tool,
                status=status,
            )
        )

    # Sort by age descending (oldest first).
    drafts.sort(key=lambda d: d.age_days, reverse=True)
    return drafts


def approve_draft(
    vault_path: str | Path,
    draft_path: str,
    target_folder: str,
) -> dict[str, Any]:
    """Move a draft to *target_folder*, strip ``generated_by`` frontmatter.

    Returns a result dict with ``moved``, ``from``, ``to`` keys.
    """
    from obsidian_connector.audit import log_action

    vault = Path(vault_path)
    source = vault / draft_path

    if not source.is_file():
        return {"error": f"Draft not found: {draft_path}", "moved": False}

    target_dir = vault / target_folder
    _validate_inside_vault(vault, target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / source.name

    # Strip generated_by from content before writing.
    content = source.read_text(encoding="utf-8", errors="replace")
    cleaned = _strip_generated_by(content)
    dest.write_text(cleaned, encoding="utf-8")
    source.unlink()

    log_action(
        "draft-approve",
        {"draft": draft_path, "target_folder": target_folder},
        None,
        affected_path=str(dest),
    )

    return {
        "moved": True,
        "from": draft_path,
        "to": str(dest.relative_to(vault)),
        "status": "approved",
    }


def reject_draft(
    vault_path: str | Path,
    draft_path: str,
    archive_folder: str = "Archive/Rejected Drafts",
) -> dict[str, Any]:
    """Move a draft to *archive_folder* with a datestamp suffix.

    Returns a result dict with ``moved``, ``from``, ``to`` keys.
    """
    from obsidian_connector.audit import log_action

    vault = Path(vault_path)
    source = vault / draft_path

    if not source.is_file():
        return {"error": f"Draft not found: {draft_path}", "moved": False}

    archive_dir = vault / archive_folder
    _validate_inside_vault(vault, archive_dir)

    archive_dir.mkdir(parents=True, exist_ok=True)
    new_name = _add_datestamp_suffix(source.name)
    dest = archive_dir / new_name

    shutil.move(str(source), str(dest))

    log_action(
        "draft-reject",
        {"draft": draft_path, "archive_folder": archive_folder},
        None,
        affected_path=str(dest),
    )

    return {
        "moved": True,
        "from": draft_path,
        "to": str(dest.relative_to(vault)),
        "status": "rejected",
    }


def clean_stale_drafts(
    vault_path: str | Path,
    max_age_days: int = 14,
    archive_folder: str = "Archive/Stale Drafts",
    dry_run: bool = False,
    drafts_folder: str = "Inbox/Agent Drafts",
) -> list[dict[str, str]]:
    """Move drafts older than *max_age_days* to *archive_folder*.

    Parameters
    ----------
    vault_path:
        Root directory of the Obsidian vault.
    max_age_days:
        Age threshold in days.  Drafts older than this are stale.
    archive_folder:
        Target folder for stale drafts.
    dry_run:
        If ``True``, report what would be moved without moving.
    drafts_folder:
        Folder to scan for drafts.

    Returns
    -------
    list[dict[str, str]]
        List of ``{"from": ..., "to": ...}`` dicts for moved (or
        would-be-moved) files.
    """
    from obsidian_connector.audit import log_action

    vault = Path(vault_path)
    archive_dir = vault / archive_folder
    _validate_inside_vault(vault, archive_dir)

    drafts = list_drafts(vault_path, drafts_folder=drafts_folder)
    moved: list[dict[str, str]] = []

    for draft in drafts:
        if draft.age_days < max_age_days:
            continue

        source = vault / draft.path
        if not source.is_file():
            continue

        new_name = _add_datestamp_suffix(source.name)
        dest = archive_dir / new_name
        entry = {"from": draft.path, "to": str(dest.relative_to(vault))}

        if not dry_run:
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(dest))
            log_action(
                "draft-clean-stale",
                {"draft": draft.path, "max_age_days": max_age_days},
                None,
                affected_path=str(dest),
            )

        moved.append(entry)

    return moved


def draft_summary(
    vault_path: str | Path,
    drafts_folder: str = "Inbox/Agent Drafts",
) -> dict[str, int]:
    """Return counts by status for dashboard integration.

    Returns a dict with ``pending_review``, ``stale``, and ``total``
    keys.
    """
    drafts = list_drafts(vault_path, drafts_folder=drafts_folder)
    pending = sum(1 for d in drafts if d.status == "pending_review")
    stale = sum(1 for d in drafts if d.status == "stale")
    return {
        "pending_review": pending,
        "stale": stale,
        "total": len(drafts),
    }


# ---------------------------------------------------------------------------
# Internal config helper
# ---------------------------------------------------------------------------

def _load_config_raw() -> dict:
    """Load raw config.json dict for draft-specific settings."""
    import json

    from obsidian_connector.config import _find_config_file

    path = _find_config_file()
    if path is None:
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
