"""Tests for run_obsidian retry + error-message hint logic (v0.11)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from obsidian_connector import client as client_mod
from obsidian_connector.errors import (
    ObsidianNotFound,
    ObsidianNotRunning,
    VaultNotFound,
)


@pytest.fixture
def _cfg(monkeypatch):
    """Inject a stable config so tests don't read the user's real one."""
    cfg = SimpleNamespace(
        obsidian_bin="obsidian",
        default_vault=None,
        cache_ttl=0,
        timeout_seconds=5,
    )
    monkeypatch.setattr(client_mod, "load_config", lambda: cfg)
    # Cache side effects: force a fresh cache per test to avoid stale hits.
    client_mod._cache.clear()
    yield cfg


def _fake_run_factory(results: list):
    """Return a subprocess.run stand-in that yields successive results."""
    calls = {"n": 0}

    def fake(cmd, **kwargs):
        idx = calls["n"]
        calls["n"] += 1
        out = results[min(idx, len(results) - 1)]
        if isinstance(out, BaseException):
            raise out
        return out

    fake.calls = calls  # type: ignore[attr-defined]
    return fake


class _CP:
    """Minimal subprocess.CompletedProcess stand-in."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# Retry behavior
# ---------------------------------------------------------------------------


def test_retry_succeeds_after_transient_not_running(_cfg, monkeypatch):
    """A transient 'Obsidian not running' error is retried and succeeds."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return _CP(1, stderr="IPC connect failed: Obsidian not running")
        return _CP(0, stdout="files: 42\n")

    monkeypatch.setattr(client_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(client_mod, "_sleep", lambda _: None)

    out = client_mod.run_obsidian(["files", "total"], retries=1)
    assert out == "files: 42\n"
    assert len(calls) == 2


def test_retry_exhausted_raises_with_hint(_cfg, monkeypatch):
    """After retries exhaust, ObsidianNotRunning carries the open-Obsidian hint."""
    monkeypatch.setattr(
        client_mod.subprocess,
        "run",
        lambda cmd, **kwargs: _CP(1, stderr="Could not connect via IPC"),
    )
    monkeypatch.setattr(client_mod, "_sleep", lambda _: None)

    with pytest.raises(ObsidianNotRunning) as exc:
        client_mod.run_obsidian(["files", "total"], retries=2)
    msg = str(exc.value)
    assert "Hint" in msg
    assert "open the Obsidian desktop app" in msg.lower() or "obsidian" in msg.lower()


def test_no_retry_for_vault_not_found(_cfg, monkeypatch):
    """VaultNotFound fails fast; retries do not fire."""
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        return _CP(1, stderr="Error: vault not found")

    monkeypatch.setattr(client_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(client_mod, "_sleep", lambda _: None)

    with pytest.raises(VaultNotFound):
        client_mod.run_obsidian(["files", "total"], retries=5)
    assert calls["n"] == 1


def test_retries_default_to_zero_when_env_missing(_cfg, monkeypatch):
    """OBSIDIAN_CLI_RETRIES unset -> 0 retries."""
    monkeypatch.delenv("OBSIDIAN_CLI_RETRIES", raising=False)
    assert client_mod._resolve_retry_default() == 0


def test_retries_read_from_env(monkeypatch):
    monkeypatch.setenv("OBSIDIAN_CLI_RETRIES", "3")
    assert client_mod._resolve_retry_default() == 3


def test_negative_retries_clamped_to_zero(monkeypatch):
    monkeypatch.setenv("OBSIDIAN_CLI_RETRIES", "-5")
    assert client_mod._resolve_retry_default() == 0


def test_garbage_retries_env_falls_back(monkeypatch):
    monkeypatch.setenv("OBSIDIAN_CLI_RETRIES", "not-a-number")
    assert client_mod._resolve_retry_default() == 0


# ---------------------------------------------------------------------------
# Error message hint injection
# ---------------------------------------------------------------------------


def test_obsidian_not_found_hint_includes_bin_path(_cfg, monkeypatch):
    """FileNotFoundError on subprocess -> ObsidianNotFound with bin path + hint."""

    def boom(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(client_mod.subprocess, "run", boom)
    with pytest.raises(ObsidianNotFound) as exc:
        client_mod.run_obsidian(["files", "total"])
    assert "OBSIDIAN_BIN" in str(exc.value) or "obsidian" in str(exc.value).lower()
    assert "Hint" in str(exc.value)


def test_vault_not_found_hint_suggests_vaults_cmd(_cfg, monkeypatch):
    monkeypatch.setattr(
        client_mod.subprocess,
        "run",
        lambda cmd, **kwargs: _CP(1, stderr="Error: vault not found"),
    )
    with pytest.raises(VaultNotFound) as exc:
        client_mod.run_obsidian(["files", "total"])
    assert "vaults" in str(exc.value) or "Hint" in str(exc.value)


def test_timeout_hint_mentions_env_knob(_cfg, monkeypatch):
    import subprocess as _sp

    def boom(cmd, **kwargs):
        raise _sp.TimeoutExpired(cmd, timeout=5)

    monkeypatch.setattr(client_mod.subprocess, "run", boom)
    from obsidian_connector.errors import CommandTimeout

    with pytest.raises(CommandTimeout) as exc:
        client_mod.run_obsidian(["files", "total"])
    assert "OBSIDIAN_TIMEOUT_SECONDS" in str(exc.value) or "retry" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Backoff sleep is invoked between retries
# ---------------------------------------------------------------------------


def test_sleep_is_called_between_retries(_cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(
        client_mod.subprocess,
        "run",
        lambda cmd, **kwargs: _CP(1, stderr="IPC not running"),
    )
    monkeypatch.setattr(client_mod, "_sleep", lambda n: calls.append(n))

    with pytest.raises(ObsidianNotRunning):
        client_mod.run_obsidian(["files", "total"], retries=2, retry_backoff=0.1)
    # 2 retries -> 2 sleeps (between attempts 1-2 and 2-3).
    assert calls == [0.1, 0.1]


def test_sleep_not_called_without_retries(_cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(
        client_mod.subprocess,
        "run",
        lambda cmd, **kwargs: _CP(1, stderr="IPC not running"),
    )
    monkeypatch.setattr(client_mod, "_sleep", lambda n: calls.append(n))

    with pytest.raises(ObsidianNotRunning):
        client_mod.run_obsidian(["files", "total"], retries=0)
    assert calls == []


# ---------------------------------------------------------------------------
# Backward compatibility: the happy path
# ---------------------------------------------------------------------------


def test_happy_path_no_retries(_cfg, monkeypatch):
    monkeypatch.setattr(
        client_mod.subprocess, "run", lambda cmd, **kwargs: _CP(0, stdout="ok\n")
    )
    out = client_mod.run_obsidian(["files", "total"])
    assert out == "ok\n"
