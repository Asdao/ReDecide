import { resolve } from "node:path";
import { Type } from "@sinclair/typebox";
import {
  createAgentSession,
  DefaultResourceLoader,
  defineTool,
  SessionManager,
  type AgentSession,
  type Skill,
} from "@earendil-works/pi-coding-agent";
import { PythonBridge } from "./bridge.js";
import { auditEvent, noopAuditSink } from "./audit.js";
import { newCallId, newCorrelationId } from "./ids.js";
import { ToolRegistry } from "./policy.js";
import type { AuditSink, HarnessConfig, RegisteredTool } from "./types.js";
import { boundedJson, executeThroughPolicy } from "./tools/common.js";
import { createToolRegistry } from "./tools/index.js";
import { discoverSkills as discoverSkillDescriptors } from "./skills.js";

export interface HarnessSession {
  readonly session: AgentSession;
  readonly registry: ToolRegistry;
  readonly bridge: PythonBridge;
  readonly correlationId: string;
  readonly audit: AuditSink;
  dispose(): void;
}

export const DEFAULT_HARNESS_CONFIG: Omit<HarnessConfig, "cwd" | "bridgeScript"> = {
  skillDirs: [],
  allowedTools: ["simulate_round"],
  sessionMode: "memory",
  maxToolCallsPerTurn: 8,
  toolTimeoutMs: 30_000,
  pythonExecutable: "python",
  maxBridgeOutputBytes: 256_000,
};

/** Build a Pi AgentSession with only explicitly registered, read-only tools. */
export async function createHarnessSession(
  partial: Partial<HarnessConfig> & Pick<HarnessConfig, "cwd" | "bridgeScript">,
  audit: AuditSink = noopAuditSink(),
): Promise<HarnessSession> {
  const config: HarnessConfig = { ...DEFAULT_HARNESS_CONFIG, ...partial };
  const correlationId = newCorrelationId();
  audit.write(auditEvent("request_started", correlationId));
  const bridge = new PythonBridge({
    executable: config.pythonExecutable,
    scriptPath: config.bridgeScript,
    cwd: config.bridgeCwd ?? config.cwd,
    timeoutMs: config.toolTimeoutMs,
    maxOutputBytes: config.maxBridgeOutputBytes,
    operations: ["simulate_round", "analyze_replay"],
    audit,
  });
  const registry = new ToolRegistry(config.allowedTools, config.maxToolCallsPerTurn, audit);
  for (const tool of createToolRegistry(bridge)) registry.register(tool);
  const skills = await loadPiSkills(config.skillDirs);
  const loader = new DefaultResourceLoader({
    cwd: config.cwd,
    // Keep resource loading local and explicit; the harness must not inherit global extensions.
    agentDir: resolve(config.cwd, ".pi-agent-harness"),
    noExtensions: true,
    noSkills: true,
    skillsOverride: (current) => {
      const existing = new Set(current.skills.map((skill) => skill.name));
      const collisions = skills.filter((skill) => existing.has(skill.name));
      if (collisions.length > 0) {
        throw new Error(`Duplicate skill name(s): ${collisions.map((skill) => skill.name).join(", ")}`);
      }
      return { skills: [...current.skills, ...skills], diagnostics: current.diagnostics };
    },
  });
  await loader.reload();
  const turnCounter = { value: 0 };
  const unknownConfiguredTools = config.allowedTools.filter((name) => registry.get(name) === undefined);
  if (unknownConfiguredTools.length > 0) {
    throw new Error(`Unknown configured tool(s): ${unknownConfiguredTools.join(", ")}`);
  }
  const enabledNames = [...config.allowedTools];
  const customTools = enabledNames.map((name) => makePiTool(registry.get(name)!, registry, audit, correlationId, turnCounter));
  const manager = config.sessionMode === "persisted" ? SessionManager.create(config.cwd) : SessionManager.inMemory();
  const options: Record<string, unknown> = {
    cwd: config.cwd,
    resourceLoader: loader,
    sessionManager: manager,
    // Pi's builtin tools are disabled while custom tools are kept active.
    noTools: "builtin",
    tools: enabledNames,
    customTools,
    thinkingLevel: config.thinkingLevel ?? "off",
  };
  if (config.model !== undefined) options.model = config.model;
  if (config.modelRuntime !== undefined) options.modelRuntime = config.modelRuntime;
  const result = await createAgentSession(options as never);
  const session = result.session as AgentSession;
  // Pi emits agent_start for each model turn. Resetting here enforces a per-turn, not global, limit.
  session.subscribe((event: unknown) => {
    if (typeof event === "object" && event !== null && "type" in event && ((event as { type?: unknown }).type === "agent_start" || (event as { type?: unknown }).type === "turn_start")) {
      turnCounter.value = 0;
    }
  });
  return {
    session,
    registry,
    bridge,
    correlationId,
    audit,
    dispose: () => {
      audit.write(auditEvent("request_finished", correlationId));
      session.dispose();
    },
  };
}

