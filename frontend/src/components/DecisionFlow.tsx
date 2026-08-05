"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  ReplayApiError,
  getAnalysisPlayers,
  getAnalysisResult,
  getAnalysisStatus,
  prepareReplayAnalysis,
  runReplayCoaching,
  uploadReplay,
} from "@/adapters/replay-api";
import { getSamples, selectSample } from "@/adapters/samples-api";
import { getShowcaseReplay } from "@/adapters/showcase-replay";
import {
  analysisFlowReducer,
  initialAnalysisFlowState,
  resultRecoveryDisposition,
  type AnalysisFlowState,
  type ReplayFlowError,
  type ReplayFlowErrorCode,
  type SampleAnalysisFlowState,
} from "@/domain/analysis-flow";
import {
  isLandingChildHistoryEntry,
  landingViewFromSearch,
  landingViewHref,
  withLandingHistoryMarker,
  type LandingView,
} from "@/domain/landing-navigation";
import { LandingScreen } from "./LandingScreen";
import { ProductHeader } from "./ProductHeader";
import { ReplayFlowScreen } from "./ReplayFlowScreen";
import { SampleSelectorScreen } from "./SampleSelectorScreen";
import { ShowcasePlayerScreen } from "./ShowcasePlayerScreen";
import type { ShowcaseReplay } from "@/domain/replay-viewer";

const PLAYER_PREPARATION_TIMEOUT_MS = 90_000;
const PLAYER_POLL_INTERVAL_MS = 1_000;
const COACHING_TIMEOUT_MS = 45_000;
const RECOVERY_GRACE_MS = 1_500;
const RECOVERY_TIMEOUT_MS = 45_000;

const sampleStatuses = new Set<AnalysisFlowState["status"]>([
  "loading-samples",
  "samples-error",
  "samples-ready",
  "selecting-sample",
  "sample-selected",
  "sample-selection-error",
]);

