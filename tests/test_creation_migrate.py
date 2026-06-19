# tests/test_creation_migrate.py
"""Tests for creation_migrate -- reversible flat->Projects/{Project}/Repos migration."""
import json
from pathlib import Path

import pytest

from obsidian_connector import creation_migrate as cm

NOW = "2026-06-19T00:00:00Z"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SYNC_CONFIG = {
    "github_root": "/tmp/fakegithub",
    "vault_subdir": "",
    "repos": [
        {
            "dir_name": "mcmc-erp",
            "display_name": "MCMC ERP",
            "group": "mcmc",
            "status": "active",
        },
        {
            "dir_name": "site",
            "display_name": "site",
            "group": "standalone",
            "status": "active",
        },
    ],
}

_MCMC_BODY = "## Notes\nMARIO NOTE"
_SITE_BODY = "## Notes\nSITE NOTE"


def _make_vault(tmp_path: Path, monkeypatch) -> Path:
    """Create a minimal vault with flat per-repo hub notes."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "vault"))

    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)

    # Write sync_config.json
    (vault / "sync_config.json").write_text(
        json.dumps(_SYNC_CONFIG), encoding="utf-8"
    )

    # Write flat per-repo hub notes
    projects_dir = vault / "projects"
    projects_dir.mkdir()

    (projects_dir / "mcmc-erp.md").write_text(
        f"---\ntitle: MCMC ERP\ngroup: mcmc\n---\n\n{_MCMC_BODY}\n",
        encoding="utf-8",
    )
    (projects_dir / "site.md").write_text(
        f"---\ntitle: site\ngroup: standalone\n---\n\n{_SITE_BODY}\n",
        encoding="utf-8",
    )

    return vault


# ---------------------------------------------------------------------------
# plan_migration -- pure, no writes
# ---------------------------------------------------------------------------

class TestPlanMigration:
    def test_returns_move_entries_for_existing_flat_notes(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        plan = cm.plan_migration()

        moves = [e for e in plan if e["action"] == "move"]
        new_paths = {e["new_path"] for e in moves}

        # mcmc group -> group_display("mcmc") == "mcmc" (no override in GROUP_DISPLAY)
        assert "Projects/mcmc/Repos/mcmc-erp.md" in new_paths
        # standalone -> display_name = "site"
        assert "Projects/site/Repos/site.md" in new_paths

    def test_returns_scaffold_entries(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        plan = cm.plan_migration()

        scaffolds = [e for e in plan if e["action"] == "scaffold"]
        scaffold_paths = {e["new_path"] for e in scaffolds}

        # One-Pager, Dashboard, Backlog for mcmc and site
        assert "Projects/mcmc/Project One-Pager.md" in scaffold_paths
        assert "Projects/mcmc/Project Dashboard.md" in scaffold_paths
        assert "Projects/mcmc/Backlog.md" in scaffold_paths
        assert "Projects/site/Project One-Pager.md" in scaffold_paths

    def test_plan_writes_nothing(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        cm.plan_migration()

        # Repo-view notes must NOT exist after a pure plan call
        # (Use the full path because macOS has a case-insensitive fs;
        #  vault/"Projects" == vault/"projects" on macOS, so we check for
        #  the specific sub-paths that the migration would create.)
        assert not (vault / "Projects" / "mcmc" / "Repos" / "mcmc-erp.md").exists()
        assert not (vault / "Projects" / "site" / "Repos" / "site.md").exists()
        assert not (vault / cm._MIGRATION_MAP_REL).exists()

    def test_old_path_is_vault_relative(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        plan = cm.plan_migration()

        moves = [e for e in plan if e["action"] == "move"]
        for move in moves:
            assert not move["old_path"].startswith("/")
            assert move["old_path"].startswith("projects/")


# ---------------------------------------------------------------------------
# migrate dry_run=True
# ---------------------------------------------------------------------------

class TestMigrateDryRun:
    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        result = cm.migrate(now_iso=NOW, dry_run=True)

        assert result["dry_run"] is True
        assert result["written"] == 0
        assert result["map_path"] is None
        # Repo-view notes and migration map must NOT exist after a dry run.
        # (We check specific sub-paths rather than the Projects/ dir itself
        #  because macOS has a case-insensitive fs where vault/"Projects" ==
        #  vault/"projects".)
        assert not (vault / "Projects" / "mcmc" / "Repos" / "mcmc-erp.md").exists()
        assert not (vault / "Projects" / "site" / "Repos" / "site.md").exists()
        assert not (vault / cm._MIGRATION_MAP_REL).exists()


# ---------------------------------------------------------------------------
# migrate dry_run=False
# ---------------------------------------------------------------------------

class TestMigrateWrite:
    def test_creates_repo_view_notes(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        result = cm.migrate(now_iso=NOW, dry_run=False)

        assert result["dry_run"] is False
        assert result["written"] > 0

        assert (vault / "Projects/mcmc/Repos/mcmc-erp.md").is_file()
        assert (vault / "Projects/site/Repos/site.md").is_file()

    def test_prose_is_preserved_in_new_note(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        cm.migrate(now_iso=NOW, dry_run=False)

        mcmc_note = (vault / "Projects/mcmc/Repos/mcmc-erp.md").read_text(encoding="utf-8")
        assert "MARIO NOTE" in mcmc_note

        site_note = (vault / "Projects/site/Repos/site.md").read_text(encoding="utf-8")
        assert "SITE NOTE" in site_note

    def test_new_note_has_repo_status_fence(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        cm.migrate(now_iso=NOW, dry_run=False)

        mcmc_note = (vault / "Projects/mcmc/Repos/mcmc-erp.md").read_text(encoding="utf-8")
        assert cm._REPO_FENCE_BEGIN in mcmc_note
        assert cm._REPO_FENCE_END in mcmc_note

    def test_scaffold_notes_created(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        cm.migrate(now_iso=NOW, dry_run=False)

        assert (vault / "Projects/mcmc/Project One-Pager.md").is_file()
        assert (vault / "Projects/mcmc/Project Dashboard.md").is_file()
        assert (vault / "Projects/mcmc/Backlog.md").is_file()
        assert (vault / "Projects/site/Project One-Pager.md").is_file()

    def test_migration_map_written(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        result = cm.migrate(now_iso=NOW, dry_run=False)

        map_path = vault / cm._MIGRATION_MAP_REL
        assert map_path.is_file()
        assert result["map_path"] == cm._MIGRATION_MAP_REL

        map_content = map_path.read_text(encoding="utf-8")
        assert cm._MAP_FENCE_BEGIN in map_content
        assert "mcmc-erp" in map_content

    def test_flat_notes_untouched(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        original_mcmc = (vault / "projects/mcmc-erp.md").read_text(encoding="utf-8")
        original_site = (vault / "projects/site.md").read_text(encoding="utf-8")

        cm.migrate(now_iso=NOW, dry_run=False)

        assert (vault / "projects/mcmc-erp.md").read_text(encoding="utf-8") == original_mcmc
        assert (vault / "projects/site.md").read_text(encoding="utf-8") == original_site

    def test_returns_planned_count(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        plan = cm.plan_migration()
        result = cm.migrate(now_iso=NOW, dry_run=False)

        assert result["planned"] == len(plan)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_second_run_does_not_clobber_or_duplicate(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)

        # First run
        cm.migrate(now_iso=NOW, dry_run=False)

        # Capture snapshots of created notes
        mcmc_content_after_first = (
            vault / "Projects/mcmc/Repos/mcmc-erp.md"
        ).read_text(encoding="utf-8")
        one_pager_content_after_first = (
            vault / "Projects/mcmc/Project One-Pager.md"
        ).read_text(encoding="utf-8")

        # Second run
        cm.migrate(now_iso=NOW, dry_run=False)

        # Notes must be byte-stable (not overwritten)
        mcmc_content_after_second = (
            vault / "Projects/mcmc/Repos/mcmc-erp.md"
        ).read_text(encoding="utf-8")
        one_pager_content_after_second = (
            vault / "Projects/mcmc/Project One-Pager.md"
        ).read_text(encoding="utf-8")

        assert mcmc_content_after_first == mcmc_content_after_second
        assert one_pager_content_after_first == one_pager_content_after_second

    def test_second_run_written_count_is_lower(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)

        first = cm.migrate(now_iso=NOW, dry_run=False)
        second = cm.migrate(now_iso=NOW, dry_run=False)

        # Second run only rewrites the map (all other files already present)
        assert second["written"] < first["written"]


# ---------------------------------------------------------------------------
# undo_migration
# ---------------------------------------------------------------------------

class TestUndoMigration:
    def test_undo_removes_created_notes(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        cm.migrate(now_iso=NOW, dry_run=False)

        result = cm.undo_migration(dry_run=False)

        assert result["dry_run"] is False
        assert result["reverted"] > 0

        # Repo-view notes should be gone
        assert not (vault / "Projects/mcmc/Repos/mcmc-erp.md").is_file()
        assert not (vault / "Projects/site/Repos/site.md").is_file()

        # Scaffold notes should be gone
        assert not (vault / "Projects/mcmc/Project One-Pager.md").is_file()

        # Map itself should be gone
        assert not (vault / cm._MIGRATION_MAP_REL).is_file()

    def test_undo_leaves_flat_notes_intact(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        original_mcmc = (vault / "projects/mcmc-erp.md").read_text(encoding="utf-8")

        cm.migrate(now_iso=NOW, dry_run=False)
        cm.undo_migration(dry_run=False)

        # Flat note must be untouched
        assert (vault / "projects/mcmc-erp.md").is_file()
        assert (vault / "projects/mcmc-erp.md").read_text(encoding="utf-8") == original_mcmc

    def test_undo_dry_run_removes_nothing(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        cm.migrate(now_iso=NOW, dry_run=False)

        cm.undo_migration(dry_run=True)

        # Notes should still exist after dry-run undo
        assert (vault / "Projects/mcmc/Repos/mcmc-erp.md").is_file()
        assert (vault / cm._MIGRATION_MAP_REL).is_file()

    def test_undo_without_map_is_no_op(self, tmp_path, monkeypatch):
        vault = _make_vault(tmp_path, monkeypatch)
        # No migration ran, so no map exists
        result = cm.undo_migration(dry_run=False)
        assert result["reverted"] == 0
