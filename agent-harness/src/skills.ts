import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

export interface SkillDescriptor {
  readonly name: string;
  readonly description: string;
  readonly filePath: string;
  readonly baseDir: string;
}

export class SkillValidationError extends Error {
  public constructor(public readonly code: string, message: string) {
    super(message);
    this.name = "SkillValidationError";
  }
}

const SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** Validate and discover only reviewed SKILL.md files from explicit directories. */
export function discoverSkills(skillDirs: readonly string[]): readonly SkillDescriptor[] {
  const files = skillDirs.flatMap((directory) => findSkillFiles(resolve(directory)));
  const descriptors = files.map(parseSkillFile);
  const seen = new Map<string, string>();
  for (const skill of descriptors) {
    const previous = seen.get(skill.name);
    if (previous) {
      throw new SkillValidationError(
        "DUPLICATE_SKILL",
        `Duplicate skill name '${skill.name}' in ${previous} and ${skill.filePath}`,
      );
    }
    seen.set(skill.name, skill.filePath);
  }
  return descriptors.sort((left, right) => left.name.localeCompare(right.name));
}

function findSkillFiles(directory: string): string[] {
  let entries;
  try {
    entries = readdirSync(directory, { withFileTypes: true });
  } catch (error) {
    if (isNodeError(error) && error.code === "ENOENT") return [];
    throw new SkillValidationError("SKILL_DIRECTORY", `Cannot read skill directory: ${directory}`);
  }

  const files: string[] = [];
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...findSkillFiles(path));
    else if (entry.isFile() && entry.name === "SKILL.md") files.push(path);
  }
  return files;
}

function parseSkillFile(filePath: string): SkillDescriptor {
  const content = readFileSync(filePath, "utf8");
  const frontmatter = parseFrontmatter(content, filePath);
  const name = frontmatter.name;
  const description = frontmatter.description;
  if (!name || !SKILL_NAME.test(name) || name.length > 64) {
    throw new SkillValidationError("INVALID_SKILL_NAME", `Invalid skill name in ${filePath}`);
  }
  if (!description || description.length > 1024) {
    throw new SkillValidationError("INVALID_SKILL_DESCRIPTION", `Invalid skill description in ${filePath}`);
  }
  return { name, description, filePath, baseDir: resolve(filePath, "..") };
}

function parseFrontmatter(content: string, filePath: string): Record<string, string> {
  const lines = content.split(/\r?\n/);
  if (lines[0]?.trim() !== "---") {
    throw new SkillValidationError("MISSING_FRONTMATTER", `Skill is missing frontmatter: ${filePath}`);
  }
  const end = lines.indexOf("---", 1);
  if (end < 0) throw new SkillValidationError("INVALID_FRONTMATTER", `Unclosed frontmatter: ${filePath}`);
  const values: Record<string, string> = {};
  for (const line of lines.slice(1, end)) {
    const separator = line.indexOf(":");
    if (separator <= 0) throw new SkillValidationError("INVALID_FRONTMATTER", `Invalid frontmatter: ${filePath}`);
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, "");
    if (key) values[key] = value;
  }
  return values;
}

function isNodeError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error;
}

