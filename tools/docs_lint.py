#!/usr/bin/env python3
"""
tools/docs_lint.py

Docs system-of-record linter:
  - required frontmatter (title, status, owner, last_reviewed)
  - doc discoverability (must be in an index)
  - broken relative links
  - staleness by time and by git vs sources_of_truth
  - AGENTS.md size and link integrity
  - deprecated docs must have replaced_by
  - generated docs must have "do not edit" header

Usage:
  python tools/docs_lint.py                          # full report
  python tools/docs_lint.py --severity error         # errors only (CI blocking)
  python tools/docs_lint.py --check-git-staleness    # include git-based staleness
  python tools/docs_lint.py --fail-on-warn-for verified  # fail on warnings for verified docs
  python tools/docs_lint.py --changed-only           # only lint changed files (pre-commit)
  python tools/docs_lint.py --json                   # output as JSON

Exit codes:
  0 = clean (no issues at chosen severity)
  1 = issues found
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

# ---------------------------------------------------------------------------
# Try to import yaml; fall back to a minimal parser if unavailable
# ---------------------------------------------------------------------------
try:
    import yaml

    def parse_frontmatter(text: str) -> dict[str, Any] | None:
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            return None
        try:
            return yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            return None

except ImportError:
    # Minimal YAML-like frontmatter parser (handles simple key: value lines)
    def parse_frontmatter(text: str) -> dict[str, Any] | None:
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            return None
        data: dict[str, Any] = {}
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                val = val.strip().strip('"').strip("'")
                # Handle lists (simple case)
                if val.startswith("[") and val.endswith("]"):
                    val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
                # Handle numbers
                elif val.isdigit():
                    val = int(val)
                data[key.strip()] = val
        return data


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REQUIRED_FRONTMATTER = {"title", "status", "owner", "last_reviewed"}
VALID_STATUSES = {"draft", "verified", "deprecated"}
AGENTS_MD_MAX_LINES = 120
DOCS_DIR = "docs"
AGENTS_MD = "AGENTS.md"
GENERATED_DIR = os.path.join(DOCS_DIR, "generated")


# ---------------------------------------------------------------------------
# Issue collection
# ---------------------------------------------------------------------------
class Issue:
    def __init__(self, path: str, category: str, severity: str, message: str):
        self.path = path
        self.category = category
        self.severity = severity  # "error" or "warn"
        self.message = message

    def __str__(self) -> str:
        icon = "ERROR" if self.severity == "error" else "WARN "
        return f"[{icon}] [{self.category}] {self.path}: {self.message}"

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
        }


def find_repo_root() -> Path:
    """Walk up from CWD to find .git directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


def find_md_files(root: Path, directory: str) -> list[Path]:
    """Find all .md files under a directory."""
    docs_path = root / directory
    if not docs_path.exists():
        return []
    return sorted(docs_path.rglob("*.md"))


def read_file(path: Path) -> str:
    """Read file contents, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def get_changed_files(root: Path) -> set[str]:
    """Get files changed in the current branch vs main/master."""
    for base in ("origin/main", "origin/master", "main", "master"):
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base, "HEAD"],
                capture_output=True, text=True, cwd=root,
            )
            if result.returncode == 0:
                return {f.strip() for f in result.stdout.splitlines() if f.strip()}
        except (OSError, subprocess.SubprocessError):
            continue
    # Fallback: staged + unstaged changes
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached", "HEAD"],
            capture_output=True, text=True, cwd=root,
        )
        staged = {f.strip() for f in result.stdout.splitlines() if f.strip()}
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, cwd=root,
        )
        unstaged = {f.strip() for f in result.stdout.splitlines() if f.strip()}
        return staged | unstaged
    except (OSError, subprocess.SubprocessError):
        return set()


def git_last_modified(root: Path, filepath: str) -> date | None:
    """Get the date of the last git commit that modified a file."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", filepath],
            capture_output=True, text=True, cwd=root,
        )
        if result.returncode == 0 and result.stdout.strip():
            return datetime.fromisoformat(result.stdout.strip()).date()
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


