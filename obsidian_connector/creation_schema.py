# obsidian_connector/creation_schema.py
"""Freshness/authority frontmatter schema + machine IDs for the Creation Vault OS.

See docs/architecture/creation-vault-schema.md.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields

STATUS_LABELS: tuple[str, ...] = (
    "verified_current",
    "fresh_user_instruction",
    "repo_grounded",
    "agent_reported_unverified",
    "stale_needs_review",
    "deprecated",
    "conflicting",
)
_ID_PREFIXES = {"bkl", "ses", "chk", "ctxp", "dec"}
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str, seed: str) -> str:
    """Deterministic ULID-style id. The random component is derived from a
    caller-supplied seed (timestamp + counter + content) so callers stay
    testable and resume-safe; this function never reads a clock."""
    if prefix not in _ID_PREFIXES:
        raise ValueError(f"unknown id prefix: {prefix!r}")
    digest = hashlib.sha256(seed.encode()).digest()
    n = int.from_bytes(digest[:13], "big")          # 104 bits -> 21 base32 chars
    chars = []
    for _ in range(21):
        n, rem = divmod(n, 32)
        chars.append(_CROCKFORD[rem])
    return f"{prefix}_" + "".join(reversed(chars))


@dataclass(frozen=True)
class Freshness:
    id: str
    authority_level: str
    confidence: float = 0.5
    last_verified_at: str | None = None
    last_verified_by: str | None = None
    verification_source: str | None = None
    source_repo: str | None = None
    source_branch: str | None = None
    source_commit: str | None = None
    source_pr: str | None = None
    source_session: str | None = None
    staleness_policy: str = "manual"     # manual | ttl | repo-commit
    valid_until: str | None = None
    supersedes: tuple[str, ...] = ()
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        if self.authority_level not in STATUS_LABELS:
            raise ValueError(f"authority_level must be one of {STATUS_LABELS}")


def freshness_to_dict(f: Freshness) -> dict:
    out: dict = {}
    for fld in fields(Freshness):
        val = getattr(f, fld.name)
        if isinstance(val, tuple):
            val = list(val)
        out[fld.name] = val
    return out


def freshness_from_dict(d: dict) -> Freshness:
    known = {fld.name for fld in fields(Freshness)}
    kwargs = {k: v for k, v in d.items() if k in known}
    # Coerce confidence to float: the frontmatter reader returns strings, so
    # `confidence: 0.8` loads as '0.8' which violates the float annotation.
    if "confidence" in kwargs:
        try:
            kwargs["confidence"] = float(kwargs["confidence"])
        except (TypeError, ValueError):
            kwargs["confidence"] = 0.5
    # Robust supersedes parse: the string-only frontmatter parser cannot
    # represent real lists yet; proper list parsing lands with backlog
    # materialization (deferred).
    if "supersedes" in kwargs:
        val = kwargs["supersedes"]
        if val is None:
            kwargs["supersedes"] = ()
        elif isinstance(val, (list, tuple)):
            kwargs["supersedes"] = tuple(val)
        elif isinstance(val, str):
            stripped = val.strip()
            if stripped in ("", "[]"):
                kwargs["supersedes"] = ()
            else:
                kwargs["supersedes"] = (stripped,)
        else:
            kwargs["supersedes"] = (str(val),)
    return Freshness(**kwargs)
