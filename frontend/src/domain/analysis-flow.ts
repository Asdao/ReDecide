import type { SamplePreparation, SampleSummary } from "./samples";

export type AnalysisFlowState =
  | { status: "choose" }
  | { status: "loading-samples" }
  | { status: "samples-error" }
  | { status: "samples-ready"; samples: SampleSummary[] }
  | { status: "selecting-sample"; samples: SampleSummary[]; sampleId: string }
  | {
      status: "sample-selected";
      samples: SampleSummary[];
      sampleId: string;
      preparation: SamplePreparation;
    }
  | { status: "sample-selection-error"; samples: SampleSummary[]; sampleId: string };

export type AnalysisFlowAction =
  | { type: "OPEN_SAMPLES" }
  | { type: "SAMPLES_LOADED"; samples: SampleSummary[] }
  | { type: "SAMPLES_FAILED" }
  | { type: "SELECT_SAMPLE"; sampleId: string }
  | { type: "SAMPLE_SELECTED"; sampleId: string; preparation: SamplePreparation }
  | { type: "SAMPLE_SELECTION_FAILED"; sampleId: string }
  | { type: "RESET" };

export const initialAnalysisFlowState: AnalysisFlowState = { status: "choose" };

export function analysisFlowReducer(
  state: AnalysisFlowState,
  action: AnalysisFlowAction,
): AnalysisFlowState {
  switch (action.type) {
    case "OPEN_SAMPLES":
      return state.status === "choose" || state.status === "samples-error"
        ? { status: "loading-samples" }
        : state;
    case "SAMPLES_LOADED":
      return state.status === "loading-samples"
        ? { status: "samples-ready", samples: action.samples }
        : state;
    case "SAMPLES_FAILED":
      return state.status === "loading-samples" ? { status: "samples-error" } : state;
    case "SELECT_SAMPLE": {
      if (
        state.status !== "samples-ready" &&
        state.status !== "sample-selected" &&
        state.status !== "sample-selection-error"
      ) {
        return state;
      }
      const sample = state.samples.find(({ sample_id }) => sample_id === action.sampleId);
      return sample?.available
        ? { status: "selecting-sample", samples: state.samples, sampleId: action.sampleId }
        : state;
    }
    case "SAMPLE_SELECTED":
      return state.status === "selecting-sample" && state.sampleId === action.sampleId
        ? {
            status: "sample-selected",
            samples: state.samples,
            sampleId: action.sampleId,
            preparation: action.preparation,
          }
        : state;
    case "SAMPLE_SELECTION_FAILED":
      return state.status === "selecting-sample" && state.sampleId === action.sampleId
        ? {
            status: "sample-selection-error",
            samples: state.samples,
            sampleId: action.sampleId,
          }
        : state;
    case "RESET":
      return initialAnalysisFlowState;
  }
}
