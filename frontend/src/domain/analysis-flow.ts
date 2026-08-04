import type { DecisionPacket } from "./contracts";

export type AnalysisFlowState =
  | { status: "choose" }
  | { status: "loading-example" }
  | { status: "example-ready"; packet: DecisionPacket }
  | { status: "example-error" };

export type AnalysisFlowAction =
  | { type: "OPEN_EXAMPLE" }
  | { type: "EXAMPLE_LOADED"; packet: DecisionPacket }
  | { type: "EXAMPLE_FAILED" }
  | { type: "RESET" };

export const initialAnalysisFlowState: AnalysisFlowState = { status: "choose" };

export function analysisFlowReducer(
  state: AnalysisFlowState,
  action: AnalysisFlowAction,
): AnalysisFlowState {
  switch (action.type) {
    case "OPEN_EXAMPLE":
      return state.status === "choose" || state.status === "example-error"
        ? { status: "loading-example" }
        : state;
    case "EXAMPLE_LOADED":
      return state.status === "loading-example"
        ? { status: "example-ready", packet: action.packet }
        : state;
    case "EXAMPLE_FAILED":
      return state.status === "loading-example" ? { status: "example-error" } : state;
    case "RESET":
      return initialAnalysisFlowState;
  }
}
