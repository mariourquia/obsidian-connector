"""Typed exception hierarchy for obsidian-connector.

All exceptions subclass ``ObsidianCLIError`` from ``client.py`` so that
existing ``except ObsidianCLIError`` handlers continue to work.
"""

from __future__ import annotations

from obsidian_connector.client import ObsidianCLIError


class ObsidianNotFound(ObsidianCLIError):
    """The ``obsidian`` binary is not on PATH."""

    def __init__(self, message: str = "obsidian binary not found on PATH") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=127,
            stdout="",
            stderr=message,
        )


class ObsidianNotRunning(ObsidianCLIError):
    """Obsidian app is not open / IPC unavailable."""

    def __init__(
        self, message: str = "Obsidian is not running (IPC unavailable)"
    ) -> None:
        super().__init__(
            command=["obsidian"],
            returncode=1,
            stdout="",
            stderr=message,
        )


class VaultNotFound(ObsidianCLIError):
    """The specified vault does not exist."""

    def __init__(self, message: str = "specified vault not found") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=1,
            stdout="",
            stderr=message,
        )


class CommandTimeout(ObsidianCLIError):
    """The subprocess timed out."""

    def __init__(self, message: str = "obsidian command timed out") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=-1,
            stdout="",
            stderr=message,
        )


class MalformedCLIOutput(ObsidianCLIError):
    """JSON parse failure on CLI stdout."""

    def __init__(self, message: str = "failed to parse CLI output as JSON") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=0,
            stdout="",
            stderr=message,
        )
