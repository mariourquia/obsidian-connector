# obsidian_connector/creation_freshness.py
"""Authority hierarchy + staleness for the Creation Vault OS freshness spine."""
from __future__ import annotations

from .creation_schema import Freshness

AUTHORITY_ORDER: tuple[str, ...] = (
    "fresh_user_instruction",
    "repo_grounded",
    "verified_current",
    "agent_reported_unverified",
    "stale_needs_review",
    "conflicting",
    "deprecated",
)


def is_stale(f: Freshness, *, repo_head: str | None = None, now_iso: str | None = None) -> bool:
    if f.staleness_policy == "repo-commit":
        return bool(f.source_commit) and repo_head is not None and f.source_commit != repo_head
    if f.staleness_policy == "ttl":
        return bool(f.valid_until) and now_iso is not None and now_iso > f.valid_until
    return False


def resolve_label(f: Freshness, *, repo_head: str | None = None, now_iso: str | None = None) -> str:
    if is_stale(f, repo_head=repo_head, now_iso=now_iso):
        return "stale_needs_review"
    return f.authority_level


def can_complete(f: Freshness) -> tuple[bool, str]:
    if f.source_commit or f.source_pr:
        return True, "has repo evidence"
    return False, "completion requires repo evidence (source_commit or source_pr)"
