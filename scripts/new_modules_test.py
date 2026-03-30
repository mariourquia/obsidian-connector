#!/usr/bin/env python3
"""Tests for idea_router, vault_guardian, vault_factory, and vault_presets modules."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_PASS = 0
_FAIL = 0


def _check(label: str, ok: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        msg = f"  FAIL  {label}"
        if detail:
            msg += f" -- {detail}"
        print(msg)


def assert_eq(label: str, got, expected) -> None:
    _check(label, got == expected, f"got {got!r}, expected {expected!r}")


def assert_in(label: str, needle, haystack) -> None:
    _check(label, needle in haystack, f"{needle!r} not in output")


def assert_type(label: str, obj, expected_type) -> None:
    _check(label, isinstance(obj, expected_type), f"got {type(obj).__name__}, expected {expected_type.__name__}")


# ---------------------------------------------------------------------------
# Test imports -- direct module imports
# ---------------------------------------------------------------------------

print("\n=== Import tests (direct) ===")

try:
    from obsidian_connector.idea_router import (
        float_idea,
        incubate_project,
        list_idea_files,
        list_incubating,
        route_idea,
        _build_keyword_index,
        _ensure_idea_file,
    )
    _check("import idea_router", True)
except ImportError as e:
    _check("import idea_router", False, str(e))

try:
    from obsidian_connector.vault_guardian import (
        mark_auto_generated,
        detect_unorganized,
        organize_file,
        _inject_callout,
        _extract_tags,
        _suggest_placement,
        OVERWRITTEN_FILES,
        AUTO_DIRS,
        USER_DIRS,
    )
    _check("import vault_guardian", True)
except ImportError as e:
    _check("import vault_guardian", False, str(e))

try:
    from obsidian_connector.vault_factory import (
        create_vault,
        discard_vault,
        list_existing_vaults,
        detect_vault_root,
        _slugify,
        _render_seed_note,
    )
    _check("import vault_factory", True)
except ImportError as e:
    _check("import vault_factory", False, str(e))

try:
    from obsidian_connector.vault_presets import (
        VaultPreset,
        PRESETS,
        list_presets,
        get_preset,
    )
    _check("import vault_presets", True)
except ImportError as e:
    _check("import vault_presets", False, str(e))

# ---------------------------------------------------------------------------
# Test imports -- __init__.py re-exports
# ---------------------------------------------------------------------------

print("\n=== Import tests (__init__ re-exports) ===")

try:
    from obsidian_connector import (
        float_idea as fi,
        incubate_project as ip,
        list_idea_files as lif,
        list_incubating as li,
        create_vault as cv,
        discard_vault as dv,
        list_existing_vaults as lev,
        detect_unorganized as du,
        mark_auto_generated as mag,
        organize_file as of_,
    )
    _check("import re-exports from __init__", True)
except ImportError as e:
    _check("import re-exports from __init__", False, str(e))

# ---------------------------------------------------------------------------
# Test idea routing
# ---------------------------------------------------------------------------

print("\n=== Idea routing tests ===")

from obsidian_connector.project_sync import RepoEntry

# Build a small repo registry for testing
test_repos = [
    RepoEntry("cre-asset-mgmt-os", "CRE Asset Management OS", "CLAUDE.md", "active", "amos", ["python", "fastapi", "cre"]),
    RepoEntry("fe-cre-asset-mgmt-os", "CRE Frontend", "CLAUDE.md", "active", "amos", ["typescript", "nextjs"]),
    RepoEntry("keiki-platform", "Keiki Platform", "AGENTS.md", "active", "keiki", ["python", "fastapi", "azure"]),
    RepoEntry("keiki-ios", "Keiki iOS", "AGENTS.md", "active", "keiki", ["swift", "swiftui"]),
    RepoEntry("site", "Personal Site", "claude.md", "active", "standalone", ["nextjs", "react", "vercel"]),
    RepoEntry("mcmc-erp", "MCMC ERP", "CLAUDE.md", "active", "mcmc", ["python", "fastapi"]),
]

# Test keyword index building
index = _build_keyword_index(test_repos)
assert_type("keyword index is dict", index, dict)
_check("keyword index is non-empty", len(index) > 0, f"got {len(index)} entries")
assert_in("keyword index has dir_name", "cre-asset-mgmt-os", index)
assert_in("keyword index has tag 'fastapi'", "fastapi", index)
assert_in("keyword index has group 'keiki'", "keiki", index)

# Test route_idea with clear match
routed = route_idea("Fix the keiki platform API endpoint", test_repos)
assert_eq("route_idea keiki match", routed, "keiki-platform")

# Test route_idea with group-level match
routed = route_idea("something about amos backend", test_repos)
assert_in("route_idea amos match", "amos", routed.lower())

# Test route_idea with no match
routed = route_idea("buy groceries and milk", test_repos)
assert_eq("route_idea no match returns general", routed, "general")

# Test route_idea with tag match
routed = route_idea("deploy the vercel project", test_repos)
assert_eq("route_idea vercel tag matches site", routed, "site")

# Test route_idea with swiftui match
routed = route_idea("swiftui layout issue on the ios app", test_repos)
_check("route_idea swiftui routes to keiki-ios", routed == "keiki-ios", f"got {routed!r}")

# ---------------------------------------------------------------------------
# Test idea file creation (float_idea) -- uses temp vault
# ---------------------------------------------------------------------------

print("\n=== Idea file tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault_path = Path(tmpdir)

    # Test _ensure_idea_file creates the file and directory
    idea_file = _ensure_idea_file(vault_path, "test-project")
    assert_eq("idea file created", idea_file.is_file(), True)
    assert_eq("Ideas dir created", (vault_path / "Inbox" / "Ideas").is_dir(), True)
    content = idea_file.read_text()
    assert_in("idea file has frontmatter", "---", content)
    assert_in("idea file has title", "Ideas -- test-project", content)
    assert_in("idea file has tags", "ideas", content)

    # Test idempotency -- calling again should not overwrite
    content_before = idea_file.read_text()
    idea_file2 = _ensure_idea_file(vault_path, "test-project")
    content_after = idea_file2.read_text()
    assert_eq("ensure_idea_file is idempotent", content_before, content_after)

    # Test list_idea_files on temp vault with one idea file
    os.environ["OBSIDIAN_VAULT_PATH"] = tmpdir
    try:
        result = list_idea_files(vault=None)
        assert_type("list_idea_files returns dict", result, dict)
        assert_in("list_idea_files has files key", "files", result)
        assert_eq("list_idea_files finds 1 file", len(result["files"]), 1)
        assert_eq("list_idea_files project name", result["files"][0]["project"], "test-project")
    finally:
        del os.environ["OBSIDIAN_VAULT_PATH"]

# ---------------------------------------------------------------------------
# Test project incubation
# ---------------------------------------------------------------------------

print("\n=== Project incubation tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault_path = Path(tmpdir)
    os.environ["OBSIDIAN_VAULT_PATH"] = tmpdir

    try:
        result = incubate_project(
            name="Aviation Data Platform",
            description="Real-time aircraft tracking with ADS-B data",
            why="Intersection of aviation and data infrastructure",
            tags="aviation, data, adsb",
            related_projects="site, cre-asset-mgmt-os",
        )

        assert_type("incubate result is dict", result, dict)
        assert_eq("incubate name", result["name"], "Aviation Data Platform")
        assert_eq("incubate slug", result["slug"], "aviation-data-platform")
        assert_eq("incubate created", result["created"], True)
        assert_eq("incubate status", result["status"], "idea")

        # Check file was created
        card_file = Path(result["file"])
        assert_eq("incubation card exists", card_file.is_file(), True)
        card_content = card_file.read_text()
        assert_in("card has title", "Aviation Data Platform", card_content)
        assert_in("card has description", "ADS-B data", card_content)
        assert_in("card has why section", "## Why", card_content)
        assert_in("card has related projects", "[[site]]", card_content)
        assert_in("card has tags", "aviation", card_content)

        # Test idempotency -- calling again should append, not overwrite
        result2 = incubate_project(
            name="Aviation Data Platform",
            description="Updated: add weather overlays",
        )
        assert_eq("incubate second call not created", result2["created"], False)
        updated_content = Path(result2["file"]).read_text()
        assert_in("updated card has original content", "ADS-B data", updated_content)
        assert_in("updated card has update section", "Updated: add weather overlays", updated_content)

        # Test list_incubating
        incubating = list_incubating()
        assert_type("list_incubating returns dict", incubating, dict)
        assert_eq("list_incubating count", incubating["count"], 1)
        assert_eq("list_incubating project slug", incubating["projects"][0]["slug"], "aviation-data-platform")

    finally:
        del os.environ["OBSIDIAN_VAULT_PATH"]

# ---------------------------------------------------------------------------
# Test vault guardian -- mark_auto_generated
# ---------------------------------------------------------------------------

print("\n=== Vault guardian tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault_path = Path(tmpdir)

    # Create a file with frontmatter (simulates a project file)
    projects_dir = vault_path / "projects"
    projects_dir.mkdir()
    proj_file = projects_dir / "test-repo.md"
    proj_file.write_text(
        "---\ntitle: \"Test Repo\"\ntags: [project]\n---\n\n# Test Repo\n\nSome content.\n"
    )

    # Create Dashboard.md (overwritten file)
    dash = vault_path / "Dashboard.md"
    dash.write_text(
        "---\ntitle: Dashboard\n---\n\n# Dashboard\n\nProject table here.\n"
    )

    result = mark_auto_generated(vault_path)
    assert_type("mark result is dict", result, dict)
    assert_in("mark result has marked key", "marked", result)
    assert_eq("marked 2 files", result["count"], 2)

    # Verify callout was injected
    proj_content = proj_file.read_text()
    assert_in("project file has callout", "Auto-generated file", proj_content)

    dash_content = dash.read_text()
    assert_in("dashboard has callout", "Auto-generated file", dash_content)

    # Test idempotency -- calling again should not re-inject
    result2 = mark_auto_generated(vault_path)
    assert_eq("mark is idempotent", result2["count"], 0)

# ---------------------------------------------------------------------------
# Test vault guardian -- _inject_callout
# ---------------------------------------------------------------------------

print("\n=== Callout injection tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault_path = Path(tmpdir)

    # File with frontmatter
    f1 = vault_path / "with_fm.md"
    f1.write_text("---\ntitle: Test\n---\n\n# Hello\n")
    assert_eq("inject into frontmatter file", _inject_callout(f1), True)
    content = f1.read_text()
    assert_in("callout after frontmatter", "Auto-generated file", content)
    # Frontmatter should be preserved
    assert_in("frontmatter preserved", "title: Test", content)

    # File without frontmatter
    f2 = vault_path / "no_fm.md"
    f2.write_text("# Just a heading\n\nSome text.\n")
    assert_eq("inject into no-frontmatter file", _inject_callout(f2), True)
    content2 = f2.read_text()
    assert_in("callout prepended", "Auto-generated file", content2)
    assert_in("original content preserved", "Just a heading", content2)

    # Already marked -- should skip
    assert_eq("skip already marked", _inject_callout(f2), False)

# ---------------------------------------------------------------------------
# Test vault guardian -- detect_unorganized
# ---------------------------------------------------------------------------

print("\n=== Detect unorganized tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault_path = Path(tmpdir)

    # Create system files (should be ignored)
    (vault_path / "Dashboard.md").write_text("# Dashboard")
    (vault_path / "Running TODO.md").write_text("# TODO")

    # Create a daily-note-pattern file in root (should be detected)
    (vault_path / "2026-03-23.md").write_text("# March 23")

    # Create a file with session tag (should be detected)
    (vault_path / "work-log.md").write_text(
        "---\ntags: [session, log]\n---\n\n# Work Log\n"
    )

    # Create an unorganized note (should suggest Cards/)
    (vault_path / "random-idea.md").write_text("# Some random idea\n\nThoughts here.\n")

    # Create a file with project-idea tag
    (vault_path / "new-startup.md").write_text(
        "---\ntags: [project-idea, startup]\n---\n\n# New Startup\n"
    )

    suggestions = detect_unorganized(vault_path)
    assert_type("suggestions is list", suggestions, list)
    assert_eq("detect found 4 unorganized files", len(suggestions), 4)

    # Build a lookup by filename
    by_file = {s["file"]: s for s in suggestions}

    assert_in("daily note detected", "2026-03-23.md", by_file)
    assert_eq("daily note -> daily/", by_file["2026-03-23.md"]["suggested_folder"], "daily")

    assert_in("session file detected", "work-log.md", by_file)
    assert_eq("session file -> sessions/", by_file["work-log.md"]["suggested_folder"], "sessions")

    assert_in("random note detected", "random-idea.md", by_file)
    assert_eq("random note -> Cards/", by_file["random-idea.md"]["suggested_folder"], "Cards")

    assert_in("project-idea detected", "new-startup.md", by_file)
    assert_eq("project-idea -> Inbox/Project Ideas", by_file["new-startup.md"]["suggested_folder"], "Inbox/Project Ideas")

# ---------------------------------------------------------------------------
# Test vault guardian -- _extract_tags
# ---------------------------------------------------------------------------

print("\n=== Tag extraction tests ===")

# Inline YAML tags
tags = _extract_tags("---\ntags: [session, daily, review]\n---\n\n# Note\n")
assert_in("extract inline tag 'session'", "session", tags)
assert_in("extract inline tag 'daily'", "daily", tags)

# Multiline YAML tags
tags2 = _extract_tags("---\ntags:\n  - project-idea\n  - startup\n---\n\nBody\n")
assert_in("extract multiline tag 'project-idea'", "project-idea", tags2)

# Inline body tags (#hashtag)
tags3 = _extract_tags("No frontmatter\n\nSome text #important and #review here\n")
assert_in("extract body tag 'important'", "important", tags3)
assert_in("extract body tag 'review'", "review", tags3)

# ---------------------------------------------------------------------------
# Test vault guardian -- organize_file
# ---------------------------------------------------------------------------

print("\n=== Organize file tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault_path = Path(tmpdir)
    os.environ["OBSIDIAN_VAULT_PATH"] = tmpdir

    try:
        # Create a file in the vault root
        (vault_path / "stray-note.md").write_text("# Stray Note\n")

        result = organize_file("stray-note.md", "Cards")
        assert_type("organize result is dict", result, dict)
        assert_eq("organize moved", result["moved"], True)
        assert_eq("organize target", result["to"], "Cards")
        assert_eq("source gone", (vault_path / "stray-note.md").exists(), False)
        assert_eq("dest exists", (vault_path / "Cards" / "stray-note.md").is_file(), True)

        # Test organizing a non-existent file
        result2 = organize_file("ghost.md", "Cards")
        assert_eq("organize missing file", result2["moved"], False)
        assert_in("organize missing has error", "error", result2)

        # Test overwrite protection
        (vault_path / "dup.md").write_text("# Original")
        (vault_path / "Cards" / "dup.md").write_text("# Already here")
        result3 = organize_file("dup.md", "Cards")
        assert_eq("organize no overwrite", result3["moved"], False)
        assert_in("organize overwrite has error", "error", result3)

    finally:
        del os.environ["OBSIDIAN_VAULT_PATH"]

# ---------------------------------------------------------------------------
# Test vault presets -- list_presets
# ---------------------------------------------------------------------------

print("\n=== Vault presets tests ===")

presets = list_presets()
assert_type("list_presets returns list", presets, list)
assert_eq("list_presets returns 13 presets", len(presets), 13)

# Each preset should have slug, name, description, icon
for p in presets:
    assert_in(f"preset '{p['slug']}' has name", "name", p)
    assert_in(f"preset '{p['slug']}' has description", "description", p)
    assert_in(f"preset '{p['slug']}' has icon", "icon", p)

# ---------------------------------------------------------------------------
# Test vault presets -- get_preset
# ---------------------------------------------------------------------------

print("\n=== Get preset tests ===")

journaling = get_preset("journaling")
assert_type("get_preset returns VaultPreset", journaling, VaultPreset)
assert_eq("journaling slug", journaling.slug, "journaling")
assert_eq("journaling name", journaling.name, "Daily Journal")
assert_in("journaling has daily dir", "daily", journaling.directories)
assert_in("journaling has Reflections dir", "Reflections", journaling.directories)
_check("journaling has seed notes", len(journaling.seed_notes) > 0, f"got {len(journaling.seed_notes)}")
_check("journaling has daily template", len(journaling.daily_template) > 0)

mental = get_preset("mental-health")
assert_type("mental-health preset exists", mental, VaultPreset)
assert_eq("mental-health slug", mental.slug, "mental-health")

poetry = get_preset("poetry")
assert_type("poetry preset exists", poetry, VaultPreset)
_check("poetry has craft notes dirs", any("Craft Notes" in d for d in poetry.directories))

# Non-existent preset
missing = get_preset("does-not-exist")
assert_eq("get_preset unknown returns None", missing, None)

# ---------------------------------------------------------------------------
# Test vault factory -- _slugify
# ---------------------------------------------------------------------------

print("\n=== Vault factory utility tests ===")

assert_eq("slugify basic", _slugify("Aviation Research"), "aviation-research")
assert_eq("slugify special chars", _slugify("CRE: Deal Analysis!"), "cre-deal-analysis")
assert_eq("slugify long name truncated", len(_slugify("a" * 100)) <= 60, True)
assert_eq("slugify strips leading dashes", _slugify("--test--"), "test")

# ---------------------------------------------------------------------------
# Test vault factory -- _render_seed_note
# ---------------------------------------------------------------------------

print("\n=== Seed note rendering tests ===")

seed = _render_seed_note("Test Note", "Some content here.", ["seed", "test"])
assert_in("seed note has frontmatter", "---", seed)
assert_in("seed note has title", "Test Note", seed)
assert_in("seed note has tags", "seed, test", seed)
assert_in("seed note has content", "Some content here.", seed)

seed_no_tags = _render_seed_note("No Tags", "Body text.", [])
assert_in("seed note empty tags defaults to 'seed'", "seed", seed_no_tags)

# ---------------------------------------------------------------------------
# Test vault factory -- create_vault (basic, no preset)
# ---------------------------------------------------------------------------

print("\n=== Vault factory create tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    result = create_vault(
        name="Test Vault",
        description="A vault for testing",
        vault_root=tmpdir,
    )

    assert_type("create_vault returns dict", result, dict)
    assert_eq("create_vault name", result["name"], "Test Vault")
    assert_eq("create_vault slug", result["slug"], "test-vault")

    vp = Path(result["vault_path"])
    assert_eq("vault dir exists", vp.is_dir(), True)
    assert_in("Home.md created", "Home.md", result["created_files"])

    # Check standard directories
    assert_eq("Cards/ exists", (vp / "Cards").is_dir(), True)
    assert_eq("Inbox/ exists", (vp / "Inbox").is_dir(), True)
    assert_eq("Research/ exists", (vp / "Research").is_dir(), True)
    assert_eq("daily/ exists", (vp / "daily").is_dir(), True)
    assert_eq("templates/ exists", (vp / "templates").is_dir(), True)

    # Check Home.md content
    home_content = (vp / "Home.md").read_text()
    assert_in("home has vault name", "Test Vault", home_content)
    assert_in("home has description", "A vault for testing", home_content)
    assert_in("home has quick links", "Quick Links", home_content)

    # Check next_steps
    assert_type("next_steps is list", result["next_steps"], list)
    _check("next_steps is non-empty", len(result["next_steps"]) > 0)

# ---------------------------------------------------------------------------
# Test vault factory -- create_vault with seed_topics
# ---------------------------------------------------------------------------

print("\n=== Vault factory with seed topics ===")

with tempfile.TemporaryDirectory() as tmpdir:
    result = create_vault(
        name="Aviation Hub",
        description="Aviation research vault",
        seed_topics=["ADS-B Tracking", "Airport Infrastructure"],
        vault_root=tmpdir,
    )

    vp = Path(result["vault_path"])
    assert_in("seed topic file created", "Research/ads-b-tracking.md", result["created_files"])
    assert_in("second seed topic created", "Research/airport-infrastructure.md", result["created_files"])
    assert_eq("Research/ dir exists", (vp / "Research").is_dir(), True)

    topic_content = (vp / "Research" / "ads-b-tracking.md").read_text()
    assert_in("topic file has title", "ADS-B Tracking", topic_content)
    assert_in("topic file has research prompt", "Research this topic", topic_content)

# ---------------------------------------------------------------------------
# Test vault factory -- create_vault with seed_notes
# ---------------------------------------------------------------------------

print("\n=== Vault factory with seed notes ===")

with tempfile.TemporaryDirectory() as tmpdir:
    result = create_vault(
        name="Notes Vault",
        seed_notes=[
            {"title": "Key Insight", "content": "Something important", "tags": "insight, core"},
        ],
        vault_root=tmpdir,
    )

    vp = Path(result["vault_path"])
    assert_in("seed note file created", "Cards/key-insight.md", result["created_files"])
    note_content = (vp / "Cards" / "key-insight.md").read_text()
    assert_in("seed note has content", "Something important", note_content)
    assert_in("seed note has tags", "insight", note_content)

# ---------------------------------------------------------------------------
# Test vault factory -- create_vault with preset
# ---------------------------------------------------------------------------

print("\n=== Vault factory with preset ===")

with tempfile.TemporaryDirectory() as tmpdir:
    result = create_vault(
        name="My Journal",
        preset="journaling",
        vault_root=tmpdir,
    )

    vp = Path(result["vault_path"])
    assert_type("preset vault result is dict", result, dict)
    assert_eq("preset vault dir exists", vp.is_dir(), True)

    # Journaling preset should create Reflections/ and Gratitude/
    assert_eq("Reflections/ exists", (vp / "Reflections").is_dir(), True)
    assert_eq("Gratitude/ exists", (vp / "Gratitude").is_dir(), True)

    # Should have daily template
    template_file = vp / "templates" / "daily-template.md"
    assert_eq("daily template created", template_file.is_file(), True)
    template_content = template_file.read_text()
    assert_in("template has date placeholder", "{{date}}", template_content)

    # Should have preset seed notes
    _check("preset created files > 1", result["file_count"] > 1, f"got {result['file_count']}")

# ---------------------------------------------------------------------------
# Test vault factory -- discard_vault (dry run)
# ---------------------------------------------------------------------------

print("\n=== Vault factory discard tests ===")

with tempfile.TemporaryDirectory() as tmpdir:
    vault_path = Path(tmpdir) / "disposable"
    vault_path.mkdir()
    (vault_path / "note.md").write_text("# Note")

    # Dry run (no confirm)
    result = discard_vault(str(vault_path), confirm=False)
    assert_eq("discard dry run has confirm_required", result["confirm_required"], True)
    assert_eq("discard dry run file_count", result["file_count"], 1)
    assert_eq("vault still exists after dry run", vault_path.is_dir(), True)

    # Actual discard
    result2 = discard_vault(str(vault_path), confirm=True)
    assert_eq("discard removed", result2["removed"], True)
    assert_eq("vault gone after discard", vault_path.exists(), False)

    # Discard non-existent
    result3 = discard_vault("/tmp/no-such-vault-12345", confirm=True)
    assert_in("discard non-existent has error", "error", result3)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'=' * 50}")
print(f"  {_PASS} passed, {_FAIL} failed")
print(f"{'=' * 50}")

sys.exit(1 if _FAIL > 0 else 0)
