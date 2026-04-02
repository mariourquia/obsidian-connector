#!/usr/bin/env tsx
/**
 * Validation engine: checks build output correctness per target.
 *
 * Usage:
 *   npx tsx tools/validate.ts --target claude-code
 *   npx tsx tools/validate.ts --target all
 */

import { parseTarget, getTargets, type TargetName } from "./lib.js";

export interface ValidationResult {
  target: string;
  passed: string[];
  failed: { rule: string; message: string }[];
}

// Lazy-import target validators
async function validateTarget(target: TargetName): Promise<ValidationResult> {
  const mod = await import(`./package/package-${target}.js`);
  return mod.validate();
}

async function main() {
  const targetArg = process.argv.find((a) => a.startsWith("--target="))?.split("=")[1]
    ?? process.argv[process.argv.indexOf("--target") + 1];

  const target = parseTarget(targetArg);
  const targets = getTargets(target);
  let allPassed = true;

  for (const t of targets) {
    const result = await validateTarget(t);
    const total = result.passed.length + result.failed.length;

    console.log(`\n--- ${t} (${result.passed.length}/${total} passed) ---`);
    for (const p of result.passed) console.log(`  PASS  ${p}`);
    for (const f of result.failed) {
      console.log(`  FAIL  ${f.rule}: ${f.message}`);
      allPassed = false;
    }
  }

  console.log(allPassed ? "\nAll validations passed." : "\nSome validations failed.");
  process.exit(allPassed ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
