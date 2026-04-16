"""Tests for the v0.11 doctor extensions."""
from __future__ import annotations

import sys
from collections import namedtuple
from types import SimpleNamespace

_VersionInfo = namedtuple("_VersionInfo", "major minor micro releaselevel serial")


def _mkver(major: int, minor: int, micro: int = 0) -> _VersionInfo:
    return _VersionInfo(major, minor, micro, "final", 0)

import pytest

from obsidian_connector import doctor as doctor_mod


# ---------------------------------------------------------------------------
# Python runtime check
# ---------------------------------------------------------------------------


def test_python_runtime_ok_on_current_interpreter(monkeypatch):
    """The running interpreter must itself satisfy the check (>= 3.11)."""
    monkeypatch.setattr(sys, "version_info", _mkver(3, 12, 1))
    result = doctor_mod._check_python_runtime("macos")
    assert result["ok"] is True
    assert "Python" in result["detail"]


def test_python_runtime_flags_old_python(monkeypatch):
    monkeypatch.setattr(sys, "version_info", _mkver(3, 9, 0))
    result = doctor_mod._check_python_runtime("macos")
    assert result["ok"] is False
    assert "3.11" in result["action"]


def test_python_runtime_detects_microsoft_store_stub(monkeypatch):
    monkeypatch.setattr(
        sys,
        "executable",
        r"C:\Users\mario\AppData\Local\Microsoft\WindowsApps\python.exe",
    )
    monkeypatch.setattr(sys, "version_info", _mkver(3, 12, 0))
    result = doctor_mod._check_python_runtime("windows")
    assert result["ok"] is False
    assert "stub" in result["detail"].lower()
    assert "python.org" in result["action"].lower() or "winget" in result["action"].lower()


def test_python_runtime_ignores_store_path_on_non_windows(monkeypatch):
    """The `windowsapps` path substring should NOT trigger the stub
    detection on non-Windows (someone might have that literal string
    in their macOS path; no reason to fail)."""
    monkeypatch.setattr(
        sys,
        "executable",
        "/Users/me/WindowsApps-foo-bar/python",
    )
    monkeypatch.setattr(sys, "version_info", _mkver(3, 12, 0))
    result = doctor_mod._check_python_runtime("macos")
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# Node runtime check
# ---------------------------------------------------------------------------


def test_node_runtime_detects_missing_node(monkeypatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: None)
    result = doctor_mod._check_node_runtime()
    assert result["ok"] is False
    assert "nodejs.org" in result["action"].lower() or "install" in result["action"].lower()


def test_node_runtime_detects_present_node(monkeypatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "/opt/node/bin/node")

    class _Proc:
        returncode = 0
        stdout = "v20.10.0\n"
        stderr = ""

    monkeypatch.setattr(doctor_mod.subprocess, "run", lambda *a, **kw: _Proc())
    result = doctor_mod._check_node_runtime()
    assert result["ok"] is True
    assert "v20.10.0" in result["detail"]


def test_node_runtime_tolerates_version_probe_failure(monkeypatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "/opt/node/bin/node")

    def boom(*a, **kw):
        raise RuntimeError("node went boom")

    monkeypatch.setattr(doctor_mod.subprocess, "run", boom)
    result = doctor_mod._check_node_runtime()
    assert result["ok"] is False
    assert "failed" in result["detail"].lower() or "boom" in result["detail"]


# ---------------------------------------------------------------------------
# Textual check
# ---------------------------------------------------------------------------


def test_textual_detects_present(monkeypatch):
    import importlib

    original = importlib.import_module

    def fake(name, *a, **kw):
        if name == "textual":
            return SimpleNamespace()
        return original(name, *a, **kw)

    monkeypatch.setattr("importlib.import_module", fake)
    result = doctor_mod._check_textual_available()
    assert result["ok"] is True


def test_textual_detects_missing(monkeypatch):
    import importlib

    original = importlib.import_module

    def fake(name, *a, **kw):
        if name == "textual":
            raise ImportError("no textual")
        return original(name, *a, **kw)

    monkeypatch.setattr("importlib.import_module", fake)
    result = doctor_mod._check_textual_available()
    assert result["ok"] is False
    assert "textual" in result["action"].lower()


# ---------------------------------------------------------------------------
# iCloud / sync-root detection
# ---------------------------------------------------------------------------


def test_icloud_detection_surfaces_icloud_path():
    hint = "~/Library/Mobile Documents/com~apple~CloudDocs/MyVault"
    result = doctor_mod._check_icloud_vault_path(hint, "macos")
    assert result["ok"] is True
    assert "iCloud" in result["detail"]
    assert "shared_vault.md" in result["action"]


def test_icloud_detection_surfaces_dropbox_path():
    result = doctor_mod._check_icloud_vault_path("/Users/me/Dropbox/MyVault", "macos")
    assert result["ok"] is True
    assert "Dropbox" in result["detail"]


def test_icloud_detection_surfaces_onedrive_path():
    result = doctor_mod._check_icloud_vault_path(
        r"C:\Users\me\OneDrive\MyVault", "windows"
    )
    assert result["ok"] is True
    assert "OneDrive" in result["detail"]


def test_icloud_detection_clean_on_local_path():
    result = doctor_mod._check_icloud_vault_path("/Users/me/vaults/local", "macos")
    assert result["ok"] is True
    assert "not under" in result["detail"].lower()


def test_icloud_detection_returns_none_on_empty_hint():
    """No vault hint -> skip this check entirely (covered upstream by vault_resolution)."""
    assert doctor_mod._check_icloud_vault_path(None, "macos") is None
    assert doctor_mod._check_icloud_vault_path("", "macos") is None


# ---------------------------------------------------------------------------
# Full Disk Access hint
# ---------------------------------------------------------------------------


def test_full_disk_access_hint_always_ok():
    """Cannot introspect TCC grants; always informational."""
    result = doctor_mod._check_full_disk_access_hint()
    assert result["ok"] is True
    assert "Full Disk Access" in result["action"]


# ---------------------------------------------------------------------------
# Integration: run_doctor returns the new checks
# ---------------------------------------------------------------------------


def test_run_doctor_includes_new_checks():
    results = doctor_mod.run_doctor()
    check_names = {r["check"] for r in results}
    # New v0.11 checks:
    assert "python_runtime" in check_names
    assert "node_runtime" in check_names
    assert "textual_available" in check_names
    # Legacy checks still present:
    assert "platform" in check_names
    assert "obsidian_binary" in check_names
    assert "platform_features" in check_names
