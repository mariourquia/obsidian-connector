#!/usr/bin/env python3
"""Validate the graph module: link/tag/frontmatter extraction and NoteIndex."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.graph import (
    NoteIndex,
    build_note_index,
    extract_frontmatter,
    extract_links,
    extract_tags,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp: str, files: dict[str, str]) -> Path:
    """Create a temporary vault directory with the given files."""
    root = Path(tmp) / "vault"
    root.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        full = root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_extract_links() -> None:
    print("\n--- extract_links ---")

    # Basic wikilink
    check("basic [[link]]", extract_links("see [[Note A]]") == ["Note A"])

    # Wikilink with alias
    check(
        "[[link|alias]] returns target",
        extract_links("see [[Note A|my alias]]") == ["Note A"],
    )

    # Multiple links
    links = extract_links("[[A]] text [[B]] more [[C]]")
    check("multiple links", links == ["A", "B", "C"])

    # Deduplicated
    links = extract_links("[[A]] [[A]] [[B]]")
    check("deduplicated links", links == ["A", "B"])

    # Skip code blocks
    content = "before\n```\n[[InCode]]\n```\nafter [[Outside]]"
    check("skip fenced code block", extract_links(content) == ["Outside"])

    # Skip inline code
    content = "see `[[InlineCode]]` and [[Real]]"
    check("skip inline code", extract_links(content) == ["Real"])

    # Empty content
    check("empty content", extract_links("") == [])

    # No links
    check("no links", extract_links("just plain text") == [])

    # Link with path
    check(
        "link with path",
        extract_links("[[folder/Note]]") == ["folder/Note"],
    )


def test_extract_tags() -> None:
    print("\n--- extract_tags ---")

    # Basic tag
    check("basic #tag", extract_tags("#hello world") == ["#hello"])

    # Nested tag
    check(
        "nested #tag/subtag",
        extract_tags("text #topic/subtopic more") == ["#topic/subtopic"],
    )

    # Multiple tags
    tags = extract_tags("#alpha text #beta more #gamma")
    check("multiple tags", tags == ["#alpha", "#beta", "#gamma"])

    # Skip code blocks
    content = "```\n#incode\n```\n#outside"
    check("skip fenced code block", extract_tags(content) == ["#outside"])

    # Skip inline code
    content = "`#inline` and #real"
    check("skip inline code", extract_tags(content) == ["#real"])

    # Skip CSS colors
    check("skip CSS color #fff", extract_tags("color: #fff") == [])
    check("skip CSS color #a1b2c3", extract_tags("color: #a1b2c3") == [])

    # Skip frontmatter tags
    content = "---\ntags: [test]\n---\n#visible"
    check("skip frontmatter", extract_tags(content) == ["#visible"])

    # Deduplicated
    tags = extract_tags("#alpha #alpha #beta")
    check("deduplicated tags", tags == ["#alpha", "#beta"])

    # Empty content
    check("empty content", extract_tags("") == [])


def test_extract_frontmatter() -> None:
    print("\n--- extract_frontmatter ---")

    # Valid YAML frontmatter
    content = "---\ntitle: My Note\nstatus: draft\n---\nBody text"
    fm = extract_frontmatter(content)
    check("valid frontmatter title", fm.get("title") == "My Note")
    check("valid frontmatter status", fm.get("status") == "draft")

    # No frontmatter
    check("no frontmatter", extract_frontmatter("Just body text") == {})

    # Missing closing fence
    content = "---\ntitle: broken\nNo closing fence"
    check("missing closing fence", extract_frontmatter(content) == {})

    # Boolean values
    content = "---\npublished: true\ndraft: false\n---\n"
    fm = extract_frontmatter(content)
    check("boolean true", fm.get("published") is True)
    check("boolean false", fm.get("draft") is False)

    # Integer value
    content = "---\norder: 42\n---\n"
    fm = extract_frontmatter(content)
    check("integer value", fm.get("order") == 42)

    # List value
    content = "---\ntags:\n  - alpha\n  - beta\n---\n"
    fm = extract_frontmatter(content)
    check("list value", fm.get("tags") == ["alpha", "beta"])

    # Quoted string
    content = '---\ntitle: "My Title"\n---\n'
    fm = extract_frontmatter(content)
    check("quoted string", fm.get("title") == "My Title")

    # Empty frontmatter
    content = "---\n---\nBody"
    fm = extract_frontmatter(content)
    check("empty frontmatter", fm == {})


def test_note_index_construction() -> None:
    print("\n--- NoteIndex construction ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Alpha.md": "---\ntitle: Alpha\n---\n#topic\n\n[[Beta]] and [[Gamma]]",
            "Beta.md": "# Beta\n\n[[Alpha]] is linked here.\n#topic",
            "Gamma.md": "# Gamma\n\nNo outgoing links.\n#other",
            "sub/Delta.md": "# Delta\n\n[[Alpha]] [[Nonexistent]]",
            ".obsidian/config.json": '{"key": "value"}',
        })

        index = build_note_index(str(vault))

        check("4 notes indexed", len(index.notes) == 4)
        check("Alpha in index", "Alpha.md" in index.notes)
        check("Beta in index", "Beta.md" in index.notes)
        check("Gamma in index", "Gamma.md" in index.notes)
        check("sub/Delta in index", "sub/Delta.md" in index.notes)
        check(".obsidian skipped", all(".obsidian" not in p for p in index.notes))

        # Forward links
        check(
            "Alpha links to Beta and Gamma",
            index.forward_links["Alpha.md"] == {"Beta.md", "Gamma.md"},
        )
        check(
            "Beta links to Alpha",
            index.forward_links["Beta.md"] == {"Alpha.md"},
        )

        # Backlinks
        check("Alpha has backlinks", "Beta.md" in index.backlinks["Alpha.md"])
        check("Alpha has Delta backlink", "sub/Delta.md" in index.backlinks["Alpha.md"])

        # Unresolved links
        check(
            "Nonexistent is unresolved",
            "Nonexistent" in index.unresolved,
        )
        check(
            "Nonexistent sourced from Delta",
            "sub/Delta.md" in index.unresolved["Nonexistent"],
        )


def test_orphan_detection() -> None:
    print("\n--- Orphan detection ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Connected.md": "[[Other]]",
            "Other.md": "[[Connected]]",
            "Orphan.md": "No links at all.",
        })

        index = build_note_index(str(vault))

        check("Orphan detected", "Orphan.md" in index.orphans)
        check("Connected not orphan", "Connected.md" not in index.orphans)
        check("Other not orphan", "Other.md" not in index.orphans)


def test_dead_end_detection() -> None:
    print("\n--- Dead-end detection ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Source.md": "[[DeadEnd]]",
            "DeadEnd.md": "This note has no outgoing links.",
        })

        index = build_note_index(str(vault))

        check("DeadEnd is a dead end", "DeadEnd.md" in index.dead_ends)
        check("Source not a dead end", "Source.md" not in index.dead_ends)


def test_neighborhood() -> None:
    print("\n--- neighborhood ---")

    with tempfile.TemporaryDirectory() as tmp:
        # A -> B -> C -> D
        vault = _make_vault(tmp, {
            "A.md": "[[B]]",
            "B.md": "[[C]]",
            "C.md": "[[D]]",
            "D.md": "end",
        })

        index = build_note_index(str(vault))

        # 1-hop from A: should include B (forward link)
        n1 = index.neighborhood("A.md", depth=1)
        check("1-hop from A includes B", "B.md" in n1)
        check("1-hop from A excludes C", "C.md" not in n1)

        # 2-hop from A: should include B and C
        n2 = index.neighborhood("A.md", depth=2)
        check("2-hop from A includes B", "B.md" in n2)
        check("2-hop from A includes C", "C.md" in n2)
        check("2-hop from A excludes D", "D.md" not in n2)

        # neighborhood is bidirectional (includes backlinks)
        n1_b = index.neighborhood("B.md", depth=1)
        check("1-hop from B includes A (backlink)", "A.md" in n1_b)
        check("1-hop from B includes C (forward)", "C.md" in n1_b)


def test_shortest_path() -> None:
    print("\n--- shortest_path ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "A.md": "[[B]]",
            "B.md": "[[C]]",
            "C.md": "[[D]]",
            "D.md": "end",
            "Isolated.md": "no links",
        })

        index = build_note_index(str(vault))

        path = index.shortest_path("A.md", "D.md")
        check(
            "A->D path is A,B,C,D",
            path == ["A.md", "B.md", "C.md", "D.md"],
        )

        path_self = index.shortest_path("A.md", "A.md")
        check("self path", path_self == ["A.md"])

        path_none = index.shortest_path("A.md", "Isolated.md")
        check("no path to isolated", path_none is None)


def test_notes_by_tag() -> None:
    print("\n--- notes_by_tag ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Tagged1.md": "#project text",
            "Tagged2.md": "text #project more",
            "Untagged.md": "no tags here",
        })

        index = build_note_index(str(vault))

        tagged = index.notes_by_tag("#project")
        check("two notes with #project", len(tagged) == 2)
        check("Tagged1 in results", "Tagged1.md" in tagged)
        check("Tagged2 in results", "Tagged2.md" in tagged)

        # Without # prefix
        tagged2 = index.notes_by_tag("project")
        check("works without # prefix", tagged2 == tagged)

        empty = index.notes_by_tag("#nonexistent")
        check("nonexistent tag returns empty", len(empty) == 0)


def test_notes_by_property() -> None:
    print("\n--- notes_by_property ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Draft.md": "---\nstatus: draft\n---\ncontent",
            "Published.md": "---\nstatus: published\n---\ncontent",
            "NoFM.md": "no frontmatter",
        })

        index = build_note_index(str(vault))

        # By key only
        with_status = index.notes_by_property("status")
        check("two notes with status property", len(with_status) == 2)

        # By key and value
        drafts = index.notes_by_property("status", "draft")
        check("one draft note", len(drafts) == 1)
        check("Draft.md is the draft", "Draft.md" in drafts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    test_extract_links()
    test_extract_tags()
    test_extract_frontmatter()
    test_note_index_construction()
    test_orphan_detection()
    test_dead_end_detection()
    test_neighborhood()
    test_shortest_path()
    test_notes_by_tag()
    test_notes_by_property()

    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
