/**
 * ui.ts — Ix CLI brand presentation layer.
 *
 * Centralizes color, formatting, and layout for all CLI commands.
 * Do not add command logic here. Do not extend format.ts.
 */

import chalk from "chalk";

// ── Brand palette ─────────────────────────────────────────────────────────────
//
//   Primary / kind accent   chalk.cyan
//   Entity names / values   chalk.bold
//   Section titles          chalk.bold
//   Success                 chalk.green
//   Warning / note          chalk.yellow / chalk.dim
//   Error                   chalk.red
//   Muted labels            chalk.dim

// ── Section / structure ───────────────────────────────────────────────────────

/** Print a bold section title preceded by a blank line. */
export function renderSection(title: string): void {
  console.log(chalk.bold(`\n${title}`));
}

/**
 * Print a dim label + value row.
 * Label is colon-suffixed and padded to 18 characters.
 */
export function renderKeyValue(label: string, value: string, indent = "  "): void {
  console.log(`${indent}${chalk.dim((label + ":").padEnd(18))}${value}`);
}

// ── Entity emphasis ───────────────────────────────────────────────────────────

/** Render an entity kind: cyan, padded to 10 characters. */
export function colorizeKind(kind: string): string {
  return chalk.cyan((kind ?? "").padEnd(10));
}

/** Render a resolved entity name: bold. */
export function colorizeEntity(name: string): string {
  return chalk.bold(name);
}

// ── Hierarchy / breadcrumb ────────────────────────────────────────────────────

/**
 * Render a breadcrumb path as a string.
 * Node names are joined with a dim separator.
 * Pass pre-humanized node names when applicable.
 */
export function renderBreadcrumb(
  nodes: Array<{ name: string; kind?: string }>,
  separator = " → ",
): string {
  return nodes.map((n) => n.name).join(chalk.dim(separator));
}

// ── Alerts ────────────────────────────────────────────────────────────────────

/** Advisory hint, stale data, or informational note. */
export function renderNote(text: string): void {
  console.log(`  ${chalk.dim("Note")}  ${chalk.dim(text)}`);
}

/** Partial or degraded result. */
export function renderWarning(text: string): void {
  console.log(`  ${chalk.yellow("Warning")}  ${chalk.yellow(text)}`);
}

/** Success confirmation. */
export function renderSuccess(text: string): void {
  console.log(`  ${chalk.green(text)}`);
}

/** Command failure or unresolved target. */
export function renderError(text: string): void {
  console.log(`  ${chalk.red("Error")}  ${chalk.red(text)}`);
}

// ── Resolved header ───────────────────────────────────────────────────────────

/** Print the "Resolved: kind name" header shown at the top of most command text output. */
export function renderResolvedHeader(kind: string, name: string): void {
  console.log(`${chalk.bold("Resolved:")} ${chalk.cyan(kind)} ${chalk.bold(name)}`);
}
