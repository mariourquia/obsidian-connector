"""Named vault registry with profiles and per-vault policies.

Provides persistent multi-vault management. Each vault has a name,
filesystem path, profile (personal|work|research|creative), and
optional policies (protected_folders, draft_max_age_days, watcher_enabled).

Registry persists to ``~/.config/obsidian-connector/vaults.json`` on
macOS/Linux or ``%APPDATA%/obsidian-connector/vaults.json`` on Windows.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from obsidian_connector.errors import VaultNotFound

# ---------------------------------------------------------------------------
# Valid profiles
# ---------------------------------------------------------------------------

VALID_PROFILES = frozenset({"personal", "work", "research", "creative"})

_REGISTRY_VERSION = 1
_REGISTRY_FILENAME = "vaults.json"


# ---------------------------------------------------------------------------
# Cross-platform config directory resolution
# ---------------------------------------------------------------------------

def _default_registry_dir() -> Path:
    """Return the platform-appropriate config directory for the registry.

    macOS/Linux: ``~/.config/obsidian-connector/``
    Windows:     ``%APPDATA%/obsidian-connector/``
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "obsidian-connector"


# ---------------------------------------------------------------------------
# VaultEntry dataclass
# ---------------------------------------------------------------------------

@dataclass
class VaultEntry:
    """A single registered vault."""

    name: str
    path: str
    is_default: bool = False
    profile: str = "personal"
    policies: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VaultEntry:
        return cls(
            name=data["name"],
            path=data["path"],
            is_default=data.get("is_default", False),
            profile=data.get("profile", "personal"),
            policies=data.get("policies", {}),
        )


# ---------------------------------------------------------------------------
# VaultRegistry
# ---------------------------------------------------------------------------

