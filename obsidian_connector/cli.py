"""CLI entry point for obsidian-connector.

This module is the canonical CLI implementation. The root ``main.py`` is a
thin wrapper that imports from here for backward compatibility with
``python main.py ...`` invocations.
"""

from __future__ import annotations

import argparse
import sys
import time

from obsidian_connector.client import (
    ObsidianCLIError,
    list_tasks,
    log_to_daily,
    read_note,
    search_notes,
)
from obsidian_connector.config import load_config
from obsidian_connector.envelope import (
    error_envelope,
    format_output,
    success_envelope,
)
from obsidian_connector.audit import log_action
from obsidian_connector.search import enrich_search_results
from obsidian_connector.workflows import (
    create_research_note,
    find_prior_work,
    log_decision,
)


# ---------------------------------------------------------------------------
# Human-readable formatters
# ---------------------------------------------------------------------------

def _fmt_search(results: list[dict]) -> str:
    if not results:
        return "No matches."
    lines: list[str] = []
    for r in results:
        n = len(r.get("matches", []))
        lines.append(f"  {r['file']}  ({n} match{'es' if n != 1 else ''})")
        for m in r.get("matches", [])[:3]:
            lines.append(f"    L{m['line']}: {m['text'][:120]}")
        if n > 3:
            lines.append(f"    ... and {n - 3} more")
    return "\n".join(lines)


def _fmt_tasks(results: list[dict]) -> str:
    if not results:
        return "No tasks."
    lines: list[str] = []
    for t in results:
        marker = "x" if t.get("status", " ").strip() else " "
        lines.append(f"  [{marker}] {t['text'].lstrip('- [x] ').lstrip('- [ ] ')}  ({t['file']}:{t['line']})")
    return "\n".join(lines)


def _fmt_prior_work(results: list[dict]) -> str:
    if not results:
        return "No prior work found."
    lines: list[str] = []
    for r in results:
        lines.append(f"  {r['file']}")
        lines.append(f"    heading:  {r['heading']}")
        if r["excerpt"]:
            lines.append(f"    excerpt:  {r['excerpt'][:120]}{'...' if len(r['excerpt']) > 120 else ''}")
        lines.append(f"    matches:  {r['match_count']}")
    return "\n".join(lines)


def _fmt_doctor(checks: list[dict]) -> str:
    """Human-readable doctor output."""
    lines: list[str] = []
    for c in checks:
        icon = "PASS" if c.get("ok") else "FAIL"
        lines.append(f"  [{icon}] {c['check']}: {c.get('detail', '')}")
    return "\n".join(lines)


