import type { PythonBridge } from "../bridge.js";
import type { RegisteredTool, ToolExecutionContext } from "../types.js";
import { ToolInputError } from "./common.js";

export interface ComparePoliciesArgs {
  readonly scenario: string;
  readonly policies: readonly string[];
  readonly seeds?: readonly number[];
}

export function validateComparePolicies(value: unknown): ComparePoliciesArgs {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new ToolInputError("INVALID_ARGUMENTS", "Arguments must be an object");
  const object = value as Record<string, unknown>;
  for (const key of Object.keys(object)) if (!["scenario", "policies", "seeds"].includes(key)) throw new ToolInputError("UNKNOWN_ARGUMENT", `Unknown argument: ${key}`);
  if (typeof object.scenario !== "string" || object.scenario.length < 1 || object.scenario.length > 64) throw new ToolInputError("INVALID_SCENARIO", "scenario must be a short string");
  if (!Array.isArray(object.policies) || object.policies.length < 1 || object.policies.length > 4 || object.policies.some((p) => typeof p !== "string" || p.length < 1 || p.length > 64)) throw new ToolInputError("INVALID_POLICIES", "policies must contain 1-4 short names");
  if (object.seeds !== undefined && (!Array.isArray(object.seeds) || object.seeds.length > 16 || object.seeds.some((seed) => !Number.isInteger(seed) || (seed as number) < -2_147_483_648 || (seed as number) > 2_147_483_647))) throw new ToolInputError("INVALID_SEEDS", "seeds must contain at most 16 signed 32-bit integers");
  return { scenario: object.scenario, policies: object.policies as string[], seeds: object.seeds as number[] | undefined };
}

export function makeComparePoliciesTool(bridge: PythonBridge): RegisteredTool<ComparePoliciesArgs> {
  return {
    metadata: {
      name: "compare_policies",
      label: "Compare policies",
      description: "Run a bounded seeded batch and compare aggregate CS2 policy metrics.",
      effect: "read",
      approval: "never",
      timeoutMs: 30_000,
      maxResultBytes: 64_000,
      maxCallsPerTurn: 2,
    },
    validate: validateComparePolicies,
    execute: (args, context: ToolExecutionContext) => bridge.call("compare_policies", args as unknown as Record<string, unknown>, context),
  };
}
