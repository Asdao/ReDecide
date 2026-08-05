"use client";

import { useEffect, useReducer, useRef } from "react";
import { getSamples, selectSample } from "@/adapters/samples-api";
import {
  analysisFlowReducer,
  initialAnalysisFlowState,
} from "@/domain/analysis-flow";
import { LandingScreen } from "./LandingScreen";
import { ProductHeader } from "./ProductHeader";
import { SampleSelectorScreen } from "./SampleSelectorScreen";

export function DecisionFlow() {
  const [state, dispatch] = useReducer(analysisFlowReducer, initialAnalysisFlowState);
  const previousStatus = useRef(state.status);

  useEffect(() => {
    if (state.status !== "loading-samples") {
      return;
    }

    const controller = new AbortController();
    getSamples(controller.signal)
      .then((samples) => dispatch({ type: "SAMPLES_LOADED", samples }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          dispatch({ type: "SAMPLES_FAILED" });
        }
      });

    return () => controller.abort();
  }, [state.status]);

  useEffect(() => {
    if (state.status !== "selecting-sample") {
      return;
    }

    const controller = new AbortController();
    const sampleId = state.sampleId;
    selectSample(sampleId, controller.signal)
      .then((preparation) => dispatch({ type: "SAMPLE_SELECTED", sampleId, preparation }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          dispatch({ type: "SAMPLE_SELECTION_FAILED", sampleId });
        }
      });

    return () => controller.abort();
  }, [state]);

  useEffect(() => {
    const wasOnLanding = previousStatus.current === "choose";
    const isOnLanding = state.status === "choose";

    if (wasOnLanding === isOnLanding) {
      previousStatus.current = state.status;
      return;
    }

    previousStatus.current = state.status;
    const headingId = isOnLanding ? "page-title" : "samples-title";
    document.getElementById(headingId)?.focus();
  }, [state.status]);

  const openSamples = () => dispatch({ type: "OPEN_SAMPLES" });
  const reset = () => dispatch({ type: "RESET" });

  return (
    <main className="shell">
      <ProductHeader />
      {state.status === "choose" ? (
        <LandingScreen onOpenExample={openSamples} />
      ) : (
        <SampleSelectorScreen
          status={
            state.status === "loading-samples"
              ? "loading"
              : state.status === "samples-error"
                ? "error"
                : "ready"
          }
          samples={"samples" in state ? state.samples : []}
          selectingSampleId={state.status === "selecting-sample" ? state.sampleId : undefined}
          selectedSampleId={state.status === "sample-selected" ? state.sampleId : undefined}
          preparation={state.status === "sample-selected" ? state.preparation : undefined}
          selectionFailedId={
            state.status === "sample-selection-error" ? state.sampleId : undefined
          }
          onBack={reset}
          onRetry={openSamples}
          onSelect={(sampleId) => dispatch({ type: "SELECT_SAMPLE", sampleId })}
        />
      )}
    </main>
  );
}
