import { describe, expect, it } from "vitest";
import backendResult from "../../../backend/tests/fixtures/analysis_api_result.json";
import {
  analysisFlowReducer,
  initialAnalysisFlowState,
  resultRecoveryDisposition,
  type AnalysisFlowState,
  type ReplayFlowError,
} from "@/domain/analysis-flow";
import {
  analysisJobSchema,
  analysisPlayersSchema,
  replayAnalysisResultSchema,
  replayManifestSchema,
} from "@/domain/replay";
import type { ProcessedReplay } from "@/domain/replay-viewer";

const file = new File(["demo"], "match.dem", { type: "application/octet-stream" });

const manifest = replayManifestSchema.parse({
  schema_version: "replay_manifest_v1",
  replay_id: "api-flow-test",
  source: "match.dem",
  map: { name: "de_mirage", tick_rate: 64 },
  players: [
    { player_id: "ct1", display_name: "CT One", sides: ["CT"] },
    { player_id: "t1", display_name: "T One", sides: ["T"] },
  ],
  rounds: [{ round_num: 1, start: 100, end: 300 }],
  visualization_status: "processing",
  coaching_status: "ready",
  visualization_unlocked: false,
});

const analysis = analysisJobSchema.parse({
  analysis_id: "analysis-1",
  status: "processing",
  players_available: false,
  result_available: false,
  selected_player_id: null,
  player_runs: {},
  logs_url: "/api/analysis/analysis-1/logs",
  events_url: "/api/analysis/analysis-1/events",
  result_url: "/api/analysis/analysis-1/result",
});

const players = analysisPlayersSchema.parse({
  analysis_id: "analysis-1",
  status: "ready",
  players: backendResult.players.map((player) => ({
    ...player,
    analysis_available: player.decision_ids.length > 0,
    analysis_status: "not_started",
  })),
}).players;

const result = replayAnalysisResultSchema.parse({
  ...backendResult,
  replay_outcome: {
    eventual_winner: "CT",
    round_score: { CT: 1, T: 0 },
    source: "round_score",
  },
});

const replay: ProcessedReplay = {
  schema_version: "replay_visualization_v1",
  replay_id: "api-flow-test",
  source: "match.dem",
  map: { name: "de_mirage", tick_rate: 64 },
  players: manifest.players,
  rounds: [{ round_num: 1, start: 100, end: 300 }],
  events: [],
  ticks: [
    {
      tick: 100,
      round_num: 1,
      player_id: "t1",
      display_name: "T One",
      side: "t",
      X: 0,
      Y: 0,
      Z: 0,
      health: 100,
      armor: 0,
      alive: true,
      has_defuser: false,
      place: null,
    },
  ],
};

const retryableError: ReplayFlowError = {
  code: "upload-failed",
  message: "The replay could not be uploaded.",
  retryable: true,
};

function advanceToPreparing(): AnalysisFlowState {
  const uploading = analysisFlowReducer(initialAnalysisFlowState, {
    type: "SELECT_REPLAY_FILE",
    file,
    requestId: "upload-1",
  });
  return analysisFlowReducer(uploading, {
    type: "UPLOAD_SUCCEEDED",
    requestId: "upload-1",
    manifest,
    prepareRequestId: "prepare-1",
  });
}

function advanceToWaiting(): AnalysisFlowState {
  return analysisFlowReducer(advanceToPreparing(), {
    type: "ANALYSIS_PREPARED",
    requestId: "prepare-1",
    analysis,
    playersRequestId: "players-1",
  });
}

function advanceToChoosing(): AnalysisFlowState {
  return analysisFlowReducer(advanceToWaiting(), {
    type: "PLAYERS_LOADED",
    requestId: "players-1",
    analysisId: "analysis-1",
    players,
  });
}

function advanceToCoaching(): AnalysisFlowState {
  return analysisFlowReducer(advanceToChoosing(), {
    type: "SELECT_PLAYER",
    playerId: "t1",
    requestId: "coach-1",
  });
}

