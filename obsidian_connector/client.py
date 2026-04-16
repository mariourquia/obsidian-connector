"""Core wrapper functions around the Obsidian CLI."""

from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from obsidian_connector.cache import CLICache
from obsidian_connector.config import load_config
from obsidian_connector.errors import (
    ObsidianCLIError,
    CommandTimeout,
    ObsidianNotFound,
    ObsidianNotRunning,
    VaultNotFound,
)

_cache = CLICache()


def _resolve_retry_default() -> int:
    """Read ``OBSIDIAN_CLI_RETRIES`` env var with safe fallback."""
    raw = os.environ.get("OBSIDIAN_CLI_RETRIES", "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return max(0, value)


def _sleep(seconds: float) -> None:
    """Thin indirection so tests can monkeypatch the retry backoff."""
    if seconds > 0:
        time.sleep(seconds)


# ---------------------------------------------------------------------------
# Low-level helper
# ---------------------------------------------------------------------------

def run_obsidian(
    args: list[str],
    vault: str | None = None,
    timeout: int | None = None,
    retries: int | None = None,
    retry_backoff: float = 0.5,
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
    retries:
        How many times to re-invoke the Obsidian CLI on a transient
        ``ObsidianNotRunning`` before giving up. Defaults to
        ``OBSIDIAN_CLI_RETRIES`` env var (fallback 0). A value of 2
        means the call is attempted up to 3 times. Retries only fire
        for ``ObsidianNotRunning``; ``VaultNotFound`` / ``ObsidianNotFound``
        / ``CommandTimeout`` / other ``ObsidianCLIError`` instances all
        fail fast because retrying will not change the outcome.
    retry_backoff:
        Seconds between retry attempts (linear, not exponential --
        Obsidian typically either responds on the next tick or stays
        down). Default 0.5s.

    Action-hint injection: on ``ObsidianNotRunning`` the exception
    message now carries a one-line remediation hint (open Obsidian,
    or check that the CLI is enabled in Settings -> Community plugins ->
    Obsidian CLI). Callers rendering these errors to users can surface
    them directly without re-templating.
    """
    if retries is None:
        retries = _resolve_retry_default()
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

    last_not_running: ObsidianNotRunning | None = None
    attempts = max(1, retries + 1)
    for attempt in range(attempts):
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
                f"obsidian command timed out after {timeout or cfg.timeout_seconds}s: {cmd}. "
                f"Hint: Obsidian may be busy indexing; retry, or raise OBSIDIAN_TIMEOUT_SECONDS."
            ) from exc
        except FileNotFoundError as exc:
            raise ObsidianNotFound(
                f"obsidian binary not found at '{cfg.obsidian_bin}'. "
                f"Hint: install Obsidian (https://obsidian.md) or set OBSIDIAN_BIN to the absolute path "
                f"of the `obsidian` CLI."
            ) from exc

        if result.returncode != 0:
            combined = (result.stderr + result.stdout).lower()
            if "not found" in combined and "vault" in combined:
                raise VaultNotFound(
                    f"vault not found: {result.stderr.strip() or result.stdout.strip()}. "
                    f"Hint: list configured vaults with `obsidian vaults` or pass --vault=<name>."
                )
            if "not running" in combined or "ipc" in combined.lower() or "connect" in combined.lower():
                stderr_short = (result.stderr.strip() or result.stdout.strip())[:200]
                last_not_running = ObsidianNotRunning(
                    f"Obsidian not running or CLI unreachable: {stderr_short}. "
                    f"Hint: open the Obsidian desktop app (v1.12+) and enable the CLI in "
                    f"Settings -> Community plugins."
                )
                # Retry on transient ObsidianNotRunning only.
                if attempt < attempts - 1:
                    _sleep(retry_backoff)
                    continue
                raise last_not_running
            if "not found" in combined or "no such file" in combined:
                raise ObsidianNotFound(
                    f"binary/resource not found: {result.stderr.strip() or result.stdout.strip()}. "
                    f"Hint: verify the vault path and that Obsidian's CLI is on PATH."
                )
            raise ObsidianCLIError(
                command=cmd,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        # Success path (break out of retry loop).
        break

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
    failed: set[str] = set()
    ipc_error_detected = False

    def _read_one(path: str) -> tuple[str, str, bool]:
        try:
            content = read_note(path, vault=vault)
            return (path, content, False)
        except ObsidianCLIError as exc:
            err_msg = str(exc).lower()
            is_ipc = "ipc" in err_msg or "not running" in err_msg or "connect" in err_msg
            return (path, "", is_ipc)

    # Try concurrent reads first.
    try:
        with ThreadPoolExecutor(max_workers=min(max_concurrent, len(paths))) as pool:
            futures = [pool.submit(_read_one, p) for p in paths]
            for future in futures:
                path, content, is_ipc = future.result()
                results[path] = content
                if content == "" and is_ipc:
                    ipc_error_detected = True
                if content == "":
                    failed.add(path)
    except (OSError, RuntimeError):
        # Pool-level infrastructure failure -- fall back to sequential.
        ipc_error_detected = True

    # If IPC error was detected, retry only failed paths sequentially.
    if ipc_error_detected:
        for path in paths:
            if path in failed or path not in results:
                try:
                    results[path] = read_note(path, vault=vault)
                except ObsidianCLIError:
                    results[path] = ""

    return results
