import type { PythonBridge } from "../bridge.js";
import type { RegisteredTool, ToolExecutionContext } from "../types.js";
import { ToolInputError } from "./common.js";

const REPLAY_SUFFIXES = new Set([".dem", ".json", ".jsonl"]);

export interface AnalyzeReplayArgs {
  readonly replay_path: string;
  readonly max_decisions?: number;
  readonly max_timeline_points?: number;
  readonly sample_every?: number;
  readonly version?: string;
  readonly decision_id?: string;
}

/** Validate the path and output bounds before crossing into the Python process. */
export function validateAnalyzeReplay(
  value: unknown,
  approvedReplayPath?: string,
): AnalyzeReplayArgs {
  const object = strictObject(value, [
    "replay_path",
    "max_decisions",
    "max_timeline_points",
    "sample_every",
    "version",
    "decision_id",
  ]);
  const pinnedReplayPath = approvedReplayPath?.trim();
  const replayPath = pinnedReplayPath
    ? boundedString(pinnedReplayPath, "approved replay path", 2_048)
    : boundedString(object.replay_path, "replay_path", 2_048);
  const suffix = replayPath.toLowerCase().slice(replayPath.lastIndexOf("."));
  if (!REPLAY_SUFFIXES.has(suffix)) {
    throw new ToolInputError("INVALID_REPLAY_PATH", "replay_path must end in .dem, .json, or .jsonl");
  }
  const maxDecisions = boundedInteger(object.max_decisions, "max_decisions", 1, 500);
  const maxTimelinePoints = boundedInteger(object.max_timeline_points, "max_timeline_points", 1, 500);
  const sampleEvery = boundedInteger(object.sample_every, "sample_every", 1, 256);
  const version = optionalString(object.version, "version", 32);
  const decisionId = optionalString(object.decision_id, "decision_id", 256);
  return {
    replay_path: replayPath,
    ...(maxDecisions === undefined ? {} : { max_decisions: maxDecisions }),
    ...(maxTimelinePoints === undefined ? {} : { max_timeline_points: maxTimelinePoints }),
    ...(sampleEvery === undefined ? {} : { sample_every: sampleEvery }),
    ...(version === undefined ? {} : { version }),
    ...(decisionId === undefined ? {} : { decision_id: decisionId }),
  };
}

export function makeAnalyzeReplayTool(
  bridge: PythonBridge,
  approvedReplayPath: string | undefined = process.env.HARNESS_REPLAY_FILE,
): RegisteredTool<AnalyzeReplayArgs> {
  return {
    metadata: {
      name: "analyze_replay",
      label: "Index replay decisions",
      description: "Analyze the replay approved for this session. Omit replay_path when a session replay is already approved. The tool indexes selector-ready players and first-damage decisions; outcome labels and private player identifiers are withheld from the model.",
      effect: "read",
      approval: "never",
      timeoutMs: 120_000,
      maxResultBytes: 220_000,
      maxCallsPerTurn: 2,
    },
    validate: (value: unknown) => validateAnalyzeReplay(value, approvedReplayPath),
    execute: (args: AnalyzeReplayArgs, context: ToolExecutionContext) =>
      bridge.call("analyze_replay", args as unknown as Record<string, unknown>, context),
  };
}

function strictObject(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ToolInputError("INVALID_ARGUMENTS", "Arguments must be a JSON object");
  }
  const object = value as Record<string, unknown>;
  for (const key of Object.keys(object)) {
    if (!keys.includes(key)) throw new ToolInputError("UNKNOWN_ARGUMENT", `Unknown argument: ${key}`);
  }
  return object;
}

function boundedString(value: unknown, field: string, maxLength: number): string {
  if (typeof value !== "string" || value.trim().length === 0 || value.length > maxLength) {
    throw new ToolInputError("INVALID_ARGUMENTS", `${field} must be a non-empty string of at most ${maxLength} characters`);
  }
  return value;
}

function optionalString(value: unknown, field: string, maxLength: number): string | undefined {
  if (value === undefined) return undefined;
  return boundedString(value, field, maxLength);
}

function boundedInteger(value: unknown, field: string, minimum: number, maximum: number): number | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "number" || !Number.isInteger(value) || value < minimum || value > maximum) {
    throw new ToolInputError("INVALID_ARGUMENTS", `${field} must be an integer between ${minimum} and ${maximum}`);
  }
  return value;
}
