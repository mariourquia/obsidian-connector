#!/usr/bin/env tsx
/**
 * Package command: creates distributable archives from built targets.
 *
 * Usage:
 *   npx tsx tools/package.ts --target claude-code
 *   npx tsx tools/package.ts --target all
 *
 * Produces zip archives in dist/
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { join, basename } from "node:path";
import { ROOT, BUILDS, parseTarget, getTargets, readVersionSources, type TargetName } from "./lib.js";

const DIST = join(ROOT, "dist");

function zipDirectory(sourceDir: string, outZip: string): void {
  // Remove existing zip if present
  if (existsSync(outZip)) rmSync(outZip);

  execFileSync("zip", ["-r", outZip, "."], {
    cwd: sourceDir,
    stdio: ["pipe", "pipe", "pipe"],
  });
}

const ARCHIVE_NAMES: Record<TargetName, (version: string) => string> = {
  "claude-code": (v) => `obsidian-connector-claude-code-v${v}.zip`,
  "claude-desktop": (v) => `obsidian-connector-desktop-v${v}.zip`,
  "portable": (v) => `obsidian-connector-portable-v${v}.zip`,
  "pypi": (_v) => "", // PyPI artifacts already named by python -m build
};

async function packageTarget(target: TargetName, version: string): Promise<string | null> {
  const buildDir = join(BUILDS, target);
  if (!existsSync(buildDir)) {
    console.error(`    builds/${target}/ does not exist. Run build first.`);
    return null;
  }

  if (target === "pypi") {
    // PyPI artifacts are already in builds/pypi/ from python -m build
    const files = readdirSync(buildDir).filter((f) => f.endsWith(".whl") || f.endsWith(".tar.gz"));
    if (files.length === 0) {
      console.error("    No wheel/sdist found in builds/pypi/. Run build --target pypi first.");
      return null;
    }
    for (const f of files) {
      const src = join(buildDir, f);
      const dst = join(DIST, f);
      execFileSync("cp", [src, dst]);
      console.log(`    ${f}`);
    }
    return files.join(", ");
  }

  const archiveName = ARCHIVE_NAMES[target](version);
  const outZip = join(DIST, archiveName);
  zipDirectory(buildDir, outZip);
  console.log(`    ${archiveName}`);
  return archiveName;
}

async function main() {
  const targetArg = process.argv.find((a) => a.startsWith("--target="))?.split("=")[1]
    ?? process.argv[process.argv.indexOf("--target") + 1];

  const target = parseTarget(targetArg);
  const targets = getTargets(target);

  // Get version
  const versions = readVersionSources();
  const version = versions.pyproject ?? "0.0.0";

  // Ensure dist/ exists
  mkdirSync(DIST, { recursive: true });

  console.log(`Packaging targets: ${targets.join(", ")} (v${version})\n`);

  const results: string[] = [];
  for (const t of targets) {
    console.log(`--- ${t} ---`);
    const result = await packageTarget(t, version);
    if (result) results.push(result);
    console.log();
  }

  if (results.length > 0) {
    console.log(`Artifacts written to dist/:`);
    for (const r of results) console.log(`  ${r}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
