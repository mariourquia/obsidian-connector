# obsidian_connector/creation_status.py
"""Read-only `creation status` + `freshness-audit` (the dashboard read-view seed)."""
from __future__ import annotations

from pathlib import Path

from . import creation_events as ce
from . import creation_freshness as cf
from . import creation_schema as cs
from . import creation_session as csess
from .draft_manager import _parse_frontmatter  # existing simple key:value YAML reader


def creation_status(vault_path: Path) -> dict:
    events = ce.read_events(vault_path)
    return {
        "active_session": csess.active_session(vault_path),
        "event_count": len(events),
        "recent_events": events[-10:],
        "stale_warnings": freshness_audit(vault_path).get("stale", []),
    }


def _load_freshness(md_path: Path) -> cs.Freshness | None:
    fm = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
    if not fm or "authority_level" not in fm:
        return None
    try:
        return cs.freshness_from_dict(fm)
    except (ValueError, TypeError):
        return None


def freshness_audit(vault_path: Path, *, repo_heads: dict | None = None,
                    now_iso: str | None = None) -> dict:
    repo_heads = repo_heads or {}
    stale, conflicting, checked = [], [], 0
    for md in sorted((Path(vault_path) / "Backlog").rglob("*.md")):
        f = _load_freshness(md)
        if f is None:
            continue
        checked += 1
        head = repo_heads.get(f.source_repo or "")
        if f.authority_level == "conflicting":
            conflicting.append({"id": f.id, "path": str(md)})
        elif cf.is_stale(f, repo_head=head, now_iso=now_iso):
            stale.append({"id": f.id, "path": str(md), "source_repo": f.source_repo})
    return {"stale": stale, "conflicting": conflicting, "checked": checked}