# ---------------------------------------------------------------------------
# Lint checks
# ---------------------------------------------------------------------------

def check_frontmatter(root: Path, md_file: Path, issues: list[Issue]) -> dict[str, Any] | None:
    """Check that a doc has valid frontmatter with required fields."""
    rel = str(md_file.relative_to(root))
    content = read_file(md_file)
    if not content:
        issues.append(Issue(rel, "metadata", "error", "File is empty or unreadable"))
        return None

    fm = parse_frontmatter(content)
    if fm is None:
        issues.append(Issue(rel, "metadata", "warn", "Missing YAML frontmatter"))
        return None

    missing = REQUIRED_FRONTMATTER - set(fm.keys())
    if missing:
        issues.append(Issue(
            rel, "metadata", "warn",
            f"Missing required frontmatter keys: {', '.join(sorted(missing))}"
        ))

    status = fm.get("status", "")
    if status and status not in VALID_STATUSES:
        issues.append(Issue(
            rel, "metadata", "warn",
            f"Invalid status '{status}'; must be one of: {', '.join(sorted(VALID_STATUSES))}"
        ))

    # Deprecated docs must have replaced_by
    if status == "deprecated" and "replaced_by" not in fm:
        issues.append(Issue(
            rel, "deprecation", "warn",
            "Deprecated doc must include 'replaced_by:' in frontmatter"
        ))

    return fm


def check_discoverability(
    root: Path,
    doc_files: list[Path],
    index_files: list[Path],
    issues: list[Issue],
) -> None:
    """Check that every doc is referenced by at least one index."""
    # Build set of all content referenced from index files
    referenced: set[str] = set()
    for idx in index_files:
        content = read_file(idx)
        idx_dir = idx.parent
        # Find all markdown links: [text](path)
        for match in re.finditer(r"\[.*?\]\((.*?)\)", content):
            link = match.group(1).split("#")[0].split("?")[0]  # strip anchors/queries
            if link:
                resolved = (idx_dir / link).resolve()
                try:
                    referenced.add(str(resolved.relative_to(root)))
                except ValueError:
                    pass

    for doc in doc_files:
        rel = str(doc.relative_to(root))
        # Skip index files themselves and exec-plan files
        if doc.name == "index.md":
            continue
        if "/exec-plans/" in rel:
            continue
        if rel not in referenced:
            issues.append(Issue(
                rel, "structure", "warn",
                "Doc is not referenced by any index.md — agents can't discover it"
            ))


