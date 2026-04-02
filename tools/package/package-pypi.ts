/**
 * PyPI target builder: delegates to python -m build for sdist/wheel.
 */

import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, existsSync, readdirSync, cpSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, BUILDS } from "../lib.js";
import type { ValidationResult } from "../validate.js";

const OUT = join(BUILDS, "pypi");

export async function build(): Promise<void> {
  // Clean
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });

  // Build sdist + wheel using Python build module
  const pythonBuildOut = join(ROOT, "dist");
  try {
    execFileSync("python3", ["-m", "build", "--outdir", OUT], {
      cwd: ROOT,
      stdio: "inherit",
    });
    console.log("    built sdist + wheel");
  } catch (err) {
    console.error("    python -m build failed. Is the 'build' package installed?");
    throw err;
  }
}

export async function validate(): Promise<ValidationResult> {
  const passed: string[] = [];
  const failed: { rule: string; message: string }[] = [];

  const check = (rule: string, ok: boolean, msg: string) => {
    if (ok) passed.push(rule);
    else failed.push({ rule, message: msg });
  };

  if (!existsSync(OUT)) {
    failed.push({ rule: "build_dir_exists", message: "builds/pypi/ does not exist. Run build first." });
    return { target: "pypi", passed, failed };
  }

  const files = readdirSync(OUT);
  const hasWheel = files.some((f) => f.endsWith(".whl"));
  const hasSdist = files.some((f) => f.endsWith(".tar.gz"));

  check("wheel_exists", hasWheel, "No .whl file found");
  check("sdist_exists", hasSdist, "No .tar.gz file found");

  // Validate with twine if available
  try {
    execFileSync("python3", ["-m", "twine", "check", ...files.map((f) => join(OUT, f))], {
      stdio: ["pipe", "pipe", "pipe"],
    });
    passed.push("twine_check");
  } catch {
    // twine not installed or check failed
    failed.push({ rule: "twine_check", message: "twine check failed or twine not installed" });
  }

  return { target: "pypi", passed, failed };
}
