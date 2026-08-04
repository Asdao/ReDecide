import type { AuditSink, RegisteredTool } from "../types.js";
import type { PythonBridge } from "../bridge.js";
import { makeSimulateRoundTool } from "./simulate-round.js";
import { makeAnalyzeReplayTool } from "./analyze-replay.js";

export function createToolRegistry(bridge: PythonBridge): readonly RegisteredTool[] {
  return [makeSimulateRoundTool(bridge), makeAnalyzeReplayTool(bridge)];
}

export type { AuditSink };
export * from "./common.js";
export * from "./simulate-round.js";
export * from "./analyze-replay.js";
export * from "./inspect-legal-actions.js";
export * from "./compare-policies.js";
