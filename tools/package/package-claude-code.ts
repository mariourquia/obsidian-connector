/**
 * Claude Code target builder: full plugin with all skills, hooks, MCP server.
 */

import { cpSync, mkdirSync, rmSync, existsSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { ROOT, SRC, BUILDS, loadTargetConfig } from "../lib.js";
import { loadSourceHooks, rewriteHookPaths } from "../normalize/hooks.js";
import { loadPluginManifest, loadMcpConfig } from "../normalize/manifest.js";
import type { ValidationResult } from "../validate.js";

const OUT = join(BUILDS, "claude-code");

export async function build(): Promise<void> {
  const config = loadTargetConfig("claude-code");

  // Clean
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });

  // 1. Skills
  cpSync(join(SRC, "skills"), join(OUT, "skills"), { recursive: true });
  console.log("    copied skills/");

  // 2. Hooks
  const hooks = rewriteHookPaths(loadSourceHooks());
  mkdirSync(join(OUT, "hooks"), { recursive: true });
  writeFileSync(join(OUT, "hooks", "hooks.json"), JSON.stringify(hooks, null, 2));
  // Copy hook scripts
  for (const f of readdirSync(join(SRC, "hooks"))) {
    if (f !== "hooks.json") {
      cpSync(join(SRC, "hooks", f), join(OUT, "hooks", f));
    }
  }
  console.log("    copied hooks/");

  // 3. Plugin manifest
  mkdirSync(join(OUT, ".claude-plugin"), { recursive: true });
  const manifest = loadPluginManifest();
  writeFileSync(
    join(OUT, ".claude-plugin", "plugin.json"),
    JSON.stringify(manifest, null, 2)
  );
  console.log("    wrote .claude-plugin/plugin.json");

  // 4. MCP config
  const mcpConfig = loadMcpConfig();
  writeFileSync(join(OUT, ".mcp.json"), JSON.stringify(mcpConfig, null, 2));
  console.log("    wrote .mcp.json");

  // 5. Python package
  cpSync(join(ROOT, "obsidian_connector"), join(OUT, "obsidian_connector"), { recursive: true });
  console.log("    copied obsidian_connector/");

  // 6. Bin wrappers
  cpSync(join(SRC, "bin"), join(OUT, "bin"), { recursive: true });
  console.log("    copied bin/");

  // 7. Support files
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

  // All 17 skills present
  const skillsDir = join(OUT, "skills");
  if (existsSync(skillsDir)) {
    const skills = readdirSync(skillsDir).filter(
      (d) => existsSync(join(skillsDir, d, "SKILL.md"))
    );
    check("all_skills_present", skills.length === 17, `Expected 17 skills, found ${skills.length}`);

    // Frontmatter validation
    for (const s of skills) {
      const content = readFileSync(join(skillsDir, s, "SKILL.md"), "utf-8");
      const hasFrontmatter = content.startsWith("---");
      const hasName = /^name:/m.test(content);
      const hasDesc = /^description:/m.test(content);
      check(
        `skill_frontmatter_${s}`,
        hasFrontmatter && hasName && hasDesc,
        `${s}: missing frontmatter (name/description)`
      );
    }
  } else {
    failed.push({ rule: "skills_dir_exists", message: "skills/ directory missing" });
  }

  // Hooks valid
  const hooksFile = join(OUT, "hooks", "hooks.json");
  if (existsSync(hooksFile)) {
    try {
      JSON.parse(readFileSync(hooksFile, "utf-8"));
      passed.push("hooks_json_valid");
    } catch {
      failed.push({ rule: "hooks_json_valid", message: "hooks.json is invalid JSON" });
    }
  } else {
    failed.push({ rule: "hooks_json_exists", message: "hooks/hooks.json missing" });
  }

  // Plugin manifest
  const pluginFile = join(OUT, ".claude-plugin", "plugin.json");
  if (existsSync(pluginFile)) {
    const pj = JSON.parse(readFileSync(pluginFile, "utf-8"));
    check("plugin_has_name", !!pj.name, "plugin.json missing name");
    check("plugin_has_version", !!pj.version, "plugin.json missing version");
    check("plugin_has_description", !!pj.description, "plugin.json missing description");
  } else {
    failed.push({ rule: "plugin_json_exists", message: ".claude-plugin/plugin.json missing" });
  }

  // MCP config
  check("mcp_config_exists", existsSync(join(OUT, ".mcp.json")), ".mcp.json missing");

  // Python package
  check(
    "python_package_exists",
    existsSync(join(OUT, "obsidian_connector", "__init__.py")),
    "obsidian_connector/__init__.py missing"
  );

  return { target: "claude-code", passed, failed };
}
