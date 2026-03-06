"""Append-only audit log for obsidian-connector commands."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_DIR: Path = Path.home() / ".obsidian-connector" / "logs"


def log_action(
    command: str,
    args: dict[str, Any],
    vault: str | None,
    dry_run: bool = False,
    affected_path: str | None = None,
    content: str | None = None,
) -> Path:
    """Append a single JSON line to today's audit log.

    Parameters
    ----------
    command:
        The CLI command name (e.g. ``"search"``, ``"read"``).
    args:
        Argument dict passed to the command.
    vault:
        Vault name, or ``None`` if not applicable.
    dry_run:
        Whether this was a dry-run invocation.
    affected_path:
        Filesystem or vault path affected by the command, if any.
    content:
        Optional content body.  If provided, its SHA-256 hex digest is
        stored as ``content_hash`` instead of the raw text.

    Returns
    -------
    Path
        Absolute path to the JSONL log file that was written to.
    """
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    content_hash: str | None = None
    if content is not None:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "args": args,
        "vault": vault,
        "dry_run": dry_run,
        "affected_path": affected_path,
        "content_hash": content_hash,
    }

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = AUDIT_DIR / f"{today}.jsonl"

    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    return log_file