function isSampleState(state: AnalysisFlowState): state is SampleAnalysisFlowState {
  return sampleStatuses.has(state.status);
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function flowError(
  error: unknown,
  fallbackCode: ReplayFlowErrorCode,
  fallbackMessage: string,
): ReplayFlowError {
  if (!(error instanceof ReplayApiError)) {
    return { code: fallbackCode, message: fallbackMessage, retryable: true };
  }

  const code = error.kind === "invalid-file" ? "invalid-file" : fallbackCode;
  const retryable =
    error.kind === "network" ||
    error.kind === "non-json" ||
    error.kind === "malformed-json" ||
    error.kind === "not-ready" ||
    error.kind === "server";
  return { code, message: error.message, retryable };
}

function isAmbiguousCoachingFailure(error: unknown): boolean {
  return (
    !(error instanceof ReplayApiError) ||
    error.kind === "network" ||
    error.kind === "non-json" ||
    error.kind === "malformed-json" ||
    error.kind === "invalid-response"
  );
}

export function DecisionFlow() {
  const router = useRouter();
  const [state, dispatch] = useReducer(analysisFlowReducer, initialAnalysisFlowState);
  const [showcase, setShowcase] = useState<
    | { status: "idle" }
    | { status: "loading"; attempt: number }
    | { status: "error"; message: string; attempt: number }
    | { status: "ready"; replay: ShowcaseReplay; attempt: number }
  >({ status: "idle" });
  const currentScreen = showcase.status === "idle" ? state.status : "showcase";
  const previousScreen = useRef(currentScreen);
  const requestSequence = useRef(0);
  const nextRequestId = useCallback((operation: string) => {
    requestSequence.current += 1;
    return `${operation}-${requestSequence.current}`;
  }, []);

  const loadShowcase = useCallback(() => {
    setShowcase((current) => ({
      status: "loading",
      attempt: "attempt" in current ? current.attempt + 1 : 1,
    }));
  }, []);

  const applyLandingView = useCallback(
    (view: LandingView) => {
      dispatch({ type: "RESET" });
      if (view === "samples") {
        setShowcase({ status: "idle" });
        dispatch({ type: "OPEN_SAMPLES" });
        return;
      }
      if (view === "showcase") {
        loadShowcase();
        return;
      }
      setShowcase({ status: "idle" });
    },
    [loadShowcase],
  );

  useEffect(() => {
    const syncFromLocation = () => {
      applyLandingView(landingViewFromSearch(window.location.search));
    };

    const initialView = landingViewFromSearch(window.location.search);
    if (initialView === "home") {
      window.history.replaceState(
        withLandingHistoryMarker(window.history.state, "home", false),
        "",
        landingViewHref("home", window.location.search),
      );
    } else if (!isLandingChildHistoryEntry(window.history.state, initialView)) {
      const currentSearch = window.location.search;
      const homeState = withLandingHistoryMarker(window.history.state, "home", false);
      window.history.replaceState(
        homeState,
        "",
        landingViewHref("home", currentSearch),
      );
      window.history.pushState(
        withLandingHistoryMarker(homeState, initialView, true),
        "",
        landingViewHref(initialView, currentSearch),
      );
    }

    syncFromLocation();
    window.addEventListener("popstate", syncFromLocation);
    return () => window.removeEventListener("popstate", syncFromLocation);
  }, [applyLandingView]);

  useEffect(() => {
    if (showcase.status !== "loading") {
      return;
    }

    const controller = new AbortController();
    const attempt = showcase.attempt;
    getShowcaseReplay(controller.signal)
      .then((replay) => setShowcase({ status: "ready", replay, attempt }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setShowcase({
            status: "error",
            message: error instanceof Error ? error.message : "The Mirage showcase could not be loaded.",
            attempt,
          });
        }
      });

    return () => controller.abort();
  }, [showcase]);

  useEffect(() => {
    if (state.status !== "loading-samples") {
      return;
    }

    const controller = new AbortController();
    getSamples(controller.signal)
      .then((samples) => dispatch({ type: "SAMPLES_LOADED", samples }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
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
        if (!isAbortError(error)) {
          dispatch({ type: "SAMPLE_SELECTION_FAILED", sampleId });
        }
      });

    return () => controller.abort();
  }, [state]);

  useEffect(() => {
    if (state.status !== "uploading") {
      return;
    }

    const controller = new AbortController();
    const requestId = state.requestId;
    uploadReplay(state.file, controller.signal)
      .then((manifest) =>
        dispatch({
          type: "UPLOAD_SUCCEEDED",
          requestId,
          manifest,
          prepareRequestId: nextRequestId("prepare"),
        }),
      )
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          dispatch({
            type: "UPLOAD_FAILED",
            requestId,
            error: flowError(error, "upload-failed", "The replay could not be uploaded."),
          });
        }
      });

    return () => controller.abort();
  }, [nextRequestId, state]);

  useEffect(() => {
    if (state.status !== "preparing-analysis") {
      return;
    }

    const controller = new AbortController();
    const requestId = state.requestId;
    prepareReplayAnalysis(state.manifest.replay_id, controller.signal)
      .then((analysis) =>
        dispatch({
          type: "ANALYSIS_PREPARED",
          requestId,
          analysis,
          playersRequestId: nextRequestId("players"),
        }),
      )
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          dispatch({
            type: "ANALYSIS_PREPARE_FAILED",
            requestId,
            error: flowError(
              error,
              "prepare-failed",
              "The uploaded replay could not be prepared for analysis.",
            ),
          });
        }
      });

    return () => controller.abort();
  }, [nextRequestId, state]);

  useEffect(() => {
    if (state.status !== "waiting-for-players") {
      return;
    }

    const controller = new AbortController();
    const requestId = state.requestId;
    const analysisId = state.analysis.analysis_id;
    const deadline = Date.now() + PLAYER_PREPARATION_TIMEOUT_MS;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const poll = async () => {
      try {
        const response = await getAnalysisPlayers(analysisId, controller.signal);
        if (cancelled) {
          return;
        }
        if (response.state === "ready") {
          dispatch({
            type: "PLAYERS_LOADED",
            requestId,
            analysisId: response.value.analysis_id,
            players: response.value.players,
          });
          return;
        }

        const status = await getAnalysisStatus(analysisId, controller.signal);
        if (status.status === "failed") {
          dispatch({
            type: "PLAYERS_FAILED",
            requestId,
            error: {
              code: "prepare-failed",
              message: "The replay could not be prepared for player selection.",
              retryable: true,
            },
          });
          return;
        }
        if (Date.now() >= deadline) {
          dispatch({
            type: "PLAYERS_FAILED",
            requestId,
            error: {
              code: "players-failed",
              message: "Player preparation is taking longer than expected.",
              retryable: true,
            },
          });
          return;
        }
        timer = setTimeout(poll, PLAYER_POLL_INTERVAL_MS);
      } catch (error: unknown) {
        if (!isAbortError(error)) {
          dispatch({
            type: "PLAYERS_FAILED",
            requestId,
            error: flowError(
              error,
              "players-failed",
              "The player list could not be loaded.",
            ),
          });
        }
      }
    };

    void poll();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [state]);

  useEffect(() => {
    if (state.status !== "running-coaching") {
      return;
    }

    const controller = new AbortController();
    const requestId = state.requestId;
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, COACHING_TIMEOUT_MS);

    runReplayCoaching(
      state.analysis.analysis_id,
      state.selectedPlayer.player_id,
      controller.signal,
    )
      .then((result) => dispatch({ type: "COACHING_SUCCEEDED", requestId, result }))
      .catch((error: unknown) => {
        if (isAbortError(error) && !timedOut) {
          return;
        }
        if (timedOut || isAmbiguousCoachingFailure(error)) {
          dispatch({
            type: "COACHING_REQUEST_UNCERTAIN",
            requestId,
            recoveryRequestId: nextRequestId("recovery"),
          });
          return;
        }
        dispatch({
          type: "COACHING_FAILED",
          requestId,
          error: flowError(error, "coaching-failed", "Coaching could not be completed."),
        });
      })
      .finally(() => clearTimeout(timeout));

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [nextRequestId, state]);

  useEffect(() => {
    if (state.status !== "recovering-result") {
      return;
    }

    const controller = new AbortController();
    const requestId = state.requestId;
    const analysisId = state.analysis.analysis_id;
    const deadline = Date.now() + RECOVERY_TIMEOUT_MS;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const checkResult = async () => {
      try {
        const recovered = await getAnalysisResult(analysisId, controller.signal);
        if (cancelled) {
          return;
        }
        if (recovered.state === "ready") {
          dispatch({ type: "RESULT_RECOVERED", requestId, result: recovered.value });
          return;
        }

        const status = await getAnalysisStatus(analysisId, controller.signal);
        const disposition = resultRecoveryDisposition(status.status, Date.now() >= deadline);
        if (disposition === "retry-coaching") {
          dispatch({
            type: "RESULT_CONFIRMED_ABSENT",
            requestId,
            error: {
              code: "coaching-failed",
              message: "The coaching request failed before producing a result.",
              retryable: true,
            },
          });
          return;
        }
        if (disposition === "retry-result") {
          dispatch({
            type: "RESULT_RECOVERY_FAILED",
            requestId,
            error: {
              code: "result-recovery-failed",
              message:
                status.status === "complete"
                  ? "The completed coaching result could not be retrieved."
                  : "No completed result is available yet. Check again before retrying coaching.",
              retryable: true,
            },
          });
          return;
        }
        timer = setTimeout(checkResult, PLAYER_POLL_INTERVAL_MS);
      } catch (error: unknown) {
        if (!isAbortError(error)) {
          dispatch({
            type: "RESULT_RECOVERY_FAILED",
            requestId,
            error: flowError(
              error,
              "result-recovery-failed",
              "The completed coaching result could not be checked.",
            ),
          });
        }
      }
    };

    timer = setTimeout(checkResult, RECOVERY_GRACE_MS);
    return () => {
      cancelled = true;
      controller.abort();
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [state]);

  useEffect(() => {
    if (previousScreen.current === currentScreen) {
      return;
    }

    previousScreen.current = currentScreen;
    const headingId =
      currentScreen === "choose"
        ? "page-title"
        : currentScreen === "showcase"
          ? "replay-title"
          : isSampleState(state)
            ? "samples-title"
            : "replay-title";
    document.getElementById(headingId)?.focus();
  }, [currentScreen, state]);

  const openLandingView = (view: Exclude<LandingView, "home">) => {
    const href = landingViewHref(view, window.location.search);
    window.history.pushState(
      withLandingHistoryMarker(window.history.state, view, true),
      "",
      href,
    );
    applyLandingView(view);
  };
  const returnHome = () => {
    if (isLandingChildHistoryEntry(window.history.state)) {
      window.history.back();
      return;
    }

    window.history.replaceState(
      withLandingHistoryMarker(window.history.state, "home", false),
      "",
      landingViewHref("home", window.location.search),
    );
    applyLandingView("home");
  };

  let content;
  if (showcase.status !== "idle") {
    content = (
      <ShowcasePlayerScreen
        {...(showcase.status === "ready"
          ? { status: "ready" as const, replay: showcase.replay }
          : showcase.status === "error"
            ? { status: "error" as const, message: showcase.message }
            : { status: "loading" as const })}
        onBack={returnHome}
        onRetry={loadShowcase}
        onSelectPlayer={(player) =>
          router.push(`/analysis?player=${encodeURIComponent(player.player_id)}`)
        }
      />
    );
  } else if (state.status === "choose") {
    content = (
      <LandingScreen
        onOpenSamples={() => openLandingView("samples")}
        onOpenShowcase={() => openLandingView("showcase")}
        onSelectReplay={(file) =>
          dispatch({ type: "SELECT_REPLAY_FILE", file, requestId: nextRequestId("upload") })
        }
      />
    );
  } else if (isSampleState(state)) {
    content = (
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
        onBack={returnHome}
        onRetry={() => dispatch({ type: "OPEN_SAMPLES" })}
        onSelect={(sampleId) => dispatch({ type: "SELECT_SAMPLE", sampleId })}
      />
    );
  } else {
    content = (
      <ReplayFlowScreen
        state={state}
        onBack={returnHome}
        onRetryUpload={() =>
          dispatch({ type: "RETRY_UPLOAD", requestId: nextRequestId("upload") })
        }
        onRetryPrepare={() =>
          dispatch({ type: "RETRY_ANALYSIS_PREPARE", requestId: nextRequestId("prepare") })
        }
        onRetryPlayers={() =>
          dispatch({ type: "RETRY_PLAYERS", requestId: nextRequestId("players") })
        }
        onSelectPlayer={(playerId) =>
          dispatch({
            type: "SELECT_PLAYER",
            playerId,
            requestId: nextRequestId("coaching"),
          })
        }
        onRetryCoaching={() =>
          dispatch({ type: "RETRY_COACHING", requestId: nextRequestId("coaching") })
        }
        onRetryRecovery={() =>
          dispatch({
            type: "RETRY_RESULT_RECOVERY",
            requestId: nextRequestId("recovery"),
          })
        }
      />
    );
  }

  return (
    <main className="shell">
      <ProductHeader
        brandHref="/"
        onBrandClick={(event) => {
          event.preventDefault();
          returnHome();
        }}
      />
      {content}
    </main>
  );
}
