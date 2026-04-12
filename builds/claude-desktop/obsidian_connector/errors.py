"""Typed exception hierarchy for obsidian-connector.

All exceptions live here. ``ObsidianCLIError`` is the base class.
"""

from __future__ import annotations


class ObsidianCLIError(Exception):
    """Raised when the Obsidian CLI exits with a non-zero code."""

    def __init__(
        self, command: list[str], returncode: int, stdout: str, stderr: str
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        detail = stderr.strip() or stdout.strip()
        super().__init__(
            f"obsidian exited {returncode}: {detail!r}\n"
            f"  command: {command}"
        )


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


class ProtectedFolderError(ObsidianCLIError):
    """Write attempted to a protected folder without --force."""

    def __init__(self, message: str = "write to protected folder denied") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=1,
            stdout="",
            stderr=message,
        )


class WriteLockError(ObsidianCLIError):
    """Could not acquire file lock within timeout."""

    def __init__(self, message: str = "failed to acquire file lock") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=1,
            stdout="",
            stderr=message,
        )


class RollbackError(ObsidianCLIError):
    """Snapshot restore failed."""

    def __init__(self, message: str = "rollback failed") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=1,
            stdout="",
            stderr=message,
        )
