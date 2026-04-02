/**
 * Claude Desktop target builder: MCP server + install config, no skills or hooks.
 */

import { cpSync, mkdirSync, rmSync, existsSync, writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, SRC, BUILDS, loadTargetConfig } from "../lib.js";
import { generateDesktopMcpConfig } from "../normalize/manifest.js";
import type { ValidationResult } from "../validate.js";

const OUT = join(BUILDS, "claude-desktop");

export async function build(): Promise<void> {
  const config = loadTargetConfig("claude-desktop");

  // Clean
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });

  // 1. Python package
  cpSync(join(ROOT, "obsidian_connector"), join(OUT, "obsidian_connector"), { recursive: true });
  console.log("    copied obsidian_connector/");

  // 2. Bin wrappers
  cpSync(join(SRC, "bin"), join(OUT, "bin"), { recursive: true });
  console.log("    copied bin/");

  // 3. MCP config snippet
  const mcpSnippet = generateDesktopMcpConfig("{{INSTALL_PATH}}");
  writeFileSync(
    join(OUT, "claude_desktop_config_snippet.json"),
    JSON.stringify(mcpSnippet, null, 2)
  );
  console.log("    wrote claude_desktop_config_snippet.json");

  // 4. Support files
  for (const f of ["pyproject.toml", "requirements-lock.txt"]) {
    if (existsSync(join(ROOT, f))) {
      cpSync(join(ROOT, f), join(OUT, f));
    }
  }
  console.log("    copied support files");
}

export async function validate(): Promise<ValidationResult> {
  const passed: string[] = [];
  const failed: { rule: string; message: string }[] = [];

  const check = (rule: string, ok: boolean, msg: string) => {
    if (ok) passed.push(rule);
    else failed.push({ rule, message: msg });
  };

  // No skills directory
  check("no_skills", !existsSync(join(OUT, "skills")), "Desktop build should not have skills/");

  // No hooks
  check("no_hooks", !existsSync(join(OUT, "hooks")), "Desktop build should not have hooks/");

  // Python package
  check(
    "python_package_exists",
    existsSync(join(OUT, "obsidian_connector", "__init__.py")),
    "obsidian_connector/__init__.py missing"
  );

  // MCP config snippet
  const snippetPath = join(OUT, "claude_desktop_config_snippet.json");
  if (existsSync(snippetPath)) {
    try {
      const snippet = JSON.parse(readFileSync(snippetPath, "utf-8"));
      check("mcp_snippet_has_servers", !!snippet.mcpServers, "MCP snippet missing mcpServers key");
      passed.push("mcp_snippet_valid_json");
    } catch {
      failed.push({ rule: "mcp_snippet_valid_json", message: "MCP snippet is invalid JSON" });
    }
  } else {
    failed.push({ rule: "mcp_snippet_exists", message: "claude_desktop_config_snippet.json missing" });
  }

  return { target: "claude-desktop", passed, failed };
}
