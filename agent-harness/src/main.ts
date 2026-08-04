#!/usr/bin/env node
import { access } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createHarnessSession } from "./session.js";
import { MemoryAuditSink } from "./audit.js";
import { createConfiguredModel, loadDotEnv } from "./model-config.js";

interface CliArgs {
  prompt?: string;
  replay?: string;
  cwd: string;
  bridge: string;
  python: string;
  tools: string[];
  toolsExplicit: boolean;
  skillDirs: string[];
}

async function main(): Promise<void> {
  const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  loadDotEnv([
    process.env.HARNESS_ENV_FILE ?? "",
    resolve(packageRoot, ".env"),
    resolve(process.cwd(), ".env"),
  ].filter(Boolean));
  const args = parseArgs(process.argv.slice(2), packageRoot);
  loadDotEnv([resolve(args.cwd, ".env")]);
  // A CLI replay is a user-approved input. Pin the child bridge to that exact
  // file so the model cannot turn a read-only analysis tool into arbitrary
  // filesystem discovery by changing replay_path in a later tool call.
  if (args.replay && process.env.HARNESS_REPLAY_FILE === undefined) {
    process.env.HARNESS_REPLAY_FILE = resolve(args.replay);
  }
  const stdinPrompt = args.prompt === undefined ? await readStdin() : "";
  const prompt = args.prompt ?? (stdinPrompt.trim() || (args.replay
    ? `Analyze the replay at ${JSON.stringify(args.replay)} with the analyze_replay tool. Return an evidence-grounded coaching summary.`
    : ""));
  if (!prompt.trim()) throw new Error("Provide a prompt as an argument or via stdin");
  try {
    await access(args.bridge);
  } catch {
    throw new Error(`Python bridge script not found: ${args.bridge}`);
  }
  const audit = new MemoryAuditSink();
  const configuredModel = await createConfiguredModel(process.env);
  const harness = await createHarnessSession({
    cwd: args.cwd,
    bridgeScript: args.bridge,
    pythonExecutable: args.python,
    allowedTools: args.tools,
    skillDirs: args.skillDirs,
    ...(configuredModel === undefined ? {} : configuredModel),
  }, audit);
  let stopping = false;
  const onSigint = (): void => {
    if (stopping) return;
    stopping = true;
    void harness.session.abort();
  };
  process.once("SIGINT", onSigint);
  const unsubscribe = harness.session.subscribe((event: unknown) => {
    if (!isRecord(event)) return;
    const assistant = event.assistantMessageEvent;
    if (isRecord(assistant) && assistant.type === "text_delta" && typeof assistant.delta === "string") {
      process.stdout.write(assistant.delta);
    }
    if (event.type === "tool_execution_start" && typeof event.toolName === "string") {
      process.stderr.write(`\n[tool:${event.toolName}]\n`);
    }
  });
  try {
    await harness.session.prompt(prompt);
    process.stdout.write("\n");
  } finally {
    unsubscribe();
    process.removeListener("SIGINT", onSigint);
    harness.dispose();
  }
}

export function parseArgs(argv: readonly string[], packageRoot: string): CliArgs {
  const result: CliArgs = {
    cwd: process.env.HARNESS_CWD ? resolve(process.env.HARNESS_CWD) : packageRoot,
    bridge: process.env.HARNESS_BRIDGE ? resolve(process.env.HARNESS_BRIDGE) : resolve(packageRoot, "src", "cs2_sim", "agent_bridge.py"),
    python: process.env.HARNESS_PYTHON ?? "python",
    tools: ["simulate_round"],
    toolsExplicit: false,
    skillDirs: [resolve(packageRoot, "skills")],
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = (): string => argv[++index] ?? "";
    switch (arg) {
      case "--prompt": result.prompt = next(); break;
      case "--replay":
        result.replay = next();
        if (!result.toolsExplicit && !result.tools.includes("analyze_replay")) result.tools.push("analyze_replay");
        break;
      case "--cwd": result.cwd = resolve(next()); break;
      case "--bridge": result.bridge = resolve(next()); break;
      case "--python": result.python = next(); break;
      case "--tool":
        result.tools = next().split(",").map((tool) => tool.trim()).filter(Boolean);
        result.toolsExplicit = true;
        break;
      case "--no-tools":
        result.tools = [];
        result.toolsExplicit = true;
        break;
      case "--skill-dir": result.skillDirs.push(resolve(next())); break;
      case "--help":
        process.stdout.write("Usage: npm run dev -- --prompt <text> [--replay path] [--bridge path] [--tool name | --no-tools]\n");
        process.exit(0);
        break;
      default:
        if (arg.startsWith("--")) throw new Error(`Unknown option: ${arg}`);
        result.prompt = result.prompt ? `${result.prompt} ${arg}` : arg;
    }
  }
  return result;
}

async function readStdin(): Promise<string> {
  if (process.stdin.isTTY) return "";
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8").trim();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
const modulePath = resolve(fileURLToPath(import.meta.url));
if (invokedPath !== "" && invokedPath === modulePath) {
  main().catch((error: unknown) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
