#!/usr/bin/env tsx
/**
 * Diff command: shows what changes the build pipeline makes to each skill.
 *
 * Usage:
 *   npx tsx tools/diff.ts --target portable
 */

import { parseTarget, getTargets } from "./lib.js";

async function main() {
  const targetArg = process.argv.find((a) => a.startsWith("--target="))?.split("=")[1]
    ?? process.argv[process.argv.indexOf("--target") + 1];

  const target = parseTarget(targetArg);
  const targets = getTargets(target);

  for (const t of targets) {
    const mod = await import(`./package/package-${t}.js`);
    if (typeof mod.diff === "function") {
      await mod.diff();
    } else {
      console.log(`No diff implementation for target: ${t}`);
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
