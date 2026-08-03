import type { AuditSink, RegisteredTool } from "../types.js";
import type { PythonBridge } from "../bridge.js";
import { makeComparePoliciesTool } from "./compare-policies.js";
import { makeInspectLegalActionsTool } from "./inspect-legal-actions.js";
import { makeSimulateRoundTool } from "./simulate-round.js";

export function createToolRegistry(bridge: PythonBridge): readonly RegisteredTool[] {
  // The first vertical slice exposes only the operation implemented by the
  // Python bridge. Other adapters remain available for a later phase.
  return [makeSimulateRoundTool(bridge)];
}

export type { AuditSink };
export * from "./common.js";
export * from "./simulate-round.js";
export * from "./inspect-legal-actions.js";
export * from "./compare-policies.js";
