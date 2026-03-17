"""Configuration loading for obsidian-connector.

Resolution order (highest wins):
    1. Explicit function argument  (handled in client.py / run_obsidian)
    2. Environment variable
    3. config.json value
    4. Built-in default
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from obsidian_connector.platform import obsidian_app_json_path, default_index_db_path

_CONFIG_FILENAME = "config.json"

_DEFAULT_INDEX_DB = default_index_db_path()

_OBSIDIAN_APP_JSON = obsidian_app_json_path()


def _find_config_file() -> Path | None:
    """Locate config.json -- check package parent directory, then CWD."""
    candidates = [
        Path(__file__).resolve().parent.parent / _CONFIG_FILENAME,
        Path.cwd() / _CONFIG_FILENAME,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_config_file() -> dict:
    """Read and parse config.json.  Returns ``{}`` when not found."""
    path = _find_config_file()
    if path is None:
        return {}
    with open(path) as f:
        return json.load(f)


@dataclass
class ConnectorConfig:
    """Runtime configuration resolved from env vars, config.json, and defaults."""

    obsidian_bin: str = "obsidian"
    default_vault: str | None = None
    timeout_seconds: int = 30
    daily_note_behavior: str = "append"
    default_folders: dict[str, str] = field(default_factory=dict)
    cache_ttl: int = 0
    vault_path: Path | None = None
    index_db_path: Path = field(default_factory=lambda: _DEFAULT_INDEX_DB)
    context_files: list[str] = field(default_factory=list)


def load_config() -> ConnectorConfig:
    """Build a ConnectorConfig by layering env vars over config.json."""
    file_cfg = _load_config_file()

    vault_path_str = os.getenv("OBSIDIAN_VAULT_PATH") or file_cfg.get("vault_path")
    vault_path = Path(vault_path_str) if vault_path_str else None

    index_db_str = os.getenv("OBSIDIAN_INDEX_DB") or file_cfg.get("index_db_path")
    index_db_path = Path(index_db_str) if index_db_str else _DEFAULT_INDEX_DB

    obsidian_bin = os.getenv("OBSIDIAN_BIN") or file_cfg.get("obsidian_bin", "obsidian")
    # Reject suspicious binary paths (defense in depth).
    if any(c in obsidian_bin for c in ";|&`$(){}!"):
        obsidian_bin = "obsidian"

    return ConnectorConfig(
        obsidian_bin=obsidian_bin,
        default_vault=os.getenv("OBSIDIAN_VAULT") or file_cfg.get("default_vault"),
        timeout_seconds=int(os.getenv("OBSIDIAN_TIMEOUT") or file_cfg.get("timeout_seconds", 30)),
        daily_note_behavior=file_cfg.get("daily_note_behavior", "append"),
        default_folders=file_cfg.get("default_folders", {}),
        cache_ttl=int(os.getenv("OBSIDIAN_CACHE_TTL") or file_cfg.get("cache_ttl", 0)),
        vault_path=vault_path,
        index_db_path=index_db_path,
        context_files=file_cfg.get("context_files", []),
    )


def resolve_vault_path(vault: str | None = None) -> Path:
    """Resolve the vault directory path.

    Resolution order:
        1. ``OBSIDIAN_VAULT_PATH`` environment variable
        2. Parse ``~/Library/Application Support/obsidian/obsidian.json``
           to find vault directories registered with the desktop app.
           If *vault* is given, match by name; otherwise use the first vault
           that matches the config.json ``default_vault``, or the first vault
           found.
        3. Raise ``VaultNotFound`` if nothing works.

    Parameters
    ----------
    vault:
        Vault name to match against Obsidian's registered vaults.
        Falls back to the ``default_vault`` from config.json.

    Returns
    -------
    Path
        Absolute path to the vault directory.

    Raises
    ------
    VaultNotFound
        When no vault can be resolved.
    """
    from obsidian_connector.errors import VaultNotFound

    # 1. Environment variable
    env_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_dir():
            return p
        raise VaultNotFound(f"OBSIDIAN_VAULT_PATH does not exist: {env_path}")

    # 2. Config vault_path field (only when no explicit vault name given)
    cfg = load_config()
    if vault is None and cfg.vault_path and cfg.vault_path.is_dir():
        return cfg.vault_path

    # 3. Parse Obsidian's obsidian.json
    target_name = vault or cfg.default_vault
    if _OBSIDIAN_APP_JSON.is_file():
        try:
            with open(_OBSIDIAN_APP_JSON) as f:
                app_cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            app_cfg = {}

        vaults = app_cfg.get("vaults", {})
        # Try to match by vault name (last path component)
        for _vid, vinfo in vaults.items():
            vpath = Path(vinfo.get("path", ""))
            if target_name and vpath.name == target_name and vpath.is_dir():
                return vpath

        # Fall back to first vault that exists
        for _vid, vinfo in vaults.items():
            vpath = Path(vinfo.get("path", ""))
            if vpath.is_dir():
                return vpath

    raise VaultNotFound(
        f"cannot resolve vault path (name={target_name!r}). "
        "Set OBSIDIAN_VAULT_PATH or configure vault_path in config.json."
    )
