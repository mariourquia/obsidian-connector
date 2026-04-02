import { readFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { parse as parseYaml } from "yaml";
import { z } from "zod";

/** Project root (one level up from tools/) */
export const ROOT = resolve(import.meta.dirname, "..");

/** Source directory for plugin artifacts */
export const SRC = join(ROOT, "src");

/** Build output directory */
export const BUILDS = join(ROOT, "builds");

/** Config directory */
export const CONFIG = join(ROOT, "config");

// -- Target config schema --

const SkillsConfigSchema = z.object({
  include: z.enum(["all", "none", "portable_only"]),
  normalize: z.boolean().optional().default(false),
  transformations: z.array(z.string()).optional().default([]),
});

const HooksConfigSchema = z.object({
  include: z.boolean(),
  variant: z.string().optional(),
});

const ManifestConfigSchema = z.object({
  include_mcp: z.boolean(),
  include_plugin: z.boolean(),
});

const PythonConfigSchema = z.object({
  include: z.boolean(),
  venv: z.boolean().optional().default(false),
});

const BinConfigSchema = z.object({
  include: z.boolean(),
});

export const TargetConfigSchema = z.object({
  name: z.string(),
  description: z.string(),
  skills: SkillsConfigSchema,
  hooks: HooksConfigSchema,
  manifest: ManifestConfigSchema,
  python_package: PythonConfigSchema,
  bin: BinConfigSchema,
});

export type TargetConfig = z.infer<typeof TargetConfigSchema>;

// -- Skill portability schema --

export const SkillPortabilitySchema = z.object({
  portable_skills: z.array(z.string()),
  non_portable_skills: z.array(z.string()),
});

export type SkillPortability = z.infer<typeof SkillPortabilitySchema>;

// -- Loaders --

export const VALID_TARGETS = [
  "claude-code",
  "claude-desktop",
  "portable",
  "pypi",
] as const;

export type TargetName = (typeof VALID_TARGETS)[number];

export function loadTargetConfig(target: TargetName): TargetConfig {
  const path = join(CONFIG, "targets", `${target}.yaml`);
  const raw = readFileSync(path, "utf-8");
  return TargetConfigSchema.parse(parseYaml(raw));
}

export function loadSkillPortability(): SkillPortability {
  const path = join(CONFIG, "defaults", "skill-portability.yaml");
  const raw = readFileSync(path, "utf-8");
  return SkillPortabilitySchema.parse(parseYaml(raw));
}

export function parseTarget(arg: string | undefined): TargetName | "all" {
  if (!arg || arg === "all") return "all";
  if (VALID_TARGETS.includes(arg as TargetName)) return arg as TargetName;
  console.error(`Unknown target: ${arg}. Valid: ${VALID_TARGETS.join(", ")}, all`);
  process.exit(1);
}

export function getTargets(target: TargetName | "all"): TargetName[] {
  return target === "all" ? [...VALID_TARGETS] : [target];
}

// -- Version helpers --

export interface VersionSources {
  pyproject: string | null;
  plugin_json: string | null;
  product_registry: string | null;
  marketplace: string | null;
  mcpb: string | null;
}

export function readVersionSources(): VersionSources {
  const read = (path: string, pattern: RegExp): string | null => {
    try {
      const content = readFileSync(join(ROOT, path), "utf-8");
      const match = content.match(pattern);
      return match?.[1] ?? null;
    } catch {
      return null;
    }
  };

  return {
    pyproject: (() => {
      try {
        const content = readFileSync(join(ROOT, "pyproject.toml"), "utf-8");
        const projectSection = content.match(/\[project\]([\s\S]*?)(?=\n\[|$)/);
        const versionMatch = projectSection?.[1]?.match(/version\s*=\s*"([^"]+)"/);
        return versionMatch?.[1] ?? null;
      } catch {
        return null;
      }
    })(),
    plugin_json: read("src/plugin/plugin.json", /"version"\s*:\s*"([^"]+)"/),
    product_registry: read(
      "obsidian_connector/product_registry.py",
      /__version__\s*=\s*"([^"]+)"/
    ),
    marketplace: read("marketplace.json", /"version"\s*:\s*"([^"]+)"/),
    mcpb: read("mcpb.json", /"version"\s*:\s*"([^"]+)"/),
  };
}
