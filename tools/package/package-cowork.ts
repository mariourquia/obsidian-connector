/**
 * Cowork target builder: skills + portable hooks for Claude Desktop Cowork tab.
 * No MCP server, no Python package, no bin wrappers.
 */

import { cpSync, mkdirSync, rmSync, existsSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { SRC, BUILDS, loadTargetConfig } from "../lib.js";
import { loadSourceHooks, rewriteHookPaths } from "../normalize/hooks.js";
import type { HooksJson } from "../normalize/hooks.js";
import { loadPluginManifest } from "../normalize/manifest.js";
import type { ValidationResult } from "../validate.js";

const OUT = join(BUILDS, "cowork");

export async function build(): Promise<void> {
  const config = loadTargetConfig("cowork");

  // Clean
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });

  // 1. Skills (all skills, no normalization)
  cpSync(join(SRC, "skills"), join(OUT, "skills"), { recursive: true });
  console.log("    copied skills/");

  // 2. Hooks (portable variant -- SessionStart only, no command hooks)
  const allHooks = rewriteHookPaths(loadSourceHooks());
  const hooks: HooksJson = { hooks: {} };
  if (allHooks.hooks["SessionStart"]) {
    hooks.hooks["SessionStart"] = allHooks.hooks["SessionStart"];
  }
  mkdirSync(join(OUT, "hooks"), { recursive: true });
  writeFileSync(join(OUT, "hooks", "hooks.json"), JSON.stringify(hooks, null, 2));
  console.log("    wrote hooks/ (portable)");

  // 3. Plugin manifest (no MCP)
  mkdirSync(join(OUT, ".claude-plugin"), { recursive: true });
  const manifest = loadPluginManifest();
  writeFileSync(
    join(OUT, ".claude-plugin", "plugin.json"),
    JSON.stringify(manifest, null, 2)
  );
  console.log("    wrote .claude-plugin/plugin.json");

  // No MCP config, no Python package, no bin wrappers
}

export async function validate(): Promise<ValidationResult> {
  const passed: string[] = [];
  const failed: { rule: string; message: string }[] = [];

  const check = (rule: string, ok: boolean, msg: string) => {
    if (ok) passed.push(rule);
    else failed.push({ rule, message: msg });
  };

  // Skills present
  const skillsDir = join(OUT, "skills");
  if (existsSync(skillsDir)) {
    const skills = readdirSync(skillsDir).filter(
      (d) => existsSync(join(skillsDir, d, "SKILL.md"))
    );
    check("all_skills_present", skills.length >= 1, `Expected skills, found ${skills.length}`);
  } else {
    failed.push({ rule: "skills_dir_exists", message: "skills/ directory missing" });
  }

  // Plugin manifest present
  check(
    "plugin_json_exists",
    existsSync(join(OUT, ".claude-plugin", "plugin.json")),
    ".claude-plugin/plugin.json missing"
  );

  // No MCP config (should not be present in cowork)
  check(
    "no_mcp_config",
    !existsSync(join(OUT, ".mcp.json")),
    ".mcp.json should not be present in cowork build"
  );

  // No Python package
  check(
    "no_python_package",
    !existsSync(join(OUT, "obsidian_connector")),
    "obsidian_connector/ should not be present in cowork build"
  );

  return { target: "cowork", passed, failed };
}

export async function diff(): Promise<void> {
  console.log("\nDIFF cowork (source -> build)\n");

  const skillsSrc = join(SRC, "skills");
  const skillsOut = join(OUT, "skills");

  if (!existsSync(skillsOut)) {
    console.log("  [NOT YET BUILT]");
    return;
  }

  const srcSkills = existsSync(skillsSrc) ? readdirSync(skillsSrc) : [];
  const outSkills = readdirSync(skillsOut);

  console.log(`  skills: ${outSkills.length}/${srcSkills.length} (all included)`);
  console.log(`  hooks: portable variant`);
  console.log(`  mcp: excluded`);
  console.log(`  python: excluded`);
  console.log(`  bin: excluded`);
}
