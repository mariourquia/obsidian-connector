"""Core wrapper functions around the Obsidian CLI."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

from obsidian_connector.config import load_config
from obsidian_connector.cache import CLICache

_cache = CLICache()

# Late imports for typed errors are done inside run_obsidian() to avoid
# circular imports (errors.py imports ObsidianCLIError from this module).


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Low-level helper
# ---------------------------------------------------------------------------

def run_obsidian(
    args: list[str],
    vault: str | None = None,
    timeout: int | None = None,
) -> str:
    """Run an Obsidian CLI command and return stdout.

    Parameters
    ----------
    args:
        Command and arguments, e.g. ``["daily:append", "content=hello"]``.
    vault:
        Optional vault name.  Prepended as ``vault=<name>``.
    timeout:
        Seconds before the subprocess is killed.  Falls back to config.
    """
    from obsidian_connector.errors import (
        CommandTimeout,
        ObsidianNotFound,
        ObsidianNotRunning,
        VaultNotFound,
    )

    cfg = load_config()
    _cache.ttl = cfg.cache_ttl
    cmd: list[str] = [cfg.obsidian_bin]
    effective_vault = vault or cfg.default_vault
    if effective_vault is not None:
        cmd.append(f"vault={effective_vault}")
    cmd.extend(args)

    # Cache: return cached result for read-only commands.
    if _cache.enabled and not _cache.is_mutation(args):
        cached = _cache.get(args, effective_vault)
        if cached is not None:
            return cached

    try:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout or cfg.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandTimeout(
            f"obsidian command timed out after {timeout or cfg.timeout_seconds}s: {cmd}"
        ) from exc
    except FileNotFoundError as exc:
        raise ObsidianNotFound(
            f"obsidian binary not found: {cfg.obsidian_bin}"
        ) from exc

    if result.returncode != 0:
        combined = (result.stderr + result.stdout).lower()
        if "not found" in combined or "no such file" in combined:
            if "vault" in combined:
                raise VaultNotFound(
                    f"vault not found: {result.stderr.strip() or result.stdout.strip()}"
                )
            if "not running" in combined or "ipc" in combined or "connect" in combined:
                raise ObsidianNotRunning(
                    f"Obsidian not running: {result.stderr.strip() or result.stdout.strip()}"
                )
            raise ObsidianNotFound(
                f"binary/resource not found: {result.stderr.strip() or result.stdout.strip()}"
            )
        raise ObsidianCLIError(
            command=cmd,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    # Soft errors: CLI exits 0 but stdout signals an error
    if result.stdout.startswith("Error:"):
        raise ObsidianCLIError(
            command=cmd,
            returncode=0,
            stdout=result.stdout,
            stderr=result.stdout,
        )

    stdout = result.stdout

    # Cache: store read results, invalidate on mutations.
    if _cache.enabled:
        if _cache.is_mutation(args):
            _cache.clear()
        else:
            _cache.put(args, effective_vault, stdout)

    return stdout


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_to_daily(content: str, vault: str | None = None) -> None:
    """Append *content* to today's daily note.

    Parameters
    ----------
    content:
        Markdown text to append.
    vault:
        Target vault name.  Falls back to the configured default.
    """
    # The CLI interprets \n as newline and \t as tab in content values.
    # It does NOT interpret \\ as a literal backslash, so we only encode
    # real newlines and tabs.  Literal \n or \t sequences in content are
    # ambiguous (a known CLI limitation).
    encoded = content.replace("\n", "\\n").replace("\t", "\\t")
    run_obsidian(["daily:append", f"content={encoded}"], vault=vault)


def search_notes(query: str, vault: str | None = None) -> list[dict]:
    """Full-text search across the vault using ``search:context``.

    Parameters
    ----------
    query:
        Search string.
    vault:
        Target vault name.

    Returns
    -------
    list[dict]
        Each dict has ``file`` (str) and ``matches`` (list of
        ``{"line": int, "text": str}``).
    """
    stdout = run_obsidian(
        ["search:context", f"query={query}", "format=json"],
        vault=vault,
    )
    stripped = stdout.strip()
    if not stripped or stripped.startswith("No "):
        return []
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ObsidianCLIError(
            command=["search:context"],
            returncode=0,
            stdout=stdout,
            stderr=f"Failed to parse JSON: {exc}",
        ) from exc
    if not isinstance(data, list):
        return [data] if isinstance(data, dict) else []
    return data


def read_note(name_or_path: str, vault: str | None = None) -> str:
    """Read and return the raw Markdown content of a note.

    Parameters
    ----------
    name_or_path:
        Wikilink-style name or exact vault-relative path.
        If the value contains ``/`` or ends with ``.md``, it is treated
        as a path; otherwise as a wikilink-style file name.
    vault:
        Target vault name.
    """
    is_path = "/" in name_or_path or name_or_path.endswith(".md")
    key = "path" if is_path else "file"
    return run_obsidian(["read", f"{key}={name_or_path}"], vault=vault)


def list_tasks(
    filter: dict | None = None, vault: str | None = None
) -> list[dict]:
    """List tasks from the vault, optionally filtered.

    Parameters
    ----------
    filter:
        Optional filter keys.  Supported:

        - ``"done"`` (bool) -- show completed tasks
        - ``"todo"`` (bool) -- show incomplete tasks
        - ``"status"`` (str) -- single-char status filter
        - ``"file"`` (str) -- filter by file name
        - ``"path"`` (str) -- filter by file path
        - ``"limit"`` (int) -- max results
    vault:
        Target vault name.

    Returns
    -------
    list[dict]
        Each dict contains ``text``, ``status``, ``file``, and ``line``.
    """
    args: list[str] = ["tasks", "format=json"]
    if filter:
        if filter.get("done"):
            args.append("done")
        if filter.get("todo"):
            args.append("todo")
        if "status" in filter:
            args.append(f'status="{filter["status"]}"')
        if "file" in filter:
            args.append(f"file={filter['file']}")
        if "path" in filter:
            args.append(f"path={filter['path']}")
        if "limit" in filter:
            args.append(f"limit={filter['limit']}")

    stdout = run_obsidian(args, vault=vault)
    stripped = stdout.strip()
    if not stripped or stripped.startswith("No "):
        return []
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ObsidianCLIError(
            command=args,
            returncode=0,
            stdout=stdout,
            stderr=f"Failed to parse JSON: {exc}",
        ) from exc
    if not isinstance(data, list):
        return [data] if isinstance(data, dict) else []
    return data


def batch_read_notes(
    paths: list[str],
    vault: str | None = None,
    max_concurrent: int = 4,
) -> dict[str, str]:
    """Read multiple notes with bounded concurrency.

    Uses :class:`concurrent.futures.ThreadPoolExecutor` with *max_concurrent*
    workers.  Falls back to sequential reads if any IPC error is detected.

    Parameters
    ----------
    paths:
        List of note names or vault-relative paths.
    vault:
        Target vault name.
    max_concurrent:
        Maximum worker threads (default 4).

    Returns
    -------
    dict[str, str]
        ``{path: content}`` dict.  Failed reads have an empty string value.
    """
    if not paths:
        return {}

    results: dict[str, str] = {}
    ipc_error_detected = False

    def _read_one(path: str) -> tuple[str, str]:
        nonlocal ipc_error_detected
        try:
            content = read_note(path, vault=vault)
            return (path, content)
        except ObsidianCLIError as exc:
            err_msg = str(exc).lower()
            if "ipc" in err_msg or "not running" in err_msg or "connect" in err_msg:
                ipc_error_detected = True
            return (path, "")

    # Try concurrent reads first.
    try:
        with ThreadPoolExecutor(max_workers=min(max_concurrent, len(paths))) as pool:
            futures = [pool.submit(_read_one, p) for p in paths]
            for future in futures:
                path, content = future.result()
                results[path] = content
    except Exception:
        # On any pool-level failure, fall back to sequential.
        ipc_error_detected = True

    # If IPC error was detected, fall back to sequential for any remaining
    # paths that weren't read successfully.
    if ipc_error_detected:
        for path in paths:
            if path not in results or results[path] == "":
                try:
                    results[path] = read_note(path, vault=vault)
                except ObsidianCLIError:
                    results[path] = ""

    return results