describe("uploaded replay state machine", () => {
  it("never treats a merely ready analysis as permission to rerun ambiguous coaching", () => {
    expect(resultRecoveryDisposition("ready", false)).toBe("continue");
    expect(resultRecoveryDisposition("processing", false)).toBe("continue");
    expect(resultRecoveryDisposition("ready", true)).toBe("retry-result");
    expect(resultRecoveryDisposition("complete", false)).toBe("retry-result");
    expect(resultRecoveryDisposition("failed", false)).toBe("retry-coaching");
  });

  it("preserves the file and distinct stable IDs through the successful flow", () => {
    const preparing = advanceToPreparing();
    expect(preparing).toMatchObject({
      status: "preparing-analysis",
      file,
      manifest: { replay_id: "api-flow-test" },
      requestId: "prepare-1",
    });

    const choosing = advanceToChoosing();
    expect(choosing).toMatchObject({
      status: "choosing-player",
      manifest: { replay_id: "api-flow-test" },
      analysis: { analysis_id: "analysis-1" },
    });

    const coaching = advanceToCoaching();
    expect(coaching).toMatchObject({
      status: "running-coaching",
      selectedPlayer: { player_id: "t1", display_name: "T One" },
      requestId: "coach-1",
    });

    const completed = analysisFlowReducer(coaching, {
      type: "COACHING_SUCCEEDED",
      requestId: "coach-1",
      result,
      visualizationRequestId: "visualization-1",
    });
    expect(completed).toMatchObject({
      status: "loading-visualization",
      result: { replay_id: "api-flow-test" },
      selectedPlayer: { player_id: "t1" },
      requestId: "visualization-1",
    });

    const viewer = analysisFlowReducer(completed, {
      type: "VISUALIZATION_LOADED",
      requestId: "visualization-1",
      replay,
    });
    expect(viewer).toMatchObject({
      status: "viewer",
      replay: { replay_id: "api-flow-test" },
      selectedPlayer: { player_id: "t1" },
    });

    const playerSelection = analysisFlowReducer(viewer, {
      type: "RETURN_TO_PLAYER_SELECTION",
    });
    expect(playerSelection).toMatchObject({
      status: "choosing-player",
      analysis: { analysis_id: "analysis-1" },
    });

    const restoredViewer = analysisFlowReducer(playerSelection, {
      type: "RESTORE_VIEWER",
      selectedPlayerId: "t1",
      result,
      replay,
    });
    expect(restoredViewer).toMatchObject({
      status: "viewer",
      selectedPlayer: { player_id: "t1" },
    });

    const selectionAgain = analysisFlowReducer(restoredViewer, {
      type: "RETURN_TO_PLAYER_SELECTION",
    });

    const secondCoaching = analysisFlowReducer(selectionAgain, {
      type: "SELECT_PLAYER",
      playerId: "ct1",
      requestId: "coach-2",
    });
    expect(secondCoaching).toMatchObject({
      status: "running-coaching",
      selectedPlayer: { player_id: "ct1" },
      analysis: { analysis_id: "analysis-1" },
      requestId: "coach-2",
    });
  });

  it("ignores stale requests, mismatched analysis IDs, and completions after reset", () => {
    const uploading = analysisFlowReducer(initialAnalysisFlowState, {
      type: "SELECT_REPLAY_FILE",
      file,
      requestId: "upload-current",
    });
    expect(
      analysisFlowReducer(uploading, {
        type: "UPLOAD_SUCCEEDED",
        requestId: "upload-stale",
        manifest,
        prepareRequestId: "prepare-stale",
      }),
    ).toBe(uploading);

    const waiting = advanceToWaiting();
    expect(
      analysisFlowReducer(waiting, {
        type: "PLAYERS_LOADED",
        requestId: "players-1",
        analysisId: "another-analysis",
        players,
      }),
    ).toBe(waiting);

    const coaching = advanceToCoaching();
    expect(
      analysisFlowReducer(coaching, {
        type: "COACHING_SUCCEEDED",
        requestId: "coach-stale",
        result,
        visualizationRequestId: "visualization-stale",
      }),
    ).toBe(coaching);

    const reset = analysisFlowReducer(coaching, { type: "RESET" });
    expect(
      analysisFlowReducer(reset, {
        type: "COACHING_SUCCEEDED",
        requestId: "coach-1",
        result,
        visualizationRequestId: "visualization-1",
      }),
    ).toEqual(initialAnalysisFlowState);
  });

  it("supports scoped retry paths without discarding uploaded replay context", () => {
    const uploading = analysisFlowReducer(initialAnalysisFlowState, {
      type: "SELECT_REPLAY_FILE",
      file,
      requestId: "upload-1",
    });
    const uploadError = analysisFlowReducer(uploading, {
      type: "UPLOAD_FAILED",
      requestId: "upload-1",
      error: retryableError,
    });
    expect(
      analysisFlowReducer(uploadError, { type: "RETRY_UPLOAD", requestId: "upload-2" }),
    ).toMatchObject({ status: "uploading", file, requestId: "upload-2" });

    const preparationError = analysisFlowReducer(advanceToPreparing(), {
      type: "ANALYSIS_PREPARE_FAILED",
      requestId: "prepare-1",
      error: { ...retryableError, code: "prepare-failed" },
    });
    const retryPreparation = analysisFlowReducer(preparationError, {
      type: "RETRY_ANALYSIS_PREPARE",
      requestId: "prepare-2",
    });
    expect(retryPreparation).toMatchObject({
      status: "preparing-analysis",
      manifest: { replay_id: "api-flow-test" },
      requestId: "prepare-2",
    });
    expect(retryPreparation).not.toHaveProperty("analysis");

    const playerError = analysisFlowReducer(advanceToWaiting(), {
      type: "PLAYERS_FAILED",
      requestId: "players-1",
      error: { ...retryableError, code: "players-failed" },
    });
    const retryPlayers = analysisFlowReducer(playerError, {
      type: "RETRY_PLAYERS",
      requestId: "players-2",
    });
    expect(retryPlayers).toMatchObject({
      status: "waiting-for-players",
      analysis: { analysis_id: "analysis-1" },
      requestId: "players-2",
    });
    expect(retryPlayers).not.toHaveProperty("error");
  });

  it("rejects empty selectors and players without a coaching decision", () => {
    const empty = analysisFlowReducer(advanceToWaiting(), {
      type: "PLAYERS_LOADED",
      requestId: "players-1",
      analysisId: "analysis-1",
      players: [],
    });
    expect(empty).toMatchObject({
      status: "players-error",
      error: { code: "empty-player-list", retryable: false },
    });

    const choosing = advanceToChoosing();
    if (choosing.status !== "choosing-player") {
      throw new Error("test setup did not reach player selection");
    }
    const noDecisionPlayer = { ...choosing.players[0], decision_ids: [] };
    const withUnavailablePlayer: AnalysisFlowState = {
      ...choosing,
      players: [noDecisionPlayer, ...choosing.players.slice(1)],
    };
    expect(
      analysisFlowReducer(withUnavailablePlayer, {
        type: "SELECT_PLAYER",
        playerId: noDecisionPlayer.player_id,
        requestId: "coach-unavailable",
      }),
    ).toBe(withUnavailablePlayer);
  });

  it("recovers an ambiguous coaching request before permitting any rerun", () => {
    const coaching = advanceToCoaching();
    const recovering = analysisFlowReducer(coaching, {
      type: "COACHING_REQUEST_UNCERTAIN",
      requestId: "coach-1",
      recoveryRequestId: "recovery-1",
    });
    expect(recovering).toMatchObject({
      status: "recovering-result",
      requestId: "recovery-1",
      selectedPlayer: { player_id: "t1" },
    });
    expect(
      analysisFlowReducer(recovering, {
        type: "RETRY_COACHING",
        requestId: "duplicate-coach",
      }),
    ).toBe(recovering);
    const confirmedAbsent = analysisFlowReducer(recovering, {
      type: "RESULT_CONFIRMED_ABSENT",
      requestId: "recovery-1",
      error: {
        code: "coaching-failed",
        message: "No completed result was found.",
        retryable: true,
      },
    });
    expect(confirmedAbsent).toMatchObject({ status: "coaching-error" });
    expect(
      analysisFlowReducer(confirmedAbsent, {
        type: "RETRY_COACHING",
        requestId: "coach-after-confirmation",
      }),
    ).toMatchObject({
      status: "running-coaching",
      requestId: "coach-after-confirmation",
    });

    const recoveryError = analysisFlowReducer(recovering, {
      type: "RESULT_RECOVERY_FAILED",
      requestId: "recovery-1",
      error: {
        code: "result-recovery-failed",
        message: "The completed result could not be checked.",
        retryable: true,
      },
    });
    const retryRecovery = analysisFlowReducer(recoveryError, {
      type: "RETRY_RESULT_RECOVERY",
      requestId: "recovery-2",
    });
    expect(retryRecovery).toMatchObject({
      status: "recovering-result",
      requestId: "recovery-2",
    });
    expect(retryRecovery).not.toHaveProperty("error");

    const completed = analysisFlowReducer(retryRecovery, {
      type: "RESULT_RECOVERED",
      requestId: "recovery-2",
      result,
      visualizationRequestId: "visualization-recovered",
    });
    expect(completed).toMatchObject({
      status: "loading-visualization",
      requestId: "visualization-recovered",
      result,
    });
  });

  it("allows an explicit retry after a confirmed coaching failure", () => {
    const failed = analysisFlowReducer(advanceToCoaching(), {
      type: "COACHING_FAILED",
      requestId: "coach-1",
      error: {
        code: "coaching-failed",
        message: "Coaching could not be completed.",
        retryable: true,
      },
    });
    const retry = analysisFlowReducer(failed, {
      type: "RETRY_COACHING",
      requestId: "coach-2",
    });
    expect(retry).toMatchObject({ status: "running-coaching", requestId: "coach-2" });
    expect(retry).not.toHaveProperty("error");
  });

  it("does not accept a validly shaped result owned by another replay", () => {
    const wrongReplayResult = replayAnalysisResultSchema.parse({
      ...result,
      replay_id: "another-replay",
    });
    const completed = analysisFlowReducer(advanceToCoaching(), {
      type: "COACHING_SUCCEEDED",
      requestId: "coach-1",
      result: wrongReplayResult,
      visualizationRequestId: "visualization-1",
    });
    expect(completed).toMatchObject({
      status: "coaching-error",
      error: { code: "invalid-response", retryable: false },
    });
  });
});
