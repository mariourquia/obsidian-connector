/**
 * Portable target builder: stripped skills for Codex, OpenCode, Gemini, etc.
 */

import { mkdirSync, rmSync, existsSync, writeFileSync, readFileSync, readdirSync, cpSync, statSync } from "node:fs";
import { join } from "node:path";
import { SRC, BUILDS, loadTargetConfig, loadSkillPortability } from "../lib.js";
import { normalizeSkill } from "../normalize/skills.js";
import type { ValidationResult } from "../validate.js";

const OUT = join(BUILDS, "portable");

const MCP_TOOL_PATTERN = /\bobsidian_\w+/;

export async function build(): Promise<void> {
  const config = loadTargetConfig("portable");
  const portability = loadSkillPortability();

  // Clean
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });

  const transformations = config.skills.transformations;

  for (const skill of portability.portable_skills) {
    const srcPath = join(SRC, "skills", skill, "SKILL.md");
    if (!existsSync(srcPath)) {
      console.warn(`    WARN: portable skill ${skill} not found at ${srcPath}`);
      continue;
    }

    const content = readFileSync(srcPath, "utf-8");
    const normalized = normalizeSkill(content, transformations);

    const outDir = join(OUT, "skills", skill);
    mkdirSync(outDir, { recursive: true });
    writeFileSync(join(outDir, "SKILL.md"), normalized);

    // Copy reference files/dirs if present
    const srcDir = join(SRC, "skills", skill);
    for (const f of readdirSync(srcDir)) {
      if (f !== "SKILL.md" && !f.includes("SKILL 2")) {
        const refSrc = join(srcDir, f);
        const refDst = join(outDir, f);
        if (statSync(refSrc).isDirectory()) {
          cpSync(refSrc, refDst, { recursive: true });
        } else {
          writeFileSync(refDst, readFileSync(refSrc));
        }
      }
    }

    console.log(`    ${skill}`);
  }

  // Generate README
  writeFileSync(
    join(OUT, "README.md"),
    generateReadme(portability.portable_skills)
  );
  console.log("    wrote README.md");
}

function generateReadme(skills: string[]): string {
  return `# Obsidian Connector -- Portable Skills

These skills work with any AI agent system that supports markdown skill files.

**Important:** Portable skills do NOT require the obsidian-connector MCP server,
Python package, or any specific runtime. They are self-contained markdown
reference files that work with any agent system that reads skill definitions.
No installation beyond copying files is needed.

## Skills Included

${skills.map((s) => `- **${s}**`).join("\n")}

## Installation

### Codex / OpenCode
Copy the \`skills/\` directory to your agent's skill configuration directory.

### Gemini CLI
Copy skill files to \`~/.gemini/skills/\`.

### Generic
Each skill is a self-contained \`SKILL.md\` file. Place it where your agent reads skill definitions.

## Full Platform

These ${skills.length} skills are a subset of the full obsidian-connector platform.
For the complete experience (62 MCP tools, 17 skills, workflow automation,
project sync, session logging), install the Claude Code plugin:

\`\`\`bash
claude plugin install obsidian-connector
\`\`\`

See the main README for all installation options:
https://github.com/mariourquia/obsidian-connector
`;
}

export async function validate(): Promise<ValidationResult> {
  const passed: string[] = [];
  const failed: { rule: string; message: string }[] = [];
  const portability = loadSkillPortability();

  const check = (rule: string, ok: boolean, msg: string) => {
    if (ok) passed.push(rule);
    else failed.push({ rule, message: msg });
  };

  const skillsDir = join(OUT, "skills");
  if (!existsSync(skillsDir)) {
    failed.push({ rule: "skills_dir_exists", message: "skills/ directory missing in portable build" });
    return { target: "portable", passed, failed };
  }

  const builtSkills = readdirSync(skillsDir);

  // Only portable skills present
  check(
    "correct_skill_count",
    builtSkills.length === portability.portable_skills.length,
    `Expected ${portability.portable_skills.length} skills, found ${builtSkills.length}`
  );

  // No non-portable skills leaked in
  for (const s of portability.non_portable_skills) {
    check(`no_workflow_skill_${s}`, !builtSkills.includes(s), `Workflow skill ${s} found in portable build`);
  }

  // No MCP tool references in any portable skill
  for (const s of builtSkills) {
    const skillPath = join(skillsDir, s, "SKILL.md");
    if (existsSync(skillPath)) {
      const content = readFileSync(skillPath, "utf-8");
      check(
        `no_mcp_refs_${s}`,
        !MCP_TOOL_PATTERN.test(content),
        `${s}/SKILL.md still contains MCP tool references`
      );
    }
  }

  // README present
  check("readme_exists", existsSync(join(OUT, "README.md")), "README.md missing");

  return { target: "portable", passed, failed };
}

export async function diff(): Promise<void> {
  const portability = loadSkillPortability();
  const allSkills = [...portability.portable_skills, ...portability.non_portable_skills].sort();

  console.log(`\nDIFF portable (source -> build)\n`);

  for (const skill of allSkills) {
    const isPortable = portability.portable_skills.includes(skill);
    if (!isPortable) {
      console.log(`  skills/${skill}/SKILL.md  [EXCLUDED -- MCP-dependent]`);
      continue;
    }

    const srcPath = join(SRC, "skills", skill, "SKILL.md");
    const outPath = join(BUILDS, "portable", "skills", skill, "SKILL.md");

    if (!existsSync(srcPath)) {
      console.log(`  skills/${skill}/SKILL.md  [SOURCE MISSING]`);
      continue;
    }
    if (!existsSync(outPath)) {
      console.log(`  skills/${skill}/SKILL.md  [NOT YET BUILT]`);
      continue;
    }

    const src = readFileSync(srcPath, "utf-8");
    const out = readFileSync(outPath, "utf-8");

    if (src === out) {
      console.log(`  skills/${skill}/SKILL.md  [INCLUDED -- no changes]`);
    } else {
      console.log(`  skills/${skill}/SKILL.md  [INCLUDED -- portable]`);
      // Show line-level diffs
      const srcLines = src.split("\n");
      const outLines = out.split("\n");
      for (const line of outLines) {
        if (!srcLines.includes(line)) {
          console.log(`    + ${line.slice(0, 80)}`);
        }
      }
      for (const line of srcLines) {
        if (!outLines.includes(line)) {
          console.log(`    - ${line.slice(0, 80)}`);
        }
      }
    }
  }
}
