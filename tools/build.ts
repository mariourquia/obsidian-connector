#!/usr/bin/env tsx
/**
 * Build pipeline: produces target-specific artifacts in builds/<target>/
 *
 * Usage:
 *   npx tsx tools/build.ts --target claude-code
 *   npx tsx tools/build.ts --target all
 */

import { parseTarget, getTargets, type TargetName } from "./lib.js";

// Lazy-import target builders so each file can be developed independently
async function buildTarget(target: TargetName): Promise<void> {
  const mod = await import(`./package/package-${target}.js`);
  await mod.build();
}

async function main() {
  const targetArg = process.argv.find((a) => a.startsWith("--target="))?.split("=")[1]
    ?? process.argv[process.argv.indexOf("--target") + 1];

  const target = parseTarget(targetArg);
  const targets = getTargets(target);

  console.log(`Building targets: ${targets.join(", ")}\n`);

  for (const t of targets) {
    const start = performance.now();
    console.log(`--- ${t} ---`);
    await buildTarget(t);
    console.log(`    done (${(performance.now() - start).toFixed(0)}ms)\n`);
  }

  console.log("All builds complete.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
