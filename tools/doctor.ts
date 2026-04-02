#!/usr/bin/env tsx
/**
 * Doctor: health check for the obsidian-connector build environment.
 *
 * Usage:
 *   npx tsx tools/doctor.ts
 */

import { execFileSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { ROOT, SRC, BUILDS, readVersionSources } from "./lib.js";

interface Check {
  name: string;
  value: string;
  ok: boolean;
}

function cmd(binary: string, args: string[]): string | null {
  try {
    return execFileSync(binary, args, { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] }).trim();
  } catch {
    return null;
  }
}

function checkExists(label: string, path: string): Check {
  const exists = existsSync(path);
  return { name: label, value: exists ? "exists" : "missing", ok: exists };
}

function main() {
  const checks: Check[] = [];

  // Runtime checks
  const pyVer = cmd("python3", ["--version"])?.replace("Python ", "") ?? "not found";
  checks.push({ name: "Python 3.11+", value: pyVer, ok: pyVer !== "not found" });

  const nodeVer = cmd("node", ["--version"])?.replace("v", "") ?? "not found";
  checks.push({ name: "Node.js", value: nodeVer, ok: nodeVer !== "not found" });

  const tsxAvail = cmd("npx", ["tsx", "--version"]) !== null;
  checks.push({ name: "tsx", value: tsxAvail ? "available" : "missing", ok: tsxAvail });

  const pipAvail = cmd("pip3", ["--version"]) !== null;
  checks.push({ name: "pip", value: pipAvail ? "available" : "missing", ok: pipAvail });

  // Directory checks
  checks.push(checkExists("src/skills/", join(SRC, "skills")));
  checks.push(checkExists("src/hooks/", join(SRC, "hooks")));
  checks.push(checkExists("src/plugin/", join(SRC, "plugin")));

  const buildsExists = existsSync(BUILDS);
  if (buildsExists) {
    const built = readdirSync(BUILDS).filter((d) => !d.startsWith("."));
    checks.push({ name: "builds/", value: `${built.length} targets`, ok: true });
  } else {
    checks.push({ name: "builds/", value: "not yet built", ok: true });
  }

  checks.push(checkExists(".venv", join(ROOT, ".venv")));

  // Version sync
  const versions = readVersionSources();
  const versionValues = Object.values(versions).filter(Boolean);
  const allSame = new Set(versionValues).size <= 1;
  checks.push({
    name: "Version sync",
    value: versionValues[0] ?? "unknown",
    ok: allSame && versionValues.length > 0,
  });

  // Print results
  console.log("DOCTOR -- obsidian-connector health check\n");
  const nameWidth = Math.max(...checks.map((c) => c.name.length));
  const valWidth = Math.max(...checks.map((c) => c.value.length));
  for (const c of checks) {
    const status = c.ok ? "OK" : "WARN";
    console.log(`  ${c.name.padEnd(nameWidth)}  ${c.value.padEnd(valWidth)}  ${status}`);
  }

  const warns = checks.filter((c) => !c.ok);
  if (warns.length > 0) {
    console.log(`\n  ${warns.length} warning(s). Fix before building.`);
  } else {
    console.log("\n  All checks passed. Run `npx tsx tools/build.ts --target all` to build.");
  }
}

main();
