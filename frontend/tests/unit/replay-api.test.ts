import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ReplayApiError,
  getAnalysisPlayers,
  getAnalysisResult,
  getReplayVisualization,
  prepareReplayAnalysis,
  prepareReplayWorkspace,
  runReplayCoaching,
  submitPlayerIntent,
  uploadReplay,
} from "@/adapters/replay-api";

const manifest = {
  schema_version: "replay_manifest_v1",
  replay_id: "replay-1",
  source: "match.dem",
  map: { name: "de_mirage", tick_rate: 64 },
  players: [{ player_id: "p1", display_name: "Player One", sides: ["CT"] }],
  rounds: [{ round_num: 1, start: 10, end: 100 }],
  visualization_status: "processing",
  coaching_status: "ready",
  visualization_unlocked: false,
};

const job = {
  analysis_id: "analysis-1",
  status: "processing",
  players_available: false,
  result_available: false,
  logs_url: "/api/analysis/analysis-1/logs",
  events_url: "/api/analysis/analysis-1/events",
  result_url: "/api/analysis/analysis-1/result",
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
    timeline: [
      { ct_probability: 0.6, t_probability: 0.4, round_number: 1, tick: 10, uncertainty: 0.2 },
    ],
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

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("replay API adapter", () => {
  it("uploads one .dem in the documented multipart field and validates the manifest", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(manifest, 202));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["demo"], "match.dem", { type: "application/octet-stream" });

    await expect(uploadReplay(file)).resolves.toEqual(manifest);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/replay/upload");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("rejects a non-.dem file before sending a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(uploadReplay(new File(["x"], "match.zip"))).rejects.toMatchObject({
      kind: "invalid-file",
      operation: "upload",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("prepares an analysis using only the stable replay_id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(job, 202));
    vi.stubGlobal("fetch", fetchMock);

    await expect(prepareReplayAnalysis("replay-1")).resolves.toEqual(job);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ replay_id: "replay-1" });
  });

  it("starts replay JSON retrieval alongside analysis preparation", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(job, 202))
      .mockResolvedValueOnce(
        jsonResponse({ status: "locked_until_coaching_complete" }, 403),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(prepareReplayWorkspace("replay-1")).resolves.toEqual(job);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://127.0.0.1:8000/api/analysis/prepare",
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "http://127.0.0.1:8000/api/replay/replay-1/json",
    );
  });

  it("represents a 202 player response as processing without fabricating players", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "not ready" }, 202)));

    await expect(getAnalysisPlayers("analysis-1")).resolves.toEqual({ state: "processing" });
  });

  it("validates ready players and submits the stable player_id for coaching", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ analysis_id: "analysis-1", status: "ready", players: [player] }),
      )
      .mockResolvedValueOnce(jsonResponse(result));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAnalysisPlayers("analysis-1")).resolves.toEqual({
      state: "ready",
      value: { analysis_id: "analysis-1", status: "ready", players: [player] },
    });
    await expect(runReplayCoaching("analysis-1", "p1")).resolves.toEqual(result);
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ player_id: "p1" });
  });

  it("uses GET result as a non-running recovery path", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "not ready" }, 202))
      .mockResolvedValueOnce(jsonResponse(result));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAnalysisResult("analysis-1")).resolves.toEqual({ state: "processing" });
    await expect(getAnalysisResult("analysis-1")).resolves.toEqual({
      state: "ready",
      value: result,
    });
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("GET");
  });

  it("keeps visualization processing, locked, failed, and ready states distinct", async () => {
    const visualization = {
      schema_version: "replay_visualization_v1",
      replay_id: "replay-1",
      source: "match.dem",
      map: { name: "de_mirage", tick_rate: 64 },
      players: manifest.players,
      rounds: [{ round_num: 1 }],
      events: [{ event: "damage", tick: 20 }],
      ticks: [{ tick: 20, player_id: "p1", X: 10, Y: 20 }],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: "processing" }, 202))
      .mockResolvedValueOnce(jsonResponse({ status: "locked_until_coaching_complete" }, 403))
      .mockResolvedValueOnce(jsonResponse({ detail: "failed" }, 422))
      .mockResolvedValueOnce(jsonResponse(visualization));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getReplayVisualization("replay-1")).resolves.toEqual({ state: "processing" });
    await expect(getReplayVisualization("replay-1")).resolves.toEqual({ state: "locked" });
    await expect(getReplayVisualization("replay-1")).resolves.toEqual({ state: "failed" });
    await expect(getReplayVisualization("replay-1")).resolves.toEqual({
      state: "ready",
      value: visualization,
    });
  });

  it("converts malformed success data and safe HTTP failures into typed errors", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ...manifest, replay_id: "" }, 202))
      .mockResolvedValueOnce(jsonResponse({ detail: "private parser details" }, 422));
    vi.stubGlobal("fetch", fetchMock);

    await expect(uploadReplay(new File(["x"], "first.dem"))).rejects.toMatchObject({
      kind: "invalid-response",
      operation: "upload",
    });
    await expect(uploadReplay(new File(["x"], "second.dem"))).rejects.toEqual(
      expect.objectContaining<Partial<ReplayApiError>>({
        message: "The selected replay could not be parsed.",
        kind: "rejected",
        status: 422,
      }),
    );
  });

  it("rejects non-JSON and unreadable JSON responses without exposing their bodies", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response("<html>proxy failure</html>", {
          status: 502,
          headers: { "Content-Type": "text/html" },
        }),
      )
      .mockResolvedValueOnce(
        new Response("not-json", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(prepareReplayAnalysis("replay-1")).rejects.toMatchObject({
      kind: "non-json",
      message: "The backend returned an unexpected response.",
    });
    await expect(prepareReplayAnalysis("replay-1")).rejects.toMatchObject({
      kind: "malformed-json",
      message: "The backend returned unreadable data.",
    });
  });

  it("keeps unknown IDs and confirmed coaching failures distinct", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "private missing ID" }, 404))
      .mockResolvedValueOnce(jsonResponse({ detail: "private provider error" }, 503));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAnalysisPlayers("missing")).rejects.toMatchObject({
      kind: "not-found",
      status: 404,
    });
    await expect(runReplayCoaching("analysis-1", "p1")).rejects.toMatchObject({
      kind: "server",
      status: 503,
      message: "The backend could not complete this request.",
    });
  });

  it("preserves AbortError while normalizing other network failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockRejectedValueOnce(new DOMException("aborted", "AbortError"))
        .mockRejectedValueOnce(new TypeError("connection refused")),
    );

    await expect(prepareReplayAnalysis("replay-1")).rejects.toMatchObject({ name: "AbortError" });
    await expect(prepareReplayAnalysis("replay-1")).rejects.toMatchObject({
      kind: "network",
      operation: "prepare",
    });
  });

  it("submits player action intent and receives contextual response", async () => {
    const intentResponse = {
      analysis_id: "analysis-1",
      player_id: "p1",
      decision_id: "decision-1",
      user_intent: "I expected my teammate to swing with me",
      intent_feasibility: "Moderate Risk",
      coordination_gap: "No audio or flash confirmation before tick 2500",
      recommended_cs2_adjustment: "Wait for utility setup or callout",
      in_depth_coaching: "Detailed CS2 tactical breakdown",
      knowledge_cutoff_tick: 2500,
      facts_referenced: ["displacement_below_threshold"],
    };

    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => intentResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await submitPlayerIntent(
      "analysis-1",
      "p1",
      "decision-1",
      "I expected my teammate to swing with me",
    );
    expect(result).toEqual(intentResponse);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/analysis/analysis-1/intent",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          analysis_id: "analysis-1",
          player_id: "p1",
          decision_id: "decision-1",
          intent_text: "I expected my teammate to swing with me",
        }),
      }),
    );
  });
});