function makePiTool(
  registered: RegisteredTool,
  registry: ToolRegistry,
  audit: AuditSink,
  correlationId: string,
  turnCounter: { value: number },
): unknown {
  const parameters = parametersFor(registered.metadata.name);
  return defineTool({
    name: registered.metadata.name,
    label: registered.metadata.label,
    description: registered.metadata.description,
    parameters,
    execute: async (_toolCallId: string, params: unknown, signal?: AbortSignal) => {
      const callId = newCallId();
      const callsThisTurn = turnCounter.value;
      turnCounter.value += 1;
      const result = await executeThroughPolicy(registry, audit, registered.metadata.name, params, {
        correlationId,
        callId,
        signal,
        callsThisTurn,
        timeoutMs: registered.metadata.timeoutMs,
      });
      const body = result.ok
        ? boundedJson(result.data, registered.metadata.maxResultBytes)
        : JSON.stringify({ error: result.error });
      return {
        content: [{ type: "text", text: body }],
        details: { ok: result.ok, ...(result.ok ? {} : { error: result.error }) },
      };
    },
  } as never);
}

function parametersFor(name: string): unknown {
  switch (name) {
    case "simulate_round":
      return Type.Object({
        seed: Type.Optional(Type.Integer({ minimum: -2_147_483_648, maximum: 2_147_483_647 })),
        scenario: Type.Union([Type.Literal("example"), Type.Literal("planted")]),
        policy: Type.Union([Type.Literal("baseline"), Type.Literal("bayesian")]),
        max_events: Type.Optional(Type.Integer({ minimum: 1, maximum: 100 })),
      }, { additionalProperties: false });
    case "analyze_replay":
      return Type.Object({
        replay_path: Type.Optional(Type.String({ minLength: 1, maxLength: 2_048 })),
        max_decisions: Type.Optional(Type.Integer({ minimum: 1, maximum: 500 })),
        max_timeline_points: Type.Optional(Type.Integer({ minimum: 1, maximum: 500 })),
        sample_every: Type.Optional(Type.Integer({ minimum: 1, maximum: 256 })),
        version: Type.Optional(Type.String({ minLength: 1, maxLength: 32 })),
        decision_id: Type.Optional(Type.String({ minLength: 1, maxLength: 256 })),
      }, { additionalProperties: false });
    case "inspect_legal_actions":
      return Type.Object({
        state: Type.Record(Type.String(), Type.Unknown()),
        player: Type.String({ minLength: 1, maxLength: 64 }),
      }, { additionalProperties: false });
    case "compare_policies":
      return Type.Object({
        scenario: Type.String({ minLength: 1, maxLength: 64 }),
        policies: Type.Array(Type.String({ minLength: 1, maxLength: 64 }), { minItems: 1, maxItems: 4 }),
        seeds: Type.Optional(Type.Array(Type.Integer({ minimum: -2_147_483_648, maximum: 2_147_483_647 }), { maxItems: 16 })),
      }, { additionalProperties: false });
    default:
      throw new Error(`No schema for registered tool: ${name}`);
  }
}

/** Load only reviewed SKILL.md files and fail startup for malformed/duplicate entries. */
async function loadPiSkills(skillDirs: readonly string[]): Promise<Skill[]> {
  return discoverSkillDescriptors(skillDirs).map((descriptor) => ({
    name: descriptor.name,
    description: descriptor.description,
    filePath: descriptor.filePath,
    baseDir: descriptor.baseDir,
    sourceInfo: {
      path: descriptor.filePath,
      source: "custom",
      scope: "project",
      origin: "top-level",
      baseDir: descriptor.baseDir,
    },
    disableModelInvocation: false,
  }));
}
