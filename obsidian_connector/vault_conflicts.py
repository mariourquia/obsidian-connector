"""Shared-vault conflict-file detection (Task 37).

A pure, filesystem-only scanner that surfaces iCloud Drive, Dropbox,
OneDrive, and Obsidian Sync conflict-file patterns inside a vault root.
No network calls. No mutation. Deterministic output (sorted by relative
path) so the result can be cached or rendered into a dashboard.

The connector never produces conflict files itself -- the sync daemon
of whichever cloud provider the vault lives on does. This module is
the read side of the "shared vault" story documented in
``docs/implementation/shared_vault.md``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConflictFile:
    """One conflict file the scanner surfaced."""

    relative_path: str
    provider: str
    pattern_label: str
    size_bytes: int

    def to_dict(self) -> dict:
        return {
            "relative_path": self.relative_path,
            "provider": self.provider,
            "pattern_label": self.pattern_label,
            "size_bytes": self.size_bytes,
        }


# Provider-specific conflict patterns. Order matters only for the first
# match wins tie-break (deliberately from most-specific to least so a
# Dropbox-style filename is not mis-labelled as iCloud).
#
# Patterns are matched against the file *stem* (filename without `.md`).
_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        "Dropbox",
        r"\(.* conflicted copy \d{4}-\d{2}-\d{2}\)",
        "(... conflicted copy YYYY-MM-DD)",
    ),
    (
        "iCloud Drive",
        r"\(.*iPhone\)",
        "(... iPhone)",
    ),
    (
        "iCloud Drive",
        r"\(.*iPad\)",
        "(... iPad)",
    ),
    (
        "iCloud Drive",
        r"\(.*Mac\)",
        "(... Mac)",
    ),
    (
        "Obsidian Sync",
        r"\([a-f0-9]{8,}\)$",
        "(<vault-id>) hex suffix",
    ),
    (
        "OneDrive",
        r"-[A-Z][A-Z0-9-]{2,}$",
        "-<DEVICENAME> suffix",
    ),
    # iCloud's " 2" / " 3" trailing-digit is a weak signal -- it catches
    # legitimate user names ("Draft 2"). Only flag when the twin
    # basename without the suffix also exists (see the resolver below).
    (
        "iCloud Drive (weak)",
        r" [0-9]+$",
        " <n> suffix with twin present",
    ),
)


def _match_pattern(stem: str) -> tuple[str, str] | None:
    """Return ``(provider, pattern_label)`` for the first pattern that matches."""
    for provider, pattern, label in _PATTERNS:
        if re.search(pattern, stem):
            return provider, label
    return None


def detect_vault_conflicts(vault_root: Path | str) -> dict:
    """Scan ``vault_root`` for conflict-file patterns.

    Returns an envelope dict::

        {
            "ok": True,
            "vault_root": "<absolute path>",
            "scanned": <int>,
            "items": [ConflictFile.to_dict(), ...],
        }

    or on invalid input::

        {"ok": False, "error": "<human-readable reason>"}

    Never raises. Skips ``.git``, ``.obsidian``, ``.trash``, and any
    directory whose name starts with ``_`` (Obsidian's "unindexed"
    convention).
    """
    root = Path(vault_root).expanduser()
    if not root.exists() or not root.is_dir():
        return {"ok": False, "error": f"vault_root not a directory: {root}"}

    root = root.resolve()
    skip_dir_names = {".git", ".obsidian", ".trash"}
    items: list[ConflictFile] = []
    scanned = 0

    # First pass: collect every .md basename so the iCloud weak-signal
    # resolver can check for a "twin" (Note.md alongside Note 2.md).
    all_md_stems: set[str] = set()
    for fpath in root.rglob("*.md"):
        if any(part in skip_dir_names or part.startswith("_") for part in fpath.relative_to(root).parts):
            continue
        all_md_stems.add(fpath.stem)

    for fpath in sorted(root.rglob("*.md")):
        rel = fpath.relative_to(root)
        if any(part in skip_dir_names or part.startswith("_") for part in rel.parts):
            continue
        scanned += 1

        stem = fpath.stem
        hit = _match_pattern(stem)
        if hit is None:
            continue

        provider, label = hit

        # Weak-signal guard: only flag the " 2.md" pattern when the
        # twin basename exists. Without a twin, " 2" is probably just
        # a user-chosen name ("Draft 2").
        if provider == "iCloud Drive (weak)":
            twin = re.sub(r" [0-9]+$", "", stem)
            if twin not in all_md_stems:
                continue
            # Promote to the canonical iCloud Drive bucket once the
            # twin is confirmed; the "(weak)" suffix was only a gate.
            provider = "iCloud Drive"

        try:
            size = fpath.stat().st_size
        except OSError:
            size = 0

        items.append(
            ConflictFile(
                relative_path=str(rel),
                provider=provider,
                pattern_label=label,
                size_bytes=size,
            )
        )

    return {
        "ok": True,
        "vault_root": str(root),
        "scanned": scanned,
        "items": [item.to_dict() for item in items],
    }


__all__ = ["ConflictFile", "detect_vault_conflicts"]
