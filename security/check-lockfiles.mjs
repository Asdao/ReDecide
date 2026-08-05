import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const securityDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = dirname(securityDir);
const projects = ["frontend", "agent-harness"];

const failures = [];

function fail(message) {
  failures.push(message);
}

function hasPolicyValue(text, key, expected) {
  const pattern = new RegExp(`^${key}:\\s*([^#\\r\\n]+)`, "m");
  return pattern.exec(text)?.[1]?.trim() === expected;
}

function resolutionBlocks(lockText) {
  const lines = lockText.split(/\r?\n/);
  const blocks = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = /^(\s+)resolution:\s*(.*)$/.exec(lines[index]);
    if (!match || match[1].length < 4) continue;
    const indent = match[1].length;
    const block = [match[2]];
    for (let next = index + 1; next < lines.length; next += 1) {
      const line = lines[next];
      if (line.trim() !== "" && (line.match(/^\s*/)?.[0].length ?? 0) <= indent) break;
      block.push(line.trim());
    }
    blocks.push(block.join(" "));
  }
  return blocks;
}

for (const project of projects) {
  const projectDir = join(repoRoot, project);
  const packageJson = JSON.parse(await readFile(join(projectDir, "package.json"), "utf8"));
  const workspace = await readFile(join(projectDir, "pnpm-workspace.yaml"), "utf8");
  const lockfile = await readFile(join(projectDir, "pnpm-lock.yaml"), "utf8");

  if (packageJson.packageManager !== "pnpm@11.9.0") {
    fail(`${project}: packageManager must be pnpm@11.9.0`);
  }
  for (const [key, expected] of [
    ["minimumReleaseAge", "10080"],
    ["minimumReleaseAgeStrict", "true"],
    ["blockExoticSubdeps", "true"],
    ["trustPolicy", "no-downgrade"],
  ]) {
    if (!hasPolicyValue(workspace, key, expected)) fail(`${project}: ${key} must be ${expected}`);
  }

  const buildSection = workspace.match(/(^|\n)allowBuilds:\n((?:\s{2}.+\n?)+)/)?.[2] ?? "";
  for (const line of buildSection.split(/\r?\n/).filter(Boolean)) {
    if (!/^(\s{2}).+:\s+(true|false)\s*$/.test(line)) {
      fail(`${project}: allowBuilds entries must use explicit true/false values`);
    }
  }

  if (!/^lockfileVersion:\s*['"]?9\.0['"]?/m.test(lockfile)) {
    fail(`${project}: unsupported or missing pnpm lockfileVersion`);
  }
  const blocks = resolutionBlocks(lockfile);
  if (blocks.length === 0) fail(`${project}: no package resolution entries found`);
  blocks.forEach((block, index) => {
    if (!/integrity:\s*sha512-/.test(block)) {
      fail(`${project}: resolution ${index + 1} is missing a sha512 integrity value`);
    }
    if (/(?:git\+|(?:^|\s)(?:git|tarball|url):\s*https?:|https?:\/\/[^ ]+\.tgz)/i.test(block)) {
      fail(`${project}: exotic git/tarball resolution found in entry ${index + 1}`);
    }
  });
}

if (failures.length > 0) {
  console.error("Dependency security checks failed:");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exitCode = 1;
} else {
  console.log("Dependency security checks passed: policy, toolchain, lockfile integrity, and sources are valid.");
}
