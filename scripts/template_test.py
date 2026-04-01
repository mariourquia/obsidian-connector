#!/usr/bin/env python3
"""Tests for the template_engine module.

Validates template loading, variable substitution, inheritance,
built-in templates, daily note path formatting, and sentinel config.
Uses tempfile for isolation.  No pytest dependency.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.template_engine import (
    BUILTIN_TEMPLATES,
    TemplateEngine,
    TemplateInfo,
    TemplateNotFoundError,
    format_daily_note_path,
    get_sentinels,
    init_templates,
    _parse_frontmatter,
    _extract_variables,
    _builtin_variables,
    _DEFAULT_SENTINELS,
)

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
    _check(
        label,
        isinstance(obj, expected_type),
        f"got {type(obj).__name__}, expected {expected_type.__name__}",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXED_NOW = datetime(2026, 3, 30, 14, 25, 0)

SAMPLE_TEMPLATE = (
    "---\n"
    "template: sample\n"
    "version: 2.1.0\n"
    "description: A sample template\n"
    "---\n"
    "# Hello {{vault_name}}\n"
    "\n"
    "Date: {{date}}\n"
    "Custom: {{custom_var}}\n"
    "Unknown: {{unknown_var}}\n"
)

BASE_TEMPLATE = (
    "---\n"
    "template: base-note\n"
    "version: 1.0.0\n"
    "description: Base template for inheritance testing\n"
    "---\n"
    "# {{title}}\n"
    "\n"
    "## Header\n"
    "\n"
    "Base header content.\n"
    "\n"
    "## Body\n"
    "\n"
    "Base body content.\n"
    "\n"
    "## Footer\n"
    "\n"
    "Base footer content.\n"
)

CHILD_TEMPLATE = (
    "---\n"
    "template: child-note\n"
    "version: 1.0.0\n"
    "extends: base-note\n"
    "description: Child that overrides Body section\n"
    "---\n"
    "# {{title}}\n"
    "\n"
    "## Body\n"
    "\n"
    "Child body override.\n"
    "\n"
    "## Extra\n"
    "\n"
    "Child-only section.\n"
)


def _make_vault_with_templates() -> tempfile.TemporaryDirectory:
    """Create a temp vault with _templates/ containing test templates."""
    td = tempfile.TemporaryDirectory()
    vault = Path(td.name)
    tpl_dir = vault / "_templates"
    tpl_dir.mkdir()

    (tpl_dir / "sample.md").write_text(SAMPLE_TEMPLATE, encoding="utf-8")
    (tpl_dir / "base-note.md").write_text(BASE_TEMPLATE, encoding="utf-8")
    (tpl_dir / "child-note.md").write_text(CHILD_TEMPLATE, encoding="utf-8")

    return td


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_engine_loads_templates():
    """TemplateEngine loads templates from _templates/ folder."""
    print("\n--- TemplateEngine loads templates ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        templates = engine.list_templates()
        _check("loaded 3 templates", len(templates) == 3)
        names = [t.name for t in templates]
        assert_in("sample in list", "sample", names)
        assert_in("base-note in list", "base-note", names)
        assert_in("child-note in list", "child-note", names)


def test_list_templates_returns_template_info():
    """list_templates returns correct TemplateInfo objects."""
    print("\n--- list_templates returns TemplateInfo ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        templates = engine.list_templates()
        sample = [t for t in templates if t.name == "sample"][0]
        assert_type("TemplateInfo type", sample, TemplateInfo)
        assert_eq("sample version", sample.version, "2.1.0")
        assert_eq("sample description", sample.description, "A sample template")
        _check("sample extends is None", sample.extends is None)


def test_get_template_returns_content():
    """get_template returns raw content."""
    print("\n--- get_template returns content ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        content = engine.get_template("sample")
        assert_in("contains frontmatter", "version: 2.1.0", content)
        assert_in("contains body", "Hello {{vault_name}}", content)


def test_get_template_raises_not_found():
    """get_template raises TemplateNotFoundError for unknown templates."""
    print("\n--- get_template raises TemplateNotFoundError ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        raised = False
        try:
            engine.get_template("nonexistent")
        except TemplateNotFoundError:
            raised = True
        _check("TemplateNotFoundError raised", raised)


def test_render_substitutes_date():
    """render substitutes {{date}} correctly."""
    print("\n--- render substitutes date ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        rendered = engine.render("sample", now=FIXED_NOW)
        assert_in("date substituted", "2026-03-30", rendered)


def test_render_substitutes_vault_name():
    """render substitutes {{vault_name}} correctly."""
    print("\n--- render substitutes vault_name ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        vault_name = Path(vault).name
        rendered = engine.render("sample", now=FIXED_NOW)
        assert_in("vault_name substituted", vault_name, rendered)


def test_render_substitutes_custom_variables():
    """render substitutes custom variables."""
    print("\n--- render substitutes custom variables ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        rendered = engine.render(
            "sample",
            variables={"custom_var": "MY_VALUE"},
            now=FIXED_NOW,
        )
        assert_in("custom var substituted", "MY_VALUE", rendered)


def test_render_leaves_unknown_variables():
    """render leaves unknown variables as-is (no crash)."""
    print("\n--- render leaves unknown variables ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        rendered = engine.render("sample", now=FIXED_NOW)
        assert_in("unknown var preserved", "{{unknown_var}}", rendered)


def test_inheritance_merges_base_and_child():
    """render_with_inheritance merges base and child templates."""
    print("\n--- render_with_inheritance merges ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        rendered = engine.render_with_inheritance(
            "child-note",
            variables={"title": "Test"},
            now=FIXED_NOW,
        )
        # Should contain content from both
        _check("result is non-empty", len(rendered) > 0)
        assert_in("has child body", "Child body override", rendered)


def test_inheritance_child_overrides_base():
    """render_with_inheritance child sections override base sections."""
    print("\n--- child sections override base ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        rendered = engine.render_with_inheritance(
            "child-note",
            variables={"title": "Test"},
            now=FIXED_NOW,
        )
        # Body should be child's, not base's
        _check("base body NOT present", "Base body content" not in rendered)
        assert_in("child body present", "Child body override", rendered)


def test_inheritance_preserves_non_overridden():
    """render_with_inheritance preserves non-overridden base sections."""
    print("\n--- preserves non-overridden base sections ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        rendered = engine.render_with_inheritance(
            "child-note",
            variables={"title": "Test"},
            now=FIXED_NOW,
        )
        # Header and Footer are base-only sections
        assert_in("base header preserved", "Base header content", rendered)
        assert_in("base footer preserved", "Base footer content", rendered)
        # Extra is child-only
        assert_in("child extra added", "Child-only section", rendered)


def test_builtin_templates_render():
    """All built-in templates render without error."""
    print("\n--- built-in templates render ---")
    with tempfile.TemporaryDirectory() as vault:
        init_templates(vault)
        engine = TemplateEngine(vault)
        for name in BUILTIN_TEMPLATES:
            try:
                rendered = engine.render(name, variables={"title": "Test"}, now=FIXED_NOW)
                _check(f"builtin {name} renders", len(rendered) > 0)
            except Exception as e:
                _check(f"builtin {name} renders", False, str(e))


def test_init_templates_creates_folder():
    """init_templates creates _templates/ folder and copies built-ins."""
    print("\n--- init_templates creates folder ---")
    with tempfile.TemporaryDirectory() as vault:
        written = init_templates(vault)
        tpl_dir = Path(vault) / "_templates"
        _check("_templates dir exists", tpl_dir.is_dir())
        assert_eq("wrote all built-ins", len(written), len(BUILTIN_TEMPLATES))
        for name in BUILTIN_TEMPLATES:
            _check(f"file {name}.md exists", (tpl_dir / f"{name}.md").is_file())


def test_init_templates_no_overwrite():
    """init_templates does not overwrite existing files."""
    print("\n--- init_templates no overwrite ---")
    with tempfile.TemporaryDirectory() as vault:
        tpl_dir = Path(vault) / "_templates"
        tpl_dir.mkdir()
        (tpl_dir / "daily-note.md").write_text("custom content", encoding="utf-8")
        written = init_templates(vault)
        _check("skipped existing", "daily-note" not in written)
        content = (tpl_dir / "daily-note.md").read_text(encoding="utf-8")
        assert_eq("existing file preserved", content, "custom content")


def test_format_daily_note_path_with_config():
    """format_daily_note_path uses config format."""
    print("\n--- format_daily_note_path with config ---")
    config = {
        "daily_note_path": "journal/{{date}}.md",
        "daily_note_format": "YYYY-MM-DD",
    }
    result = format_daily_note_path(config, date=FIXED_NOW)
    assert_eq("custom path", result, "journal/2026-03-30.md")


def test_format_daily_note_path_defaults():
    """format_daily_note_path defaults to YYYY-MM-DD format."""
    print("\n--- format_daily_note_path defaults ---")
    result = format_daily_note_path({}, date=FIXED_NOW)
    assert_eq("default path", result, "daily/2026-03-30.md")


def test_get_sentinels_defaults():
    """get_sentinels returns defaults when config has no sentinels key."""
    print("\n--- get_sentinels defaults ---")
    sentinels = get_sentinels({})
    assert_eq("default sentinels", sentinels, _DEFAULT_SENTINELS)
    assert_in("morning_ritual key", "morning_ritual", sentinels)


def test_get_sentinels_custom():
    """get_sentinels returns custom sentinels from config."""
    print("\n--- get_sentinels custom ---")
    custom = {"morning_ritual": "## Buenos Dias", "evening_ritual": "## Buenas Noches"}
    sentinels = get_sentinels({"sentinels": custom})
    assert_eq("custom sentinels", sentinels, custom)


def test_check_updates_detects_outdated():
    """check_updates detects outdated templates."""
    print("\n--- check_updates detects outdated ---")
    with tempfile.TemporaryDirectory() as vault:
        tpl_dir = Path(vault) / "_templates"
        tpl_dir.mkdir()
        # Write a daily-note with an older version
        old = (
            "---\n"
            "template: daily-note\n"
            "version: 0.1.0\n"
            "description: old daily note\n"
            "---\n"
            "# Old daily note\n"
        )
        (tpl_dir / "daily-note.md").write_text(old, encoding="utf-8")
        engine = TemplateEngine(vault)
        outdated = engine.check_updates()
        _check("found outdated", len(outdated) >= 1)
        names = [o["name"] for o in outdated]
        assert_in("daily-note is outdated", "daily-note", names)


def test_version_parsed_from_frontmatter():
    """Template version is parsed from frontmatter."""
    print("\n--- version parsed from frontmatter ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        templates = engine.list_templates()
        sample = [t for t in templates if t.name == "sample"][0]
        assert_eq("version is 2.1.0", sample.version, "2.1.0")
        child = [t for t in templates if t.name == "child-note"][0]
        assert_eq("child extends base-note", child.extends, "base-note")


def test_variables_extracted_from_content():
    """Variables list is extracted from template content."""
    print("\n--- variables extracted ---")
    with _make_vault_with_templates() as vault:
        engine = TemplateEngine(vault)
        templates = engine.list_templates()
        sample = [t for t in templates if t.name == "sample"][0]
        assert_in("date in variables", "date", sample.variables)
        assert_in("vault_name in variables", "vault_name", sample.variables)
        assert_in("custom_var in variables", "custom_var", sample.variables)
        assert_in("unknown_var in variables", "unknown_var", sample.variables)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    test_engine_loads_templates()
    test_list_templates_returns_template_info()
    test_get_template_returns_content()
    test_get_template_raises_not_found()
    test_render_substitutes_date()
    test_render_substitutes_vault_name()
    test_render_substitutes_custom_variables()
    test_render_leaves_unknown_variables()
    test_inheritance_merges_base_and_child()
    test_inheritance_child_overrides_base()
    test_inheritance_preserves_non_overridden()
    test_builtin_templates_render()
    test_init_templates_creates_folder()
    test_init_templates_no_overwrite()
    test_format_daily_note_path_with_config()
    test_format_daily_note_path_defaults()
    test_get_sentinels_defaults()
    test_get_sentinels_custom()
    test_check_updates_detects_outdated()
    test_version_parsed_from_frontmatter()
    test_variables_extracted_from_content()

    print(f"\n{'='*50}")
    print(f"RESULTS: {_PASS} passed, {_FAIL} failed")
    print(f"{'='*50}")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
