import type {
  SamplePreparation,
  SampleReplayPreparation,
  SampleSummary,
} from "./samples";
import type {
  AnalysisJob,
  AnalysisPlayer,
  ReplayAnalysisResult,
  ReplayManifest,
} from "./replay";
import type { ProcessedReplay } from "./replay-viewer";

export type ReplayFlowErrorCode =
  | "invalid-file"
  | "upload-failed"
  | "prepare-failed"
  | "players-failed"
  | "empty-player-list"
  | "coaching-failed"
  | "result-recovery-failed"
  | "visualization-failed"
  | "invalid-response";

export type ReplayFlowError = {
  code: ReplayFlowErrorCode;
  message: string;
  retryable: boolean;
};

type ResultRecoveryDisposition = "continue" | "retry-result" | "retry-coaching";

export function resultRecoveryDisposition(
  status: AnalysisJob["status"],
  timedOut: boolean,
): ResultRecoveryDisposition {
  if (status === "failed") {
    return "retry-coaching";
  }
  if (status === "complete" || timedOut) {
    return "retry-result";
  }
  return "continue";
}

type UploadedReplayContext = {
  file?: File;
  sourceName?: string;
  sampleId?: string;
  manifest: ReplayManifest;
};

type PreparedReplayContext = UploadedReplayContext & {
  analysis: AnalysisJob;
};

type PlayerSelectionContext = PreparedReplayContext & {
  players: AnalysisPlayer[];
};

type SelectedPlayerContext = PlayerSelectionContext & {
  selectedPlayer: AnalysisPlayer;
};

type CompletedCoachingContext = SelectedPlayerContext & {
  result: ReplayAnalysisResult;
};

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
  | { status: "sample-selection-error"; samples: SampleSummary[]; sampleId: string }
  | { status: "uploading"; file: File; requestId: string }
  | { status: "upload-error"; file: File; error: ReplayFlowError }
  | ({ status: "preparing-analysis"; requestId: string } & UploadedReplayContext)
  | ({ status: "analysis-prepare-error"; error: ReplayFlowError } & UploadedReplayContext)
  | ({ status: "waiting-for-players"; requestId: string } & PreparedReplayContext)
  | ({ status: "players-error"; error: ReplayFlowError } & PreparedReplayContext)
  | ({ status: "choosing-player" } & PlayerSelectionContext)
  | ({ status: "running-coaching"; requestId: string } & SelectedPlayerContext)
  | ({ status: "recovering-result"; requestId: string } & SelectedPlayerContext)
  | ({ status: "result-recovery-error"; error: ReplayFlowError } & SelectedPlayerContext)
  | ({ status: "coaching-error"; error: ReplayFlowError } & SelectedPlayerContext)
  | ({ status: "loading-visualization"; requestId: string } & CompletedCoachingContext)
  | ({ status: "visualization-error"; error: ReplayFlowError } & CompletedCoachingContext)
  | ({ status: "viewer"; replay: ProcessedReplay } & CompletedCoachingContext);

export type SampleAnalysisFlowState = Extract<
  AnalysisFlowState,
  {
    status:
      | "loading-samples"
      | "samples-error"
      | "samples-ready"
      | "selecting-sample"
      | "sample-selected"
      | "sample-selection-error";
  }
>;

export type ReplayAnalysisFlowState = Exclude<
  AnalysisFlowState,
  { status: "choose" } | SampleAnalysisFlowState
>;

