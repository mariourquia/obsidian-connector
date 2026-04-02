/**
 * Hook normalization: adjusts hook paths for build targets.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SRC } from "../lib.js";

export interface HooksJson {
  hooks: Record<string, Array<{
    matcher: string;
    hooks: Array<{
      type: string;
      command?: string;
      prompt?: string;
    }>;
  }>>;
}

export function loadSourceHooks(): HooksJson {
  const raw = readFileSync(join(SRC, "hooks", "hooks.json"), "utf-8");
  return JSON.parse(raw) as HooksJson;
}

/**
 * Rewrite ${CLAUDE_PLUGIN_ROOT}/hooks/ paths to point at the build output
 * layout where hooks live at the top level hooks/ directory.
 */
export function rewriteHookPaths(hooks: HooksJson): HooksJson {
  // In the build output, hooks/ is at the top level, so the
  // ${CLAUDE_PLUGIN_ROOT}/hooks/ prefix is already correct.
  // This function exists for future path transformations.
  return hooks;
}