class VaultRegistry:
    """Named vault registry backed by a JSON file.

    Parameters
    ----------
    registry_path:
        Explicit path to the registry JSON file. When ``None``,
        defaults to the platform-appropriate config directory.
    """

    def __init__(self, registry_path: str | Path | None = None) -> None:
        if registry_path is not None:
            self._path = Path(registry_path)
        else:
            self._path = _default_registry_dir() / _REGISTRY_FILENAME

        self._vaults: list[VaultEntry] = []
        self.load()

    # -- persistence --------------------------------------------------------

    def load(self) -> None:
        """Read vaults from the JSON file. Create file if missing."""
        if not self._path.is_file():
            self._vaults = []
            self.save()
            return

        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._vaults = []
            return

        self._vaults = [
            VaultEntry.from_dict(v) for v in data.get("vaults", [])
        ]

    def save(self) -> None:
        """Persist current state to JSON."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _REGISTRY_VERSION,
            "vaults": [v.to_dict() for v in self._vaults],
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    # -- registration -------------------------------------------------------

    def register(
        self,
        name: str,
        path: str | Path,
        profile: str = "personal",
        is_default: bool = False,
    ) -> VaultEntry:
        """Add a vault to the registry.

        Parameters
        ----------
        name:
            Unique vault identifier.
        path:
            Filesystem path to the vault directory. Must exist.
        profile:
            One of ``personal``, ``work``, ``research``, ``creative``.
        is_default:
            If ``True``, this vault becomes the default (unsetting any
            previous default).

        Raises
        ------
        FileNotFoundError
            When *path* does not exist on disk.
        ValueError
            When *profile* is not one of the valid profiles, or when
            a vault with the same *name* is already registered.
        """
        resolved = Path(path).expanduser()
        if not resolved.is_dir():
            raise FileNotFoundError(f"Vault path does not exist: {resolved}")

        if profile not in VALID_PROFILES:
            raise ValueError(
                f"Invalid profile {profile!r}. "
                f"Must be one of: {', '.join(sorted(VALID_PROFILES))}"
            )

        # Duplicate name check
        for v in self._vaults:
            if v.name == name:
                raise ValueError(f"Vault {name!r} is already registered")

        if is_default:
            self._clear_default()

        entry = VaultEntry(
            name=name,
            path=str(resolved),
            is_default=is_default,
            profile=profile,
        )
        self._vaults.append(entry)
        self.save()
        return entry

    def unregister(self, name: str) -> None:
        """Remove a vault from the registry.

        Raises
        ------
        VaultNotFound
            When no vault with *name* is registered.
        """
        for i, v in enumerate(self._vaults):
            if v.name == name:
                self._vaults.pop(i)
                self.save()
                return
        raise VaultNotFound(f"Vault {name!r} is not registered")

    # -- lookup -------------------------------------------------------------

    def get(self, name: str) -> VaultEntry:
        """Return the VaultEntry for *name*.

        Raises
        ------
        VaultNotFound
            When no vault with *name* is registered.
        """
        for v in self._vaults:
            if v.name == name:
                return v
        raise VaultNotFound(f"Vault {name!r} is not registered")

    def get_default(self) -> VaultEntry | None:
        """Return the default vault, or ``None`` if no default is set."""
        for v in self._vaults:
            if v.is_default:
                return v
        return None

    def set_default(self, name: str) -> None:
        """Set *name* as the default vault.

        Raises
        ------
        VaultNotFound
            When no vault with *name* is registered.
        """
        found = False
        for v in self._vaults:
            if v.name == name:
                found = True
                break
        if not found:
            raise VaultNotFound(f"Vault {name!r} is not registered")

        self._clear_default()
        for v in self._vaults:
            if v.name == name:
                v.is_default = True
                break
        self.save()

    def list_vaults(self) -> list[VaultEntry]:
        """Return all registered VaultEntry objects."""
        return list(self._vaults)

    def find_by_path(self, path: str | Path) -> VaultEntry | None:
        """Look up a vault by its filesystem path.

        Returns ``None`` when no vault matches.
        """
        resolved = str(Path(path).expanduser().resolve())
        for v in self._vaults:
            if str(Path(v.path).resolve()) == resolved:
                return v
        return None

    # -- policies -----------------------------------------------------------

    def update_policies(self, name: str, policies: dict[str, Any]) -> VaultEntry:
        """Merge policy overrides for a vault.

        Existing policy keys are overwritten by *policies*; keys not
        present in *policies* are preserved.

        Raises
        ------
        VaultNotFound
            When no vault with *name* is registered.
        """
        entry = self.get(name)  # raises VaultNotFound
        entry.policies.update(policies)
        self.save()
        return entry

    # -- selectors ----------------------------------------------------------

    def get_vault_names(self, selector: str) -> list[str]:
        """Parse a vault selector string and return matching vault names.

        Selector formats:
        - ``"all"`` -- returns all vault names
        - ``"personal,research"`` -- returns vaults whose profile matches
          any of the comma-separated values (profile-based filtering)
        - ``"work"`` -- single profile filter

        When a selector token does not match a valid profile, it is
        treated as a vault name for exact matching.
        """
        selector = selector.strip()
        if selector.lower() == "all":
            return [v.name for v in self._vaults]

        tokens = [t.strip() for t in selector.split(",") if t.strip()]
        result: list[str] = []

        for token in tokens:
            if token in VALID_PROFILES:
                # Profile-based selection
                for v in self._vaults:
                    if v.profile == token and v.name not in result:
                        result.append(v.name)
            else:
                # Exact vault name match
                for v in self._vaults:
                    if v.name == token and v.name not in result:
                        result.append(v.name)

        return result

    # -- health check -------------------------------------------------------

    def doctor(self) -> list[str]:
        """Check all registered vaults exist on disk.

        Returns a list of human-readable issue strings.  An empty list
        means everything is healthy.
        """
        issues: list[str] = []
        for v in self._vaults:
            if not Path(v.path).is_dir():
                issues.append(
                    f"Vault {v.name!r} path does not exist: {v.path}"
                )
        return issues

    # -- internal helpers ---------------------------------------------------

    def _clear_default(self) -> None:
        """Unset the is_default flag on all vaults."""
        for v in self._vaults:
            v.is_default = False
