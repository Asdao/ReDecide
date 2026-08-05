"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  ReplayApiError,
  getAnalysisPlayers,
  getAnalysisResult,
  getAnalysisStatus,
  getReplayVisualization,
  prepareReplayWorkspace,
  runReplayCoaching,
  uploadReplay,
} from "@/adapters/replay-api";
import { getSamples, selectSample } from "@/adapters/samples-api";
import { getProcessedReplay } from "@/adapters/processed-replay";
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
  landingHistoryViewFromState,
  landingViewFromSearch,
  landingViewHref,
  withLandingHistoryMarker,
  type LandingView,
} from "@/domain/landing-navigation";
import { LandingScreen } from "./LandingScreen";
import { ProductHeader } from "./ProductHeader";
import { ReplayFlowScreen } from "./ReplayFlowScreen";
import { SampleSelectorScreen } from "./SampleSelectorScreen";
import { ProcessedReplaySelectorScreen } from "./ProcessedReplaySelectorScreen";
import { ProcessedReplayPlayerScreen } from "./ProcessedReplayPlayerScreen";
import { PROCESSED_REPLAYS, processedReplayById } from "@/domain/processed-replays";
import type { ProcessedReplay } from "@/domain/replay-viewer";
import { normalizeBackendReplay } from "@/domain/replay-viewer";
import type { ReplayAnalysisResult } from "@/domain/replay";
import { isAbortError } from "@/lib/http";
import { ReplayAnalysisScreen } from "./ReplayAnalysisScreen";
import { ReplayMapLoadingScreen } from "./ReplayMapLoadingScreen";

const PLAYER_PREPARATION_TIMEOUT_MS = 90_000;
const PLAYER_POLL_INTERVAL_MS = 1_000;
const COACHING_TIMEOUT_MS = 45_000;
const RECOVERY_GRACE_MS = 1_500;
const RECOVERY_TIMEOUT_MS = 45_000;
const VISUALIZATION_TIMEOUT_MS = 90_000;
const VISUALIZATION_POLL_INTERVAL_MS = 1_000;

