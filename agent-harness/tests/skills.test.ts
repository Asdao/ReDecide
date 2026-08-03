import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { discoverSkills, SkillValidationError } from "../src/skills.js";

const temporaryDirectories: string[] = [];

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

function skillDirectory(name: string, description = "A valid test skill"): string {
  const root = mkdtempSync(join(tmpdir(), "agent-harness-skills-"));
  temporaryDirectories.push(root);
  const directory = join(root, name);
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, "SKILL.md"), `---\nname: ${name}\ndescription: ${description}\n---\n\n# Instructions\n`, "utf8");
  return root;
}

describe("discoverSkills", () => {
  it("discovers valid skills deterministically", () => {
    const root = skillDirectory("analyze-cs2-round");
    const skills = discoverSkills([root]);
    expect(skills).toHaveLength(1);
    expect(skills[0]?.name).toBe("analyze-cs2-round");
  });

  it("rejects missing descriptions", () => {
    const root = skillDirectory("missing-description", "");
    expect(() => discoverSkills([root])).toThrowError(SkillValidationError);
  });

  it("rejects duplicate names across directories", () => {
    const first = skillDirectory("same-skill");
    const second = skillDirectory("same-skill");
    expect(() => discoverSkills([first, second])).toThrowError(/Duplicate skill name/);
  });
});

