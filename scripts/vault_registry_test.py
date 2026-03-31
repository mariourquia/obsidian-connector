#!/usr/bin/env python3
"""Validate the VaultRegistry module -- multi-vault support (Milestone B2)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.errors import VaultNotFound
from obsidian_connector.vault_registry import (
    VALID_PROFILES,
    VaultEntry,
    VaultRegistry,
)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}")
        FAIL += 1


def main() -> int:
    # All tests use a temporary directory so we never touch real config.
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_file = Path(tmpdir) / "vaults.json"
        vault_a = Path(tmpdir) / "vault_a"
        vault_b = Path(tmpdir) / "vault_b"
        vault_c = Path(tmpdir) / "vault_c"
        vault_a.mkdir()
        vault_b.mkdir()
        vault_c.mkdir()

        # -- Test 1: Registry creates file on first init -------------------
        print("\n--- Registry creates file on first init ---")
        reg = VaultRegistry(registry_path=registry_file)
        check("registry file exists", registry_file.is_file())

        # -- Test 2: Registry file has version field -----------------------
        print("\n--- Registry file format has version field ---")
        with open(registry_file) as f:
            raw = json.load(f)
        check("version key exists", "version" in raw)
        check("version is 1", raw["version"] == 1)

        # -- Test 3: register adds vault entry -----------------------------
        print("\n--- register adds vault entry ---")
        entry = reg.register("alpha", str(vault_a), profile="personal")
        check("returned VaultEntry name", entry.name == "alpha")
        check("list_vaults has 1 entry", len(reg.list_vaults()) == 1)

        # -- Test 4: register validates path exists ------------------------
        print("\n--- register validates path exists ---")
        bad_path = Path(tmpdir) / "nonexistent"
        try:
            reg.register("ghost", str(bad_path))
            check("raises for missing path", False)
        except FileNotFoundError:
            check("raises for missing path", True)

        # -- Test 5: register with is_default unsets previous default ------
        print("\n--- register with is_default unsets previous default ---")
        reg.register("beta", str(vault_b), profile="work", is_default=True)
        reg.register("gamma", str(vault_c), profile="research", is_default=True)
        check("gamma is default", reg.get_default().name == "gamma")
        check("beta lost default", reg.get("beta").is_default is False)

        # -- Test 6: unregister removes vault ------------------------------
        print("\n--- unregister removes vault ---")
        reg.unregister("gamma")
        check("list_vaults has 2 entries", len(reg.list_vaults()) == 2)

        # -- Test 7: unregister of nonexistent vault raises error ----------
        print("\n--- unregister of nonexistent vault raises error ---")
        try:
            reg.unregister("nope")
            check("raises VaultNotFound", False)
        except VaultNotFound:
            check("raises VaultNotFound", True)

        # -- Test 8: get returns correct VaultEntry ------------------------
        print("\n--- get returns correct VaultEntry ---")
        got = reg.get("alpha")
        check("get name matches", got.name == "alpha")
        check("get path matches", got.path == str(vault_a))
        check("get profile matches", got.profile == "personal")

        # -- Test 9: get of nonexistent vault raises VaultNotFound ---------
        print("\n--- get of nonexistent vault raises VaultNotFound ---")
        try:
            reg.get("missing")
            check("raises VaultNotFound", False)
        except VaultNotFound:
            check("raises VaultNotFound", True)

        # -- Test 10: get_default returns default vault --------------------
        print("\n--- get_default returns default vault ---")
        reg.set_default("beta")
        default = reg.get_default()
        check("get_default returns beta", default is not None and default.name == "beta")

        # -- Test 11: get_default returns None when no default -------------
        print("\n--- get_default returns None when no default ---")
        # Create a fresh registry with no defaults
        reg2_file = Path(tmpdir) / "vaults2.json"
        reg2 = VaultRegistry(registry_path=reg2_file)
        reg2.register("solo", str(vault_a), profile="personal", is_default=False)
        check("get_default is None", reg2.get_default() is None)

        # -- Test 12: set_default changes default --------------------------
        print("\n--- set_default changes default ---")
        reg.set_default("alpha")
        check("alpha is now default", reg.get_default().name == "alpha")
        check("beta lost default", reg.get("beta").is_default is False)

        # -- Test 13: list_vaults returns all entries ----------------------
        print("\n--- list_vaults returns all entries ---")
        all_vaults = reg.list_vaults()
        names = {v.name for v in all_vaults}
        check("alpha in list", "alpha" in names)
        check("beta in list", "beta" in names)

        # -- Test 14: find_by_path finds vault by path ---------------------
        print("\n--- find_by_path finds vault by path ---")
        found = reg.find_by_path(str(vault_a))
        check("find_by_path returns alpha", found is not None and found.name == "alpha")

        # -- Test 15: find_by_path returns None for unknown path -----------
        print("\n--- find_by_path returns None for unknown path ---")
        unknown = reg.find_by_path("/tmp/not_a_vault_12345")
        check("find_by_path returns None", unknown is None)

        # -- Test 16: update_policies merges correctly ---------------------
        print("\n--- update_policies merges correctly ---")
        reg.update_policies("alpha", {"protected_folders": ["Archive/"]})
        reg.update_policies("alpha", {"draft_max_age_days": 14})
        entry_a = reg.get("alpha")
        check("protected_folders preserved", entry_a.policies.get("protected_folders") == ["Archive/"])
        check("draft_max_age_days added", entry_a.policies.get("draft_max_age_days") == 14)

        # -- Test 17: get_vault_names("all") returns all names -------------
        print('\n--- get_vault_names("all") returns all names ---')
        all_names = reg.get_vault_names("all")
        check("all returns 2 names", len(all_names) == 2)

        # -- Test 18: get_vault_names("personal,research") filters --------
        print('\n--- get_vault_names("personal,research") filters ---')
        filtered = reg.get_vault_names("personal,research")
        check("personal filter includes alpha", "alpha" in filtered)
        check("work filter excludes beta", "beta" not in filtered)

        # -- Test 19: save/load round-trip preserves all data --------------
        print("\n--- save/load round-trip preserves all data ---")
        reg.save()
        reg_reloaded = VaultRegistry(registry_path=registry_file)
        reloaded = reg_reloaded.get("alpha")
        check("round-trip name", reloaded.name == "alpha")
        check("round-trip policies", reloaded.policies.get("draft_max_age_days") == 14)
        check("round-trip is_default", reloaded.is_default is True)

        # -- Test 20: doctor detects missing vault paths -------------------
        print("\n--- doctor detects missing vault paths ---")
        # Register a vault then remove its directory
        ghost_dir = Path(tmpdir) / "ghost_vault"
        ghost_dir.mkdir()
        reg.register("ghost", str(ghost_dir), profile="creative")
        os.rmdir(str(ghost_dir))
        issues = reg.doctor()
        check("doctor reports issue for missing path", len(issues) >= 1)
        check("issue mentions ghost", any("ghost" in i for i in issues))

        # -- Test 21: VaultEntry.from_dict / to_dict round-trip ------------
        print("\n--- VaultEntry from_dict / to_dict round-trip ---")
        original = VaultEntry(
            name="test",
            path="/some/path",
            is_default=True,
            profile="work",
            policies={"watcher_enabled": True},
        )
        rebuilt = VaultEntry.from_dict(original.to_dict())
        check("to_dict/from_dict name", rebuilt.name == "test")
        check("to_dict/from_dict policies", rebuilt.policies == {"watcher_enabled": True})

        # -- Test 22: register rejects invalid profile ---------------------
        print("\n--- register rejects invalid profile ---")
        try:
            reg.register("bad_profile", str(vault_a), profile="gaming")
            check("raises ValueError for bad profile", False)
        except ValueError:
            check("raises ValueError for bad profile", True)

        # -- Test 23: register rejects duplicate name ----------------------
        print("\n--- register rejects duplicate name ---")
        try:
            reg.register("alpha", str(vault_b), profile="work")
            check("raises ValueError for duplicate name", False)
        except ValueError:
            check("raises ValueError for duplicate name", True)

    # -- Summary -----------------------------------------------------------
    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
