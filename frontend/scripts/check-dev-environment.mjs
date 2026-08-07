import { existsSync, readFileSync, readdirSync } from "node:fs";
import { arch, argv, env, exit, platform, versions } from "node:process";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { release } from "node:os";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDirectory, "..");
const installing = argv.includes("--install");
const problems = [];

const nodeMajor = Number.parseInt(versions.node.split(".")[0] ?? "", 10);
if (nodeMajor !== 24) {
  problems.push(`Node 24.x is required; found ${versions.node}.`);
}

const packageManager = env.npm_config_user_agent?.split(" ")[0];
if (packageManager && !packageManager.startsWith("pnpm/")) {
  problems.push(`Use pnpm 11.x for this project; found ${packageManager}.`);
}
if (packageManager?.startsWith("pnpm/")) {
  const pnpmMajor = Number.parseInt(packageManager.slice("pnpm/".length).split(".")[0] ?? "", 10);
  if (pnpmMajor !== 11) {
    problems.push(`pnpm 11.x is required; found ${packageManager}.`);
  }
}

const normalizedRoot = frontendRoot.replaceAll("\\", "/");
const isWsl = platform === "linux" && /microsoft/i.test(release());
if (isWsl && /^\/mnt\/[a-z]\//i.test(normalizedRoot)) {
  problems.push(
    "Do not install or run the frontend from WSL against /mnt/<drive>. " +
      "Use Windows PowerShell for this checkout, or clone the repository into the native WSL filesystem first.",
  );
}

if (!installing) {
  const virtualStore = join(frontendRoot, "node_modules", ".pnpm");
  if (!existsSync(virtualStore)) {
    problems.push("node_modules is missing; run pnpm install --frozen-lockfile from this same operating system.");
  } else {
    const entries = readdirSync(virtualStore);
    const expectedNativePackages =
      platform === "win32" && arch === "x64"
        ? ["@next+swc-win32-x64-msvc@", "@tailwindcss+oxide-win32-x64-msvc@"]
        : platform === "linux" && arch === "x64"
          ? ["@next+swc-linux-x64-gnu@", "@tailwindcss+oxide-linux-x64-gnu@"]
          : [];

    for (const expectedPackage of expectedNativePackages) {
      if (!entries.some((entry) => entry.startsWith(expectedPackage))) {
        problems.push(
          `The native dependency ${expectedPackage.slice(0, -1)} is missing for ${platform}/${arch}. ` +
            "Reinstall node_modules from this same operating system.",
        );
      }
    }

    const modulesMetadata = join(frontendRoot, "node_modules", ".modules.yaml");
    if (existsSync(modulesMetadata)) {
      const metadata = readFileSync(modulesMetadata, "utf8");
      if (platform === "win32" && /\"storeDir\"\s*:\s*\"\/(?:home|mnt)\//.test(metadata)) {
        problems.push("node_modules was installed from Linux/WSL; reinstall it from Windows PowerShell.");
      }
      if (platform === "linux" && /\"storeDir\"\s*:\s*\"[A-Za-z]:\\\\/.test(metadata)) {
        problems.push("node_modules was installed from Windows; reinstall it from this Linux environment.");
      }
    }
  }
}

if (problems.length > 0) {
  console.error("\nFrontend environment check failed:\n");
  for (const problem of problems) console.error(`- ${problem}`);
  console.error("\nSee docs/JAVASCRIPT_SETUP.md for the supported recovery steps.\n");
  exit(1);
}

console.log(`Frontend environment OK: Node ${versions.node}, ${platform}/${arch}.`);
