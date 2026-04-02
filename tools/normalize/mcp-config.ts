/**
 * MCP config normalization: target-specific .mcp.json generation.
 */

import { loadMcpConfig } from "./manifest.js";

/**
 * For Claude Code target: return the source .mcp.json as-is
 * (uses ${CLAUDE_PLUGIN_ROOT} variable).
 */
export function mcpConfigForClaudeCode(): Record<string, unknown> {
  return loadMcpConfig();
}
