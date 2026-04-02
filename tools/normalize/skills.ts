/**
 * Skill normalization: strips MCP-dependent content for portable targets.
 *
 * Transformations:
 *   strip_mcp_references -- remove lines referencing obsidian_* MCP tools
 *   add_portable_header  -- prepend portability notice
 */

/** Lines that are pure MCP tool invocations or references */
const MCP_LINE_PATTERNS = [
  /^\s*-\s*`?obsidian_\w+`?/,          // bullet list tool references
  /Use the `obsidian_\w+` tool/i,       // prose tool references
  /call\s+obsidian_\w+/i,              // "call obsidian_*" instructions
];

const PORTABLE_HEADER = `> **Portable skill** -- This skill works with any AI agent (Codex, OpenCode, Gemini, etc.).\n> It does not require the obsidian-connector MCP server.\n\n`;

export function stripMcpReferences(content: string): string {
  return content
    .split("\n")
    .filter((line) => !MCP_LINE_PATTERNS.some((p) => p.test(line)))
    .join("\n")
    .replace(/`obsidian_\w+`/g, "");
}

export function addPortableHeader(content: string): string {
  // Insert after YAML frontmatter if present
  const fmEnd = content.indexOf("---", content.indexOf("---") + 3);
  if (fmEnd !== -1) {
    const after = fmEnd + 3;
    return content.slice(0, after) + "\n\n" + PORTABLE_HEADER + content.slice(after).trimStart();
  }
  return PORTABLE_HEADER + content;
}

export function normalizeSkill(
  content: string,
  transformations: string[]
): string {
  let result = content;
  for (const t of transformations) {
    switch (t) {
      case "strip_mcp_references":
        result = stripMcpReferences(result);
        break;
      case "add_portable_header":
        result = addPortableHeader(result);
        break;
      default:
        throw new Error(`Unknown transformation: ${t}`);
    }
  }
  return result;
}