def strip_html_comments(text: str) -> str:
    """Remove HTML comments from text."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def check_relative_links(root: Path, md_file: Path, issues: list[Issue]) -> None:
    """Check that all relative links in a doc point to existing files."""
    rel = str(md_file.relative_to(root))
    content = strip_html_comments(read_file(md_file))
    doc_dir = md_file.parent

    for match in re.finditer(r"\[.*?\]\((.*?)\)", content):
        link = match.group(1).split("#")[0].split("?")[0]
        if not link or link.startswith("http://") or link.startswith("https://"):
            continue
        if link.startswith("mailto:"):
            continue
        # Handle {{}} template vars — skip
        if "{{" in link:
            continue

        target = (doc_dir / unquote(link)).resolve()
        if not target.exists():
            issues.append(Issue(
                rel, "links", "error",
                f"Broken relative link: {link}"
            ))


def check_agents_md(root: Path, issues: list[Issue]) -> None:
    """Check AGENTS.md size and link integrity."""
    agents_path = root / AGENTS_MD
    if not agents_path.exists():
        issues.append(Issue(AGENTS_MD, "agents_map", "error", "AGENTS.md does not exist"))
        return

    content = read_file(agents_path)
    lines = content.splitlines()

    if len(lines) > AGENTS_MD_MAX_LINES:
        issues.append(Issue(
            AGENTS_MD, "agents_map", "error",
            f"AGENTS.md is {len(lines)} lines (max {AGENTS_MD_MAX_LINES})"
        ))

    # Check all relative links
    for match in re.finditer(r"\[.*?\]\((.*?)\)", content):
        link = match.group(1).split("#")[0].split("?")[0]
        if not link or link.startswith("http"):
            continue
        target = (root / link).resolve()
        # Allow directory links (e.g., ./docs/exec-plans/active/)
        if not target.exists():
            issues.append(Issue(
                AGENTS_MD, "agents_map", "error",
                f"AGENTS.md links to non-existent path: {link}"
            ))


def check_staleness_time(
    root: Path, md_file: Path, fm: dict[str, Any], issues: list[Issue]
) -> None:
    """Check time-based staleness: now - last_reviewed > review_cycle_days."""
    rel = str(md_file.relative_to(root))
    last_reviewed_str = fm.get("last_reviewed", "")
    cycle_days = fm.get("review_cycle_days", 90)

    if not last_reviewed_str:
        return

    try:
        if isinstance(last_reviewed_str, date):
            last_reviewed = last_reviewed_str
        else:
            last_reviewed = date.fromisoformat(str(last_reviewed_str))
    except (ValueError, TypeError):
        issues.append(Issue(
            rel, "staleness_time", "warn",
            f"Invalid last_reviewed date: {last_reviewed_str}"
        ))
        return

    days_since = (date.today() - last_reviewed).days
    if days_since > cycle_days:
        issues.append(Issue(
            rel, "staleness_time", "warn",
            f"Stale by time: last reviewed {days_since} days ago "
            f"(cycle: {cycle_days} days)"
        ))


def check_staleness_git(
    root: Path, md_file: Path, fm: dict[str, Any], issues: list[Issue]
) -> None:
    """Check git-based staleness: sources_of_truth changed after last_reviewed."""
    rel = str(md_file.relative_to(root))
    sources = fm.get("sources_of_truth", [])
    last_reviewed_str = fm.get("last_reviewed", "")
    status = fm.get("status", "")

    if not sources or not last_reviewed_str:
        return

    try:
        if isinstance(last_reviewed_str, date):
            last_reviewed = last_reviewed_str
        else:
            last_reviewed = date.fromisoformat(str(last_reviewed_str))
    except (ValueError, TypeError):
        return

    for source in sources:
        source_path = root / source
        if not source_path.exists():
            issues.append(Issue(
                rel, "staleness_git", "warn",
                f"sources_of_truth path does not exist: {source}"
            ))
            continue

        # Check if any file in the source path was modified after last_reviewed
        if source_path.is_dir():
            # Check all files in the directory
            for f in source_path.rglob("*"):
                if f.is_file():
                    last_mod = git_last_modified(root, str(f.relative_to(root)))
                    if last_mod and last_mod > last_reviewed:
                        severity = "error" if status == "verified" else "warn"
                        issues.append(Issue(
                            rel, "staleness_git", severity,
                            f"Source code changed after last review: "
                            f"{f.relative_to(root)} (modified {last_mod})"
                        ))
                        return  # One finding per doc is enough
        else:
            last_mod = git_last_modified(root, str(source_path.relative_to(root)))
            if last_mod and last_mod > last_reviewed:
                severity = "error" if status == "verified" else "warn"
                issues.append(Issue(
                    rel, "staleness_git", severity,
                    f"Source code changed after last review: "
                    f"{source} (modified {last_mod})"
                ))


def check_generated_docs(root: Path, issues: list[Issue]) -> None:
    """Check that generated docs contain 'do not edit' header."""
    gen_dir = root / GENERATED_DIR
    if not gen_dir.exists():
        return

    for md in gen_dir.rglob("*.md"):
        rel = str(md.relative_to(root))
        content = read_file(md)
        # Check first 5 lines for "generated" and "do not edit"
        header = "\n".join(content.splitlines()[:5]).lower()
        if "generated" not in header or "do not edit" not in header:
            issues.append(Issue(
                rel, "generated", "error",
                "Generated doc must contain 'generated, do not edit' in header"
            ))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def lint(
    root: Path,
    check_git: bool = False,
    changed_only: bool = False,
    fail_on_warn_for: str | None = None,
) -> list[Issue]:
    """Run all lint checks and return issues."""
    issues: list[Issue] = []

    # Find all markdown files
    all_docs = find_md_files(root, DOCS_DIR)
    index_files = [f for f in all_docs if f.name == "index.md"]

    # Also include root-level docs
    root_docs = [
        root / "HARNESS_PLAN.md",
        root / "ARCHITECTURE.md",
    ]
    root_docs = [f for f in root_docs if f.exists()]

    # If changed-only mode, filter to changed files
    if changed_only:
        changed = get_changed_files(root)
        all_docs = [f for f in all_docs if str(f.relative_to(root)) in changed]

    # 1. Check AGENTS.md
    check_agents_md(root, issues)

    # 2. Check frontmatter for each doc
    frontmatter_map: dict[Path, dict[str, Any]] = {}
    for doc in all_docs + root_docs:
        fm = check_frontmatter(root, doc, issues)
        if fm:
            frontmatter_map[doc] = fm

    # 3. Check discoverability (every doc in an index)
    check_discoverability(root, all_docs, index_files, issues)

    # 4. Check relative links
    for doc in all_docs + root_docs:
        check_relative_links(root, doc, issues)
    # Also check AGENTS.md links (done in check_agents_md)

    # 5. Check time-based staleness
    for doc, fm in frontmatter_map.items():
        check_staleness_time(root, doc, fm, issues)

    # 6. Check git-based staleness (optional)
    if check_git:
        for doc, fm in frontmatter_map.items():
            check_staleness_git(root, doc, fm, issues)

    # 7. Check generated docs
    check_generated_docs(root, issues)

    # 8. Optionally escalate warnings to errors for specific statuses
    if fail_on_warn_for:
        for issue in issues:
            if issue.severity == "warn":
                # Look up the doc's status
                doc_path = root / issue.path
                fm = frontmatter_map.get(doc_path, {})
                if fm.get("status") == fail_on_warn_for:
                    issue.severity = "error"

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Docs system-of-record linter")
    parser.add_argument(
        "--severity",
        choices=["error", "warn"],
        default="warn",
        help="Minimum severity to display (default: warn = show all)",
    )
    parser.add_argument(
        "--check-git-staleness",
        action="store_true",
        help="Enable git-based staleness checks (slower, needs git history)",
    )
    parser.add_argument(
        "--fail-on-warn-for",
        metavar="STATUS",
        help="Escalate warnings to errors for docs with this status (e.g., 'verified')",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Only lint files changed in the current branch",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (auto-detected if not specified)",
    )
    args = parser.parse_args()

    root = args.root or find_repo_root()
    issues = lint(
        root,
        check_git=args.check_git_staleness,
        changed_only=args.changed_only,
        fail_on_warn_for=args.fail_on_warn_for,
    )

    # Filter by severity
    if args.severity == "error":
        display_issues = [i for i in issues if i.severity == "error"]
    else:
        display_issues = issues

    # Output
    if args.json:
        result = {
            "total": len(display_issues),
            "errors": sum(1 for i in display_issues if i.severity == "error"),
            "warnings": sum(1 for i in display_issues if i.severity == "warn"),
            "issues": [i.to_dict() for i in display_issues],
        }
        print(json.dumps(result, indent=2))
    else:
        if not display_issues:
            print(f"docs-lint: clean ({len(issues)} total issues, "
                  f"{len(display_issues)} at severity '{args.severity}')")
        else:
            for issue in display_issues:
                print(issue)
            print(f"\n--- Summary: {len(display_issues)} issue(s) ---")
            errors = sum(1 for i in display_issues if i.severity == "error")
            warns = sum(1 for i in display_issues if i.severity == "warn")
            if errors:
                print(f"  Errors: {errors}")
            if warns:
                print(f"  Warnings: {warns}")

    # Exit code
    has_errors = any(i.severity == "error" for i in display_issues)
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
