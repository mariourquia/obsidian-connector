"""Canonical JSON response envelope for obsidian-connector commands."""

from __future__ import annotations

import json
from typing import Any


def success_envelope(
    command: str,
    data: Any,
    vault: str | None,
    duration_ms: int,
) -> dict:
    """Build a success response envelope.

    Parameters
    ----------
    command:
        The CLI command name (e.g. ``"search"``, ``"read"``).
    data:
        Arbitrary payload returned by the command.
    vault:
        Vault name used for the command, or ``None``.
    duration_ms:
        Wall-clock duration of the command in milliseconds.
    """
    return {
        "ok": True,
        "command": command,
        "vault": vault,
        "duration_ms": duration_ms,
        "data": data,
    }


def error_envelope(
    command: str,
    error_type: str,
    message: str,
    stderr: str = "",
    exit_code: int | None = None,
    vault: str | None = None,
) -> dict:
    """Build an error response envelope.

    Parameters
    ----------
    command:
        The CLI command name that failed.
    error_type:
        Error class name (e.g. ``"ObsidianCLIError"``).
    message:
        Human-readable error description.
    stderr:
        Raw stderr output from the subprocess, if any.
    exit_code:
        Process exit code, or ``None`` if not applicable.
    vault:
        Vault name used for the command, or ``None``.
    """
    return {
        "ok": False,
        "command": command,
        "vault": vault,
        "error": {
            "type": error_type,
            "message": message,
            "stderr": stderr,
            "exit_code": exit_code,
        },
    }


def format_output(envelope: dict, as_json: bool) -> str:
    """Render an envelope as a string for display.

    Parameters
    ----------
    envelope:
        A dict produced by :func:`success_envelope` or :func:`error_envelope`.
    as_json:
        If ``True``, return pretty-printed JSON.  Otherwise return a
        human-readable plain-text representation.
    """
    if as_json:
        return json.dumps(envelope, indent=2)

    if envelope.get("ok"):
        data = envelope.get("data")
        if isinstance(data, str):
            return data
        return json.dumps(data, indent=2)

    error = envelope.get("error", {})
    return error.get("message", "Unknown error")
