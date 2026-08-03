import type { PythonBridge } from "../bridge.js";
import type { RegisteredTool, ToolExecutionContext } from "../types.js";
import { ToolInputError } from "./common.js";

export interface SimulateRoundArgs {
  readonly seed?: number;
  readonly scenario: string;
  readonly policy: string;
  readonly max_events?: number;
}

export const SUPPORTED_SCENARIOS = ["example", "planted"] as const;
export const SUPPORTED_POLICIES = ["baseline", "bayesian"] as const;

export function validateSimulateRound(value: unknown): SimulateRoundArgs {
  const object = strictObject(value, ["seed", "scenario", "policy", "max_events"]);
  const seed = object.seed;
  if (seed !== undefined && (typeof seed !== "number" || !Number.isInteger(seed) || seed < -2_147_483_648 || seed > 2_147_483_647)) {
    throw new ToolInputError("INVALID_SEED", "seed must be a signed 32-bit integer");
  }
  const scenario = boundedString(object.scenario, "scenario");
  const policy = boundedString(object.policy, "policy");
  if (!(SUPPORTED_SCENARIOS as readonly string[]).includes(scenario)) throw new ToolInputError("INVALID_SCENARIO", "Unknown scenario");
  if (!(SUPPORTED_POLICIES as readonly string[]).includes(policy)) throw new ToolInputError("INVALID_POLICY", "Unknown policy");
  const maxEvents = object.max_events;
  if (maxEvents !== undefined && (typeof maxEvents !== "number" || !Number.isInteger(maxEvents) || maxEvents < 1 || maxEvents > 100)) {
    throw new ToolInputError("INVALID_EVENT_LIMIT", "max_events must be an integer between 1 and 100");
  }
  return {
    ...(seed === undefined ? {} : { seed }),
    scenario,
    policy,
    ...(maxEvents === undefined ? {} : { max_events: maxEvents }),
  };
}

export function makeSimulateRoundTool(bridge: PythonBridge): RegisteredTool<SimulateRoundArgs> {
  return {
    metadata: {
      name: "simulate_round",
      label: "Simulate CS2 round",
      description: "Run one bounded, deterministic CS2 round simulation and return key events.",
      effect: "read",
      approval: "never",
      timeoutMs: 30_000,
      maxResultBytes: 64_000,
      maxCallsPerTurn: 4,
    },
    validate: validateSimulateRound,
    execute: (args: SimulateRoundArgs, context: ToolExecutionContext) => bridge.call("simulate_round", args as unknown as Record<string, unknown>, context),
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

function boundedString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim().length === 0 || value.length > 64) {
    throw new ToolInputError("INVALID_ARGUMENTS", `${field} must be a non-empty string of at most 64 characters`);
  }
  return value;
}