export type AnalysisFlowAction =
  | { type: "OPEN_SAMPLES" }
  | { type: "SAMPLES_LOADED"; samples: SampleSummary[] }
  | { type: "SAMPLES_FAILED" }
  | { type: "SELECT_SAMPLE"; sampleId: string }
  | { type: "SAMPLE_SELECTED"; sampleId: string; preparation: SamplePreparation }
  | {
      type: "SAMPLE_REPLAY_READY";
      sampleId: string;
      sourceName: string;
      preparation: SampleReplayPreparation;
      playersRequestId: string;
    }
  | { type: "SAMPLE_SELECTION_FAILED"; sampleId: string }
  | { type: "SELECT_REPLAY_FILE"; file: File; requestId: string }
  | {
      type: "UPLOAD_SUCCEEDED";
      requestId: string;
      manifest: ReplayManifest;
      prepareRequestId: string;
    }
  | { type: "UPLOAD_FAILED"; requestId: string; error: ReplayFlowError }
  | { type: "RETRY_UPLOAD"; requestId: string }
  | {
      type: "ANALYSIS_PREPARED";
      requestId: string;
      analysis: AnalysisJob;
      playersRequestId: string;
    }
  | { type: "ANALYSIS_PREPARE_FAILED"; requestId: string; error: ReplayFlowError }
  | { type: "RETRY_ANALYSIS_PREPARE"; requestId: string }
  | { type: "PLAYERS_LOADED"; requestId: string; analysisId: string; players: AnalysisPlayer[] }
  | { type: "PLAYERS_FAILED"; requestId: string; error: ReplayFlowError }
  | { type: "RETRY_PLAYERS"; requestId: string }
  | { type: "SELECT_PLAYER"; playerId: string; requestId: string }
  | {
      type: "COACHING_SUCCEEDED";
      requestId: string;
      result: ReplayAnalysisResult;
      visualizationRequestId: string;
    }
  | {
      type: "COACHING_REQUEST_UNCERTAIN";
      requestId: string;
      recoveryRequestId: string;
    }
  | { type: "COACHING_FAILED"; requestId: string; error: ReplayFlowError }
  | {
      type: "RESULT_RECOVERED";
      requestId: string;
      result: ReplayAnalysisResult;
      visualizationRequestId: string;
    }
  | { type: "RESULT_CONFIRMED_ABSENT"; requestId: string; error: ReplayFlowError }
  | { type: "RESULT_RECOVERY_FAILED"; requestId: string; error: ReplayFlowError }
  | { type: "RETRY_RESULT_RECOVERY"; requestId: string }
  | { type: "RETRY_COACHING"; requestId: string }
  | { type: "VISUALIZATION_LOADED"; requestId: string; replay: ProcessedReplay }
  | { type: "VISUALIZATION_FAILED"; requestId: string; error: ReplayFlowError }
  | { type: "RETRY_VISUALIZATION"; requestId: string }
  | { type: "RETURN_TO_PLAYER_SELECTION" }
  | {
      type: "RESTORE_VIEWER";
      selectedPlayerId: string;
      result: ReplayAnalysisResult;
      replay: ProcessedReplay;
    }
  | { type: "RESET" };

export const initialAnalysisFlowState: AnalysisFlowState = { status: "choose" };

const emptyPlayerListError: ReplayFlowError = {
  code: "empty-player-list",
  message: "No players are available for coaching in this replay.",
  retryable: false,
};

const mismatchedResultError: ReplayFlowError = {
  code: "invalid-response",
  message: "The coaching result did not match the selected replay and player.",
  retryable: false,
};

function resultMatchesSelection(
  result: ReplayAnalysisResult,
  context: SelectedPlayerContext,
): boolean {
  return (
    result.replay_id === context.manifest.replay_id &&
    result.selected_decision.player_id === context.selectedPlayer.player_id &&
    result.coach_analysis.player_id === context.selectedPlayer.player_id
  );
}

function uploadedReplayContext(state: UploadedReplayContext): UploadedReplayContext {
  return {
    ...(state.file ? { file: state.file } : {}),
    ...(state.sourceName ? { sourceName: state.sourceName } : {}),
    ...(state.sampleId ? { sampleId: state.sampleId } : {}),
    manifest: state.manifest,
  };
}

function preparedReplayContext(state: PreparedReplayContext): PreparedReplayContext {
  return {
    ...uploadedReplayContext(state),
    analysis: state.analysis,
    ...(state.sampleId ? { sampleId: state.sampleId } : {}),
  };
}

function playerSelectionContext(state: PlayerSelectionContext): PlayerSelectionContext {
  return { ...preparedReplayContext(state), players: state.players };
}

