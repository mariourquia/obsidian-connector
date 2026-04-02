"""Negative tests for config.py -- malformed input, missing fields, invalid values.

These tests verify that the config module handles bad input gracefully
rather than propagating cryptic errors to the user.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from obsidian_connector.config import (
    ConnectorConfig,
    _find_config_file,
    _load_config_file,
    load_config,
    resolve_vault_path,
)


# ---------------------------------------------------------------------------
# Malformed JSON
# ---------------------------------------------------------------------------


class TestMalformedJSON:
    """Config loader must degrade gracefully on invalid JSON (returns {})."""

    def test_trailing_comma(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text('{"default_vault": "test",}')
        with patch(
            "obsidian_connector.config._find_config_file", return_value=cfg
        ):
            result = _load_config_file()
            assert result == {}

    def test_missing_closing_brace(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text('{"default_vault": "test"')
        with patch(
            "obsidian_connector.config._find_config_file", return_value=cfg
        ):
            result = _load_config_file()
            assert result == {}

    def test_empty_file(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text("")
        with patch(
            "obsidian_connector.config._find_config_file", return_value=cfg
        ):
            result = _load_config_file()
            assert result == {}

    def test_plain_string_not_object(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text('"just a string"')
        with patch(
            "obsidian_connector.config._find_config_file", return_value=cfg
        ):
            # Not a dict -- config loader returns {} for non-dict results
            result = _load_config_file()
            assert result == {}


# ---------------------------------------------------------------------------
# Missing / absent config
# ---------------------------------------------------------------------------


class TestMissingConfig:
    """When config.json is absent, defaults must be used."""

    def test_no_config_file_returns_empty_dict(self) -> None:
        with patch(
            "obsidian_connector.config._find_config_file", return_value=None
        ):
            assert _load_config_file() == {}

    def test_load_config_with_no_file_uses_defaults(self) -> None:
        with patch(
            "obsidian_connector.config._find_config_file", return_value=None
        ):
            cfg = load_config()
            assert cfg.obsidian_bin == "obsidian"
            assert cfg.default_vault is None
            assert cfg.timeout_seconds == 30
            assert cfg.daily_note_behavior == "append"
            assert cfg.cache_ttl == 0

    def test_missing_default_vault_key(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text('{"timeout_seconds": 15}')
        with patch(
            "obsidian_connector.config._find_config_file", return_value=cfg_file
        ):
            cfg = load_config()
            assert cfg.default_vault is None
            assert cfg.timeout_seconds == 15


# ---------------------------------------------------------------------------
# vault_path with tilde
# ---------------------------------------------------------------------------


class TestTildeExpansion:
    """vault_path containing ~ should be expanded."""

    def test_tilde_in_vault_path_via_env(self, tmp_path: Path) -> None:
        # Create a real directory to stand in for ~/my-vault
        vault_dir = tmp_path / "my-vault"
        vault_dir.mkdir()

        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}):
            result = resolve_vault_path()
            assert result == vault_dir

    def test_tilde_expansion_in_env_var(self, tmp_path: Path) -> None:
        # The resolve_vault_path function calls Path.expanduser()
        # Verify it handles ~/ prefix without crashing
        with patch.dict(
            os.environ, {"OBSIDIAN_VAULT_PATH": "~/nonexistent-test-vault-xyzzy"}
        ):
            from obsidian_connector.errors import VaultNotFound

            with pytest.raises(VaultNotFound):
                resolve_vault_path()


# ---------------------------------------------------------------------------
# Nonexistent vault_path
# ---------------------------------------------------------------------------


class TestNonexistentVaultPath:
    """vault_path pointing to missing directory must raise VaultNotFound."""

    def test_env_var_nonexistent_dir(self) -> None:
        from obsidian_connector.errors import VaultNotFound

        with patch.dict(
            os.environ,
            {"OBSIDIAN_VAULT_PATH": "/tmp/absolutely-does-not-exist-oc-test"},
        ):
            with pytest.raises(VaultNotFound):
                resolve_vault_path()


# ---------------------------------------------------------------------------
# Invalid timeout_seconds
# ---------------------------------------------------------------------------


class TestInvalidTimeoutSeconds:
    """timeout_seconds must be coerced to int; bad values should surface clearly."""

    def test_negative_timeout(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text('{"timeout_seconds": -5}')
        with patch(
            "obsidian_connector.config._find_config_file", return_value=cfg_file
        ):
            cfg = load_config()
            # Negative value is loaded as-is (no validation clamp).
            # This test documents current behavior.
            assert cfg.timeout_seconds == -5

    def test_string_timeout_via_env(self) -> None:
        with patch.dict(os.environ, {"OBSIDIAN_TIMEOUT": "not_a_number"}):
            cfg = load_config()
            # _safe_int returns default (30) for non-numeric strings
            assert cfg.timeout_seconds == 30

    def test_string_timeout_in_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text('{"timeout_seconds": "thirty"}')
        with patch(
            "obsidian_connector.config._find_config_file", return_value=cfg_file
        ):
            cfg = load_config()
            # _safe_int returns default (30) for non-numeric strings
            assert cfg.timeout_seconds == 30

    def test_zero_timeout(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text('{"timeout_seconds": 0}')
        with patch(
            "obsidian_connector.config._find_config_file", return_value=cfg_file
        ):
            cfg = load_config()
            assert cfg.timeout_seconds == 0


# ---------------------------------------------------------------------------
# Suspicious obsidian_bin (injection defense)
# ---------------------------------------------------------------------------


class TestObsidianBinSanitization:
    """obsidian_bin with shell metacharacters must be rejected."""

    @pytest.mark.parametrize(
        "bad_bin",
        [
            "obsidian; rm -rf /",
            "obsidian | cat /etc/passwd",
            "obsidian && echo pwned",
            "$(whoami)",
            "obsidian`id`",
        ],
    )
    def test_shell_metachar_rejected(self, bad_bin: str, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"obsidian_bin": bad_bin}))
        with patch(
            "obsidian_connector.config._find_config_file", return_value=cfg_file
        ):
            cfg = load_config()
            assert cfg.obsidian_bin == "obsidian"  # Falls back to safe default
