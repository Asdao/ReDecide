import { describe, expect, it } from "vitest";
import {
  analysisJobSchema,
  analysisPlayersSchema,
  replayAnalysisResultSchema,
  replayManifestSchema,
} from "@/domain/replay";

const manifest = {
  schema_version: "replay_manifest_v1",
  replay_id: "replay-1",
  source: "match.dem",
  map: { name: "de_mirage", tick_rate: 64 },
  players: [
    { player_id: "p1", display_name: "Player One", sides: ["CT"] },
    { player_id: "p2", display_name: "Player Two", sides: ["T"] },
  ],
  rounds: [{ round_num: 1, start: 10, end: 100 }],
  visualization_status: "processing",
  coaching_status: "ready",
  visualization_unlocked: false,
};

const player = {
  player_id: "p1",
  display_name: "Player One",
  side_by_round: { "1": "ct" },
  rounds: [1],
  event_ids: ["event-1"],
  key_event_ids: ["event-1"],
  decision_ids: ["decision-1"],
};

const selectablePlayer = {
  ...player,
  analysis_available: true,
  analysis_status: "not_started",
};

const candidate = {
  action_close_tick: 30,
  contact_tick: 20,
  decision_id: "decision-1",
  decision_open_tick: 20,
  display_name: "Player One",
  event_category: "damage",
  evidence: ["displacement_below_threshold"],
  observed_action: "hold",
  observed_action_confidence: 0.8,
  opponent_id: "p2",
  player_id: "p1",
  player_name: "Player One",
  role: "attacker",
  round_number: 1,
  side: "ct",
};

const event = {
  event_id: "event-1",
  event_type: "damage",
  is_coaching_anchor: true,
  is_key_event: true,
  key_event_type: "first_damage_contact",
  participant_ids: ["p1", "p2"],
  round_number: 1,
  tick: 20,
};

const result = {
  schema_version: "replay_pipeline_v1",
  report_type: "replay_pipeline_analysis",
  source: "match.dem",
  replay_id: "replay-1",
  map_name: "de_mirage",
  players: [player],
  events: [event],
  key_events: [event],
  filter_contract: {
    player_event_field: "participant_ids",
    player_reference_fields: ["event_ids", "key_event_ids", "decision_ids"],
    global_unfiltered_fields: ["win_estimator"],
  },
  decision_candidates: [candidate],
  selected_decision: candidate,
  coach_analysis: {
    decision_id: "decision-1",
    player_id: "p1",
    player_name: "Player One",
    source: "pi",
    what_could_be_done_better: "Reset before taking the next fight.",
  },
  win_estimator: {
    filtered_by_player: false,
    model_available: true,
    model_type: "test",
    scope: "global_team_probability",
    timeline: [],
  },
  summary: {
    player_count: 1,
    event_count: 1,
    key_event_count: 1,
    decision_candidate_count: 1,
    anchor: "first_damage_contact",
    anchor_fallback: false,
    analysis_available: true,
    outcome_blind: true,
  },
  replay_outcome: {
    eventual_winner: "CT",
    round_score: { CT: 1, T: 0 },
    source: "round_score",
  },
};

describe("uploaded replay contracts", () => {
  it("accepts the documented manifest and rejects duplicate players", () => {
    expect(replayManifestSchema.parse(manifest).replay_id).toBe("replay-1");
    expect(() =>
      replayManifestSchema.parse({
        ...manifest,
        players: [...manifest.players, manifest.players[0]],
      }),
    ).toThrow("replay manifest player_id values must be unique");
  });

  it("rejects invalid round boundaries and extra manifest data", () => {
    expect(() =>
      replayManifestSchema.parse({
        ...manifest,
        rounds: [{ round_num: 1, start: 100, end: 10 }],
      }),
    ).toThrow("replay round end must be at or after its start");
    expect(() => replayManifestSchema.parse({ ...manifest, server_path: "private" })).toThrow();
  });

  it("keeps visualization failure and coaching unlock states internally consistent", () => {
    expect(() =>
      replayManifestSchema.parse({
        ...manifest,
        visualization_status: "failed",
      }),
    ).toThrow("failed visualization status requires a safe error message");
    expect(() =>
      replayManifestSchema.parse({
        ...manifest,
        visualization_unlocked: true,
      }),
    ).toThrow("visualization unlock must match coaching completion");
    expect(
      replayManifestSchema.parse({
        ...manifest,
        visualization_status: "failed",
        visualization_error: "visualization JSON generation failed",
      }).visualization_status,
    ).toBe("failed");
  });

  it("requires unique stable IDs in the authoritative player selector", () => {
    expect(() =>
      analysisPlayersSchema.parse({
        analysis_id: "analysis-1",
        status: "ready",
        players: [selectablePlayer, selectablePlayer],
      }),
    ).toThrow("analysis player_id values must be unique");
  });

  it("accepts backend per-player run metadata and the coaching status", () => {
    expect(
      analysisJobSchema.parse({
        analysis_id: "analysis-1",
        status: "coaching",
        players_available: true,
        result_available: false,
        selected_player_id: "p1",
        player_runs: {
          p1: {
            status: "running",
            result_available: false,
            run_id: "run-1",
          },
        },
        logs_url: "/api/analysis/analysis-1/logs",
        events_url: "/api/analysis/analysis-1/events",
        result_url: "/api/analysis/analysis-1/result",
      }).player_runs.p1.status,
    ).toBe("running");

    expect(
      analysisPlayersSchema.parse({
        analysis_id: "analysis-1",
        status: "ready",
        players: [selectablePlayer],
      }).players[0],
    ).toMatchObject({
      player_id: "p1",
      analysis_available: true,
      analysis_status: "not_started",
    });
  });

  it("accepts a consistent result and rejects mismatched coaching ownership", () => {
    expect(replayAnalysisResultSchema.parse(result).coach_analysis.player_id).toBe("p1");
    expect(() =>
      replayAnalysisResultSchema.parse({
        ...result,
        coach_analysis: { ...result.coach_analysis, player_id: "another-player" },
      }),
    ).toThrow("coaching analysis must match the selected decision and player");
  });

  it("requires the selected decision to be one of the returned candidates", () => {
    expect(() =>
      replayAnalysisResultSchema.parse({
        ...result,
        decision_candidates: [],
      }),
    ).toThrow("selected decision must match a returned decision candidate");
  });
});
