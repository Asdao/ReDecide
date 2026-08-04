import { describe, expect, it } from "vitest";
import { loadSavedExample } from "@/adapters/saved-example";
import {
  analysisFlowReducer,
  initialAnalysisFlowState,
} from "@/domain/analysis-flow";

describe("saved example flow", () => {
  it("loads and validates the saved decision packet", () => {
    const packet = loadSavedExample();

    expect(packet.decision_id).toBe("fixture-match-7-PlayerA-12345");
    expect(packet.known_before_decision).toHaveLength(2);
  });

  it("moves from the landing page to loading and ready", () => {
    const loading = analysisFlowReducer(initialAnalysisFlowState, { type: "OPEN_EXAMPLE" });
    expect(loading).toEqual({ status: "loading-example" });

    const packet = loadSavedExample();
    const ready = analysisFlowReducer(loading, { type: "EXAMPLE_LOADED", packet });
    expect(ready).toEqual({ status: "example-ready", packet });
  });

  it("supports a safe error, retry, and reset", () => {
    const loading = analysisFlowReducer(initialAnalysisFlowState, { type: "OPEN_EXAMPLE" });
    const failed = analysisFlowReducer(loading, { type: "EXAMPLE_FAILED" });
    expect(failed).toEqual({ status: "example-error" });

    const retrying = analysisFlowReducer(failed, { type: "OPEN_EXAMPLE" });
    expect(retrying).toEqual({ status: "loading-example" });
    expect(analysisFlowReducer(retrying, { type: "RESET" })).toEqual({ status: "choose" });
  });

  it("ignores a loaded packet unless an example is being opened", () => {
    const packet = loadSavedExample();

    expect(
      analysisFlowReducer(initialAnalysisFlowState, { type: "EXAMPLE_LOADED", packet }),
    ).toEqual(initialAnalysisFlowState);
  });
});
