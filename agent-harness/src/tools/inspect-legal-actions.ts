import type { PythonBridge } from "../bridge.js";
import type { RegisteredTool, ToolExecutionContext } from "../types.js";
import { ToolInputError } from "./common.js";

export interface InspectLegalActionsArgs {
  readonly state: Record<string, unknown>;
  readonly player: string;
}

export function validateInspectLegalActions(value: unknown): InspectLegalActionsArgs {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new ToolInputError("INVALID_ARGUMENTS", "Arguments must be an object");
  const object = value as Record<string, unknown>;
  for (const key of Object.keys(object)) if (!["state", "player"].includes(key)) throw new ToolInputError("UNKNOWN_ARGUMENT", `Unknown argument: ${key}`);
  if (typeof object.state !== "object" || object.state === null || Array.isArray(object.state)) throw new ToolInputError("INVALID_STATE", "state must be an object");
  if (typeof object.player !== "string" || object.player.length < 1 || object.player.length > 64) throw new ToolInputError("INVALID_PLAYER", "player must be a short string");
  return { state: object.state as Record<string, unknown>, player: object.player };
}

export function makeInspectLegalActionsTool(bridge: PythonBridge): RegisteredTool<InspectLegalActionsArgs> {
  return {
    metadata: {
      name: "inspect_legal_actions",
      label: "Inspect legal actions",
      description: "List legal actions for one player in a supplied simulator state.",
      effect: "read",
      approval: "never",
      timeoutMs: 10_000,
      maxResultBytes: 32_000,
      maxCallsPerTurn: 4,
    },
    validate: validateInspectLegalActions,
    execute: (args, context: ToolExecutionContext) => bridge.call("inspect_legal_actions", args as unknown as Record<string, unknown>, context),
  };
}