# Map command names to their human-readable formatter.
_HUMAN_FORMATTERS: dict[str, callable] = {
    "search": _fmt_search,
    "tasks": _fmt_tasks,
    "find-prior-work": _fmt_prior_work,
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-connector",
        description="Python CLI wrapper for the Obsidian desktop app.",
    )
    parser.add_argument(
        "--vault", default=None, help="Target vault name (overrides OBSIDIAN_VAULT).",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true", default=False,
        help="Output canonical JSON envelope for any command.",
    )
    sub = parser.add_subparsers(dest="command")

    # -- log-daily ---------------------------------------------------------
    p = sub.add_parser("log-daily", help="Append text to today's daily note.")
    p.add_argument("content", help="Markdown text to append.")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without mutating.")

    # -- search ------------------------------------------------------------
    p = sub.add_parser("search", help="Full-text search across the vault.")
    p.add_argument("query", help="Search query string.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")
    p.add_argument("--max-results", type=int, default=None, help="Limit number of files returned.")
    p.add_argument("--context-lines", type=int, default=0, help="Lines of context around matches.")
    p.add_argument("--dedupe", action="store_true", help="Deduplicate matches per file.")

    # -- read --------------------------------------------------------------
    p = sub.add_parser("read", help="Read a note by name or path.")
    p.add_argument("note", help="Note name (wikilink) or vault-relative path.")

    # -- tasks -------------------------------------------------------------
    p = sub.add_parser("tasks", help="List tasks in the vault.")
    p.add_argument("--status", choices=["todo", "done"], default=None, help="Filter by completion status.")
    p.add_argument("--path-prefix", default=None, help="Filter by vault-relative path prefix.")
    p.add_argument("--due-before", default=None, metavar="DATE", help="Due before ISO date (stored, not yet enforced by CLI).")
    p.add_argument("--due-after", default=None, metavar="DATE", help="Due after ISO date (stored, not yet enforced by CLI).")
    p.add_argument("--limit", type=int, default=None, help="Max results.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- log-decision ------------------------------------------------------
    p = sub.add_parser("log-decision", help="Append a structured decision record to the daily note.")
    p.add_argument("--project", required=True, help="Project or workstream name.")
    p.add_argument("--summary", required=True, help="One-line decision summary.")
    p.add_argument("--details", required=True, help="Longer context or rationale (markdown OK).")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without mutating.")

    # -- create-research-note ----------------------------------------------
    p = sub.add_parser("create-research-note", help="Create a new note from a template.")
    p.add_argument("--title", required=True, help="Note title (becomes file name).")
    p.add_argument("--template", required=True, help='Template name (e.g. "Template, Note").')
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without mutating.")

    # -- find-prior-work ---------------------------------------------------
    p = sub.add_parser("find-prior-work", help="Search for prior work on a topic and summarise hits.")
    p.add_argument("topic", help="Search topic.")
    p.add_argument("--top-n", type=int, default=5, help="Max notes to return (default 5).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- doctor ------------------------------------------------------------
    sub.add_parser("doctor", help="Run health checks on Obsidian CLI and vault connectivity.")

    return parser


def _resolve_json(args: argparse.Namespace) -> bool:
    """Return True if JSON output was requested via global or subcommand flag."""
    return args.as_json or getattr(args, "sub_json", False)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    use_json = _resolve_json(args)
    cfg = load_config()
    vault = args.vault or cfg.default_vault
    t0 = time.monotonic()

    try:
        data: object = None
        human: str | None = None

        if args.command == "log-daily":
            dry = getattr(args, "dry_run", False)
            log_action(
                "log-daily", {"content": args.content}, vault,
                dry_run=dry, affected_path="daily", content=args.content,
            )
            if dry:
                data = {"dry_run": True, "action": "append_to_daily", "content": args.content}
                human = f"[dry-run] Would append to daily note:\n  {args.content}"
            else:
                log_to_daily(args.content, vault=args.vault)
                data = {"appended": True}
                human = "Appended to daily note."

        elif args.command == "search":
            results = search_notes(args.query, vault=args.vault)
            results = enrich_search_results(
                results,
                vault=args.vault,
                context_lines=getattr(args, "context_lines", 0),
                dedupe=getattr(args, "dedupe", False),
                max_results=getattr(args, "max_results", None),
            )
            data = results
            human = _fmt_search(results)

        elif args.command == "read":
            content = read_note(args.note, vault=args.vault)
            data = {"file": args.note, "content": content}
            human = content.rstrip("\n")

        elif args.command == "tasks":
            f: dict = {}
            if args.status == "todo":
                f["todo"] = True
            elif args.status == "done":
                f["done"] = True
            if args.path_prefix:
                f["path"] = args.path_prefix
            if args.limit is not None:
                f["limit"] = args.limit
            if args.due_before:
                f["due_before"] = args.due_before
            if args.due_after:
                f["due_after"] = args.due_after
            results = list_tasks(filter=f or None, vault=args.vault)
            data = results
            human = _fmt_tasks(results)

        elif args.command == "log-decision":
            dry = getattr(args, "dry_run", False)
            log_action(
                "log-decision",
                {"project": args.project, "summary": args.summary, "details": args.details},
                vault, dry_run=dry, affected_path="daily",
                content=args.details,
            )
            if dry:
                data = {
                    "dry_run": True, "action": "log_decision",
                    "project": args.project, "summary": args.summary, "details": args.details,
                }
                human = (
                    f"[dry-run] Would log decision:\n"
                    f"  project: {args.project}\n"
                    f"  summary: {args.summary}\n"
                    f"  details: {args.details}"
                )
            else:
                log_decision(
                    project=args.project,
                    summary=args.summary,
                    details=args.details,
                    vault=args.vault,
                )
                data = {"logged": True, "project": args.project}
                human = "Decision logged to daily note."

        elif args.command == "create-research-note":
            dry = getattr(args, "dry_run", False)
            log_action(
                "create-research-note",
                {"title": args.title, "template": args.template},
                vault, dry_run=dry, affected_path=f"{args.title}.md",
            )
            if dry:
                data = {
                    "dry_run": True, "action": "create_research_note",
                    "title": args.title, "template": args.template,
                }
                human = (
                    f"[dry-run] Would create note:\n"
                    f"  title:    {args.title}\n"
                    f"  template: {args.template}"
                )
            else:
                path = create_research_note(
                    title=args.title,
                    template=args.template,
                    vault=args.vault,
                )
                data = {"created": True, "path": path}
                human = f"Created: {path}"

        elif args.command == "find-prior-work":
            results = find_prior_work(
                topic=args.topic,
                vault=args.vault,
                top_n=args.top_n,
            )
            data = results
            human = _fmt_prior_work(results)

        elif args.command == "doctor":
            from obsidian_connector.doctor import run_doctor
            checks = run_doctor(vault=args.vault)
            data = checks
            human = _fmt_doctor(checks)

        duration_ms = int((time.monotonic() - t0) * 1000)

        if use_json:
            env = success_envelope(args.command, data, vault, duration_ms)
            print(format_output(env, as_json=True))
        else:
            print(human if human is not None else str(data))

    except ObsidianCLIError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        if use_json:
            env = error_envelope(
                command=args.command,
                error_type=type(exc).__name__,
                message=str(exc),
                stderr=getattr(exc, "stderr", ""),
                exit_code=getattr(exc, "returncode", None),
                vault=vault,
            )
            print(format_output(env, as_json=True))
            return 1
        else:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