type UploadedViewerCache = {
  selectedPlayerId: string;
  result: ReplayAnalysisResult;
  replay: ProcessedReplay;
};

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
  const [processedReplaysOpen, setProcessedReplaysOpen] = useState(false);
  const [processedReplay, setProcessedReplay] = useState<
    | { status: "catalog" }
    | { status: "loading"; replayId: string; attempt: number }
    | { status: "error"; replayId: string; attempt: number; message: string }
    | { status: "ready"; replayId: string; attempt: number; replay: ProcessedReplay }
  >({ status: "catalog" });
  const currentScreen = processedReplaysOpen
    ? processedReplay.status === "catalog"
      ? "processed-replays"
      : "processed-player"
    : state.status;
  const previousScreen = useRef(currentScreen);
  const uploadedViewerCache = useRef<UploadedViewerCache | undefined>(undefined);
  const requestSequence = useRef(0);
  const nextRequestId = useCallback((operation: string) => {
    requestSequence.current += 1;
    return `${operation}-${requestSequence.current}`;
  }, []);

  const applyLandingView = useCallback(
    (view: LandingView) => {
      dispatch({ type: "RESET" });
      if (view === "samples") {
        setProcessedReplaysOpen(false);
        setProcessedReplay({ status: "catalog" });
        dispatch({ type: "OPEN_SAMPLES" });
        return;
      }
      if (view === "showcase") {
        setProcessedReplaysOpen(true);
        setProcessedReplay({ status: "catalog" });
        return;
      }
      setProcessedReplaysOpen(false);
      setProcessedReplay({ status: "catalog" });
    },
    [],
  );

  useEffect(() => {
    if (processedReplay.status !== "loading") {
      return;
    }

    const controller = new AbortController();
    const { replayId, attempt } = processedReplay;
    let active = true;
    getProcessedReplay(replayId, controller.signal)
      .then((replay) => {
        if (active) {
          setProcessedReplay({ status: "ready", replayId, attempt, replay });
        }
      })
      .catch((error: unknown) => {
        if (active && !isAbortError(error)) {
          setProcessedReplay({
            status: "error",
            replayId,
            attempt,
            message: error instanceof Error ? error.message : "The processed replay could not be loaded.",
          });
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [processedReplay]);

  useEffect(() => {
    const syncFromLocation = () => {
      const historyView = landingHistoryViewFromState(window.history.state);
      if (historyView === "upload") {
        setProcessedReplaysOpen(false);
        setProcessedReplay({ status: "catalog" });
        dispatch({ type: "RETURN_TO_PLAYER_SELECTION" });
        return;
      }
      if (historyView === "upload-viewer") {
        const cached = uploadedViewerCache.current;
        if (cached) {
          dispatch({ type: "RESTORE_VIEWER", ...cached });
        }
        return;
      }
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
    prepareReplayWorkspace(state.manifest.replay_id, controller.signal)
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
      .then((result) =>
        dispatch({
          type: "COACHING_SUCCEEDED",
          requestId,
          result,
          visualizationRequestId: nextRequestId("visualization"),
        }),
      )
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
          dispatch({
            type: "RESULT_RECOVERED",
            requestId,
            result: recovered.value,
            visualizationRequestId: nextRequestId("visualization"),
          });
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
  }, [nextRequestId, state]);

  useEffect(() => {
    if (state.status !== "loading-visualization") {
      return;
    }

    const controller = new AbortController();
    const requestId = state.requestId;
    const replayId = state.manifest.replay_id;
    const deadline = Date.now() + VISUALIZATION_TIMEOUT_MS;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const poll = async () => {
      try {
        const response = await getReplayVisualization(replayId, controller.signal);
        if (cancelled) return;

        if (response.state === "failed") {
          dispatch({
            type: "VISUALIZATION_FAILED",
            requestId,
            error: {
              code: "visualization-failed",
              message: "The replay map could not be generated for this demo.",
              retryable: false,
            },
          });
          return;
        }

        if (response.state === "ready") {
          let replay: ProcessedReplay;
          try {
            replay = normalizeBackendReplay(response.value);
          } catch {
            dispatch({
              type: "VISUALIZATION_FAILED",
              requestId,
              error: {
                code: "invalid-response",
                message: "The replay map data was not in a supported format.",
                retryable: false,
              },
            });
            return;
          }
          if (
            replay.replay_id !== replayId ||
            replay.source !== state.result.source ||
            replay.map.name !== state.result.map_name
          ) {
            dispatch({
              type: "VISUALIZATION_FAILED",
              requestId,
              error: {
                code: "invalid-response",
                message: "The replay map did not match the completed analysis.",
                retryable: false,
              },
            });
            return;
          }
          uploadedViewerCache.current = {
            selectedPlayerId: state.selectedPlayer.player_id,
            result: state.result,
            replay,
          };
          dispatch({ type: "VISUALIZATION_LOADED", requestId, replay });
          return;
        }

        if (Date.now() >= deadline) {
          dispatch({
            type: "VISUALIZATION_FAILED",
            requestId,
            error: {
              code: "visualization-failed",
              message: "The replay map is taking longer than expected to become available.",
              retryable: true,
            },
          });
          return;
        }
        timer = setTimeout(poll, VISUALIZATION_POLL_INTERVAL_MS);
      } catch (error: unknown) {
        if (!isAbortError(error)) {
          dispatch({
            type: "VISUALIZATION_FAILED",
            requestId,
            error: flowError(
              error,
              "visualization-failed",
              "The replay map could not be loaded.",
            ),
          });
        }
      }
    };

    void poll();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer) clearTimeout(timer);
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
        : currentScreen === "processed-replays"
          ? "processed-replays-title"
          : currentScreen === "processed-player"
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
  const selectReplayFile = (file: File) => {
    window.history.pushState(
      withLandingHistoryMarker(window.history.state, "upload", true),
      "",
      landingViewHref("home", window.location.search),
    );
    dispatch({ type: "SELECT_REPLAY_FILE", file, requestId: nextRequestId("upload") });
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
  const returnToPlayerSelection = () => {
    if (landingHistoryViewFromState(window.history.state) === "upload-viewer") {
      window.history.back();
      return;
    }
    dispatch({ type: "RETURN_TO_PLAYER_SELECTION" });
  };

  if (state.status === "viewer") {
    return (
      <ReplayAnalysisScreen
        initialPlayerId={state.selectedPlayer.player_id}
        initialReplay={state.replay}
        initialAnalysis={state.result}
        uploaded
        onChoosePlayer={returnToPlayerSelection}
      />
    );
  }

  if (
    state.status === "running-coaching" ||
    state.status === "recovering-result" ||
    state.status === "loading-visualization"
  ) {
    return (
      <ReplayMapLoadingScreen
        manifest={state.manifest}
        player={state.selectedPlayer}
        phase={
          state.status === "running-coaching"
            ? "coaching"
            : state.status === "recovering-result"
              ? "recovery"
              : "visualization"
        }
        onReturnToPlayers={returnToPlayerSelection}
      />
    );
  }

  let content;
  if (processedReplaysOpen) {
    if (processedReplay.status === "catalog") {
      content = (
        <ProcessedReplaySelectorScreen
          replays={PROCESSED_REPLAYS}
          onBack={returnHome}
          onSelect={(replayId) =>
            setProcessedReplay({ status: "loading", replayId, attempt: 1 })
          }
        />
      );
    } else {
      const summary = processedReplayById(processedReplay.replayId);
      content = summary ? (
        <ProcessedReplayPlayerScreen
          status={processedReplay.status}
          summary={summary}
          replay={processedReplay.status === "ready" ? processedReplay.replay : undefined}
          message={processedReplay.status === "error" ? processedReplay.message : undefined}
          onBack={() => setProcessedReplay({ status: "catalog" })}
          onRetry={() =>
            setProcessedReplay({
              status: "loading",
              replayId: processedReplay.replayId,
              attempt: processedReplay.attempt + 1,
            })
          }
          onSelectPlayer={(player) =>
            router.push(
              `/analysis?replay=${encodeURIComponent(processedReplay.replayId)}&player=${encodeURIComponent(player.player_id)}`,
            )
          }
        />
      ) : null;
    }
  } else if (state.status === "choose") {
    content = (
      <LandingScreen
        onOpenSamples={() => openLandingView("samples")}
        onOpenShowcase={() => openLandingView("showcase")}
        onSelectReplay={selectReplayFile}
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
        onSelectPlayer={(playerId) => {
          uploadedViewerCache.current = undefined;
          window.history.pushState(
            withLandingHistoryMarker(window.history.state, "upload-viewer", true),
            "",
            landingViewHref("home", window.location.search),
          );
          dispatch({
            type: "SELECT_PLAYER",
            playerId,
            requestId: nextRequestId("coaching"),
          });
        }}
        onRetryCoaching={() =>
          dispatch({ type: "RETRY_COACHING", requestId: nextRequestId("coaching") })
        }
        onRetryRecovery={() =>
          dispatch({
            type: "RETRY_RESULT_RECOVERY",
            requestId: nextRequestId("recovery"),
          })
        }
        onRetryVisualization={() =>
          dispatch({
            type: "RETRY_VISUALIZATION",
            requestId: nextRequestId("visualization"),
          })
        }
        onReturnToPlayers={returnToPlayerSelection}
      />
    );
  }

  return (
    <main className="shell">
      <ProductHeader brandHref="/" />
      {content}
    </main>
  );
}