function selectedPlayerContext(state: SelectedPlayerContext): SelectedPlayerContext {
  return { ...playerSelectionContext(state), selectedPlayer: state.selectedPlayer };
}

function completedCoachingContext(state: CompletedCoachingContext): CompletedCoachingContext {
  return { ...selectedPlayerContext(state), result: state.result };
}

function finishCoaching(
  state: Extract<AnalysisFlowState, { status: "running-coaching" | "recovering-result" }>,
  result: ReplayAnalysisResult,
  visualizationRequestId: string,
): AnalysisFlowState {
  const context = selectedPlayerContext(state);
  return resultMatchesSelection(result, state)
    ? {
        ...context,
        status: "loading-visualization",
        result,
        requestId: visualizationRequestId,
      }
    : {
        ...context,
        status: "coaching-error",
        error: mismatchedResultError,
      };
}

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
    case "SAMPLE_REPLAY_READY":
      return state.status === "selecting-sample" && state.sampleId === action.sampleId
        ? {
            status: "waiting-for-players",
            sourceName: action.sourceName,
            manifest: action.preparation.manifest,
            analysis: action.preparation.analysis,
            sampleId: action.sampleId,
            requestId: action.playersRequestId,
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
    case "SELECT_REPLAY_FILE":
      return state.status === "choose"
        ? { status: "uploading", file: action.file, requestId: action.requestId }
        : state;
    case "UPLOAD_SUCCEEDED":
      return state.status === "uploading" && state.requestId === action.requestId
        ? {
            status: "preparing-analysis",
            file: state.file,
            sourceName: state.file.name,
            manifest: action.manifest,
            requestId: action.prepareRequestId,
          }
        : state;
    case "UPLOAD_FAILED":
      return state.status === "uploading" && state.requestId === action.requestId
        ? { status: "upload-error", file: state.file, error: action.error }
        : state;
    case "RETRY_UPLOAD":
      return state.status === "upload-error" && state.error.retryable
        ? { status: "uploading", file: state.file, requestId: action.requestId }
        : state;
    case "ANALYSIS_PREPARED":
      return state.status === "preparing-analysis" && state.requestId === action.requestId
        ? {
            status: "waiting-for-players",
            file: state.file,
            sourceName: state.sourceName ?? state.file?.name,
            manifest: state.manifest,
            analysis: action.analysis,
            requestId: action.playersRequestId,
          }
        : state;
    case "ANALYSIS_PREPARE_FAILED":
      return state.status === "preparing-analysis" && state.requestId === action.requestId
        ? {
            status: "analysis-prepare-error",
            file: state.file,
            manifest: state.manifest,
            error: action.error,
          }
        : state;
    case "RETRY_ANALYSIS_PREPARE":
      return (state.status === "analysis-prepare-error" || state.status === "players-error") &&
        state.error.retryable
        ? {
            ...uploadedReplayContext(state),
            status: "preparing-analysis",
            requestId: action.requestId,
          }
        : state;
    case "PLAYERS_LOADED":
      if (
        state.status !== "waiting-for-players" ||
        state.requestId !== action.requestId ||
        state.analysis.analysis_id !== action.analysisId
      ) {
        return state;
      }
      if (action.players.length === 0) {
        const context = preparedReplayContext(state);
        return { ...context, status: "players-error", error: emptyPlayerListError };
      }
      {
        const context = preparedReplayContext(state);
        return { ...context, status: "choosing-player", players: action.players };
      }
    case "PLAYERS_FAILED":
      if (state.status !== "waiting-for-players" || state.requestId !== action.requestId) {
        return state;
      }
      {
        const context = preparedReplayContext(state);
        return { ...context, status: "players-error", error: action.error };
      }
    case "RETRY_PLAYERS":
      return state.status === "players-error" && state.error.retryable
        ? {
            ...preparedReplayContext(state),
            status: "waiting-for-players",
            requestId: action.requestId,
          }
        : state;
    case "SELECT_PLAYER":
      if (state.status !== "choosing-player") {
        return state;
      }
      {
        const selectedPlayer = state.players.find(
          ({ player_id }) => player_id === action.playerId,
        );
        return selectedPlayer && selectedPlayer.decision_ids.length > 0
          ? {
              ...state,
              status: "running-coaching",
              selectedPlayer,
              requestId: action.requestId,
            }
          : state;
      }
    case "COACHING_SUCCEEDED":
      return state.status === "running-coaching" && state.requestId === action.requestId
        ? finishCoaching(state, action.result, action.visualizationRequestId)
        : state;
    case "COACHING_REQUEST_UNCERTAIN":
      if (state.status !== "running-coaching" || state.requestId !== action.requestId) {
        return state;
      }
      {
        const context = selectedPlayerContext(state);
        return {
          ...context,
          status: "recovering-result",
          requestId: action.recoveryRequestId,
        };
      }
    case "COACHING_FAILED":
      if (state.status !== "running-coaching" || state.requestId !== action.requestId) {
        return state;
      }
      {
        const context = selectedPlayerContext(state);
        return {
          ...context,
          status: "coaching-error",
          error: action.error,
        };
      }
    case "RESULT_RECOVERED":
      return state.status === "recovering-result" && state.requestId === action.requestId
        ? finishCoaching(state, action.result, action.visualizationRequestId)
        : state;
    case "RESULT_CONFIRMED_ABSENT":
      if (state.status !== "recovering-result" || state.requestId !== action.requestId) {
        return state;
      }
      return {
        ...selectedPlayerContext(state),
        status: "coaching-error",
        error: action.error,
      };
    case "RESULT_RECOVERY_FAILED":
      if (state.status !== "recovering-result" || state.requestId !== action.requestId) {
        return state;
      }
      {
        const context = selectedPlayerContext(state);
        return { ...context, status: "result-recovery-error", error: action.error };
      }
    case "RETRY_RESULT_RECOVERY":
      return state.status === "result-recovery-error" && state.error.retryable
        ? {
            ...selectedPlayerContext(state),
            status: "recovering-result",
            requestId: action.requestId,
          }
        : state;
    case "RETRY_COACHING":
      return state.status === "coaching-error" && state.error.retryable
        ? {
            ...selectedPlayerContext(state),
            status: "running-coaching",
            requestId: action.requestId,
          }
        : state;
    case "VISUALIZATION_LOADED":
      return state.status === "loading-visualization" && state.requestId === action.requestId
        ? {
            ...completedCoachingContext(state),
            status: "viewer",
            replay: action.replay,
          }
        : state;
    case "VISUALIZATION_FAILED":
      return state.status === "loading-visualization" && state.requestId === action.requestId
        ? {
            ...completedCoachingContext(state),
            status: "visualization-error",
            error: action.error,
          }
        : state;
    case "RETRY_VISUALIZATION":
      return state.status === "visualization-error" && state.error.retryable
        ? {
            ...completedCoachingContext(state),
            status: "loading-visualization",
            requestId: action.requestId,
          }
        : state;
    case "RETURN_TO_PLAYER_SELECTION":
      if (
        state.status !== "running-coaching" &&
        state.status !== "recovering-result" &&
        state.status !== "result-recovery-error" &&
        state.status !== "coaching-error" &&
        state.status !== "loading-visualization" &&
        state.status !== "visualization-error" &&
        state.status !== "viewer"
      ) {
        return state;
      }
      return {
        ...playerSelectionContext(state),
        status: "choosing-player",
      };
    case "RESTORE_VIEWER":
      if (state.status !== "choosing-player") {
        return state;
      }
      {
        const selectedPlayer = state.players.find(
          ({ player_id }) => player_id === action.selectedPlayerId,
        );
        if (!selectedPlayer) {
          return state;
        }
        const context = { ...state, selectedPlayer };
        return resultMatchesSelection(action.result, context) &&
          action.replay.replay_id === state.manifest.replay_id
          ? {
              ...context,
              status: "viewer",
              result: action.result,
              replay: action.replay,
            }
          : state;
      }
    case "RESET":
      return initialAnalysisFlowState;
  }
}
