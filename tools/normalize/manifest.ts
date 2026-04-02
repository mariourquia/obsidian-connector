/**
 * Manifest normalization: compiles target-specific plugin.json and .mcp.json.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SRC } from "../lib.js";

export interface PluginManifest {
  name: string;
  version: string;
  description: string;
  [key: string]: unknown;
}

export function loadPluginManifest(): PluginManifest {
  const raw = readFileSync(join(SRC, "plugin", "plugin.json"), "utf-8");
  return JSON.parse(raw) as PluginManifest;
}

export function loadMcpConfig(): Record<string, unknown> {
  const raw = readFileSync(join(SRC, "plugin", ".mcp.json"), "utf-8");
  return JSON.parse(raw) as Record<string, unknown>;
}

/**
 * Generate a claude_desktop_config.json snippet for the Desktop target.
 */
export function generateDesktopMcpConfig(installPath: string): Record<string, unknown> {
  return {
    mcpServers: {
      "obsidian-connector": {
        command: `${installPath}/.venv/bin/python3`,
        args: ["-u", "-m", "obsidian_connector.mcp_server"],
        cwd: installPath,
        env: {
          PYTHONPATH: installPath,
          OBSIDIAN_VAULT: "",
        },
      },
    },
  };
}
