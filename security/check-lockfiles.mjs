import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const securityDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = dirname(securityDir);
const projects = ["frontend", "agent-harness"];
const requiredOverrides = {
  frontend: { postcss: "8.5.23", sharp: "0.35.0" },
  "agent-harness": { undici: "8.9.0" },
};

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

function policyList(text, key) {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim() === `${key}:`);
  if (start === -1) return [];
  const values = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    const match = /^\s{2}-\s+(.+?)\s*$/.exec(lines[index]);
    if (!match) break;
    values.push(match[1].replace(/^['"]|['"]$/g, ""));
  }
  return values;
}

function policyMap(text, key) {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim() === `${key}:`);
  if (start === -1) return {};
  const values = {};
  for (let index = start + 1; index < lines.length; index += 1) {
    const match = /^\s{2}([^:#]+):\s+([^#\s]+)\s*$/.exec(lines[index]);
    if (!match) break;
    values[match[1].replace(/^['"]|['"]$/g, "")] = match[2].replace(/^['"]|['"]$/g, "");
  }
  return values;
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
    ["minimumReleaseAge", "4320"],
    ["minimumReleaseAgeStrict", "true"],
    ["blockExoticSubdeps", "true"],
    ["trustPolicy", "no-downgrade"],
    ["verifyDepsBeforeRun", "error"],
  ]) {
    if (!hasPolicyValue(workspace, key, expected)) fail(`${project}: ${key} must be ${expected}`);
  }

  const buildSection = workspace.match(/(^|\n)allowBuilds:\n((?:\s{2}.+\n?)+)/)?.[2] ?? "";
  for (const line of buildSection.split(/\r?\n/).filter(Boolean)) {
    if (!/^(\s{2}).+:\s+(true|false)\s*$/.test(line)) {
      fail(`${project}: allowBuilds entries must use explicit true/false values`);
    }
  }
  for (const key of ["minimumReleaseAgeExclude", "trustPolicyExclude"]) {
    for (const selector of policyList(workspace, key)) {
      if (!/^(?:@[^/]+\/)?[^@\s]+@\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(selector)) {
        fail(`${project}: ${key} must contain exact package versions, found ${selector}`);
      }
    }
  }
  const overrides = policyMap(workspace, "overrides");
  for (const [name, version] of Object.entries(requiredOverrides[project])) {
    if (overrides[name] !== version) fail(`${project}: security override ${name} must be pinned to ${version}`);
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

const workflow = await readFile(join(repoRoot, ".github", "workflows", "dependency-security.yml"), "utf8");
const actionReferences = [...workflow.matchAll(/^\s*uses:\s*([^\s#]+)/gm)].map((match) => match[1]);
if (actionReferences.length === 0) fail("CI: no GitHub Actions references found");
for (const reference of actionReferences) {
  if (!/@[0-9a-f]{40}$/.test(reference)) fail(`CI: action is not pinned to a full commit SHA: ${reference}`);
}
for (const required of [
  "persist-credentials: false",
  "pnpm install --frozen-lockfile",
  "pnpm audit --audit-level=high",
  "node security/check-lockfiles.mjs",
]) {
  if (!workflow.includes(required)) fail(`CI: missing required control: ${required}`);
}
if (/^\s*schedule:/m.test(workflow)) fail("CI: scheduled runs are not allowed");
if (/defaults:[\s\S]*working-directory:\s*\$\{\{\s*matrix\./m.test(workflow)) {
  fail("CI: matrix expressions are not valid in defaults.run.working-directory");
}

if (failures.length > 0) {
  console.error("Dependency security checks failed:");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exitCode = 1;
} else {
  console.log("Dependency security checks passed: policy, toolchain, lockfiles, sources, and CI controls are valid.");
}
