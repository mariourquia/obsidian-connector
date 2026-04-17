"""Tests for obsidian_connector.platform.safe_filename_fragment (v0.11)."""
from __future__ import annotations

from obsidian_connector.platform import safe_filename_fragment


def test_iso_timestamp_colons_replaced():
    assert safe_filename_fragment("2026-04-16T14:30:00") == "2026-04-16T14-30-00"


def test_windows_reserved_chars_replaced():
    assert safe_filename_fragment('a<b>c:d"e/f\\g|h?i*j') == "a-b-c-d-e-f-g-h-i-j"


def test_control_chars_replaced():
    raw = "hello\x00world\x1f"
    out = safe_filename_fragment(raw)
    assert "\x00" not in out
    assert "\x1f" not in out
    assert "hello-world" in out


def test_trailing_whitespace_and_dots_stripped():
    assert safe_filename_fragment("draft  .  ") == "draft"
    assert safe_filename_fragment("clean") == "clean"


def test_only_disallowed_yields_replaced_sequence():
    """Purely-disallowed input gets each char replaced; no squash.
    The hyphens are valid filename characters, so leaving them as-is
    gives a deterministic, length-preserving output."""
    assert safe_filename_fragment(":::") == "---"


def test_custom_replacement_respected():
    assert safe_filename_fragment("a:b", replacement="_") == "a_b"


def test_empty_replacement_allowed():
    """Empty string is allowed; colons simply vanish."""
    assert safe_filename_fragment("a:b", replacement="") == "ab"


def test_empty_after_rstrip_uses_replacement():
    # "   ." strips to empty; fall back to replacement char.
    assert safe_filename_fragment("   .") == "-"


def test_non_string_coerced():
    """Type-unsafe callers should get a defensive coerce, not a crash."""
    assert safe_filename_fragment(1234) == "1234"  # type: ignore[arg-type]


def test_idempotent_on_safe_input():
    out = safe_filename_fragment("2026-04-16_hello")
    assert out == "2026-04-16_hello"
    assert safe_filename_fragment(out) == out


def test_path_separator_stripped_on_any_os():
    """Forward and back slashes are stripped even on POSIX (they are
    always filename delimiters, regardless of the target OS). This is
    why the helper is platform-unconditional."""
    assert safe_filename_fragment("a/b") == "a-b"
    assert safe_filename_fragment("a\\b") == "a-b"
