"use client";

import { useEffect, useReducer, useRef } from "react";
import { loadSavedExample } from "@/adapters/saved-example";
import {
  analysisFlowReducer,
  initialAnalysisFlowState,
} from "@/domain/analysis-flow";
import { AnalysisProgressScreen } from "./AnalysisProgressScreen";
import { LandingScreen } from "./LandingScreen";
import { ProductHeader } from "./ProductHeader";

export function DecisionFlow() {
  const [state, dispatch] = useReducer(analysisFlowReducer, initialAnalysisFlowState);
  const previousStatus = useRef(state.status);

  useEffect(() => {
    if (state.status !== "loading-example") {
      return;
    }

    try {
      const packet = loadSavedExample();
      dispatch({ type: "EXAMPLE_LOADED", packet });
    } catch {
      dispatch({ type: "EXAMPLE_FAILED" });
    }
  }, [state.status]);

  useEffect(() => {
    if (previousStatus.current === state.status) {
      return;
    }

    previousStatus.current = state.status;
    const headingId = state.status === "choose" ? "page-title" : "progress-title";
    document.getElementById(headingId)?.focus();
  }, [state.status]);

  const openExample = () => dispatch({ type: "OPEN_EXAMPLE" });
  const reset = () => dispatch({ type: "RESET" });

  return (
    <main className="shell">
      <ProductHeader />
      {state.status === "choose" ? (
        <LandingScreen onOpenExample={openExample} />
      ) : (
        <AnalysisProgressScreen
          status={
            state.status === "loading-example"
              ? "loading"
              : state.status === "example-ready"
                ? "ready"
                : "error"
          }
          packet={state.status === "example-ready" ? state.packet : undefined}
          onBack={reset}
          onRetry={openExample}
        />
      )}
    </main>
  );
}
