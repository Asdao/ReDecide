import { afterEach, describe, expect, it, vi } from "vitest";

const blobUploadMock = vi.hoisted(() => vi.fn());

vi.mock("@vercel/blob/client", () => ({ uploadPresigned: blobUploadMock }));

import {
  ReplayApiError,
  getAnalysisPlayers,
  getAnalysisResult,
  getReplayVisualization,
  prepareReplayAnalysis,
  prepareReplayWorkspace,
  runReplayCoaching,
  subscribeToAnalysisProgress,
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
  selected_player_id: null,
  player_runs: {},
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
  blobUploadMock.mockReset();
});

describe("replay API adapter", () => {
  it("validates and forwards SSE analysis progress", () => {
    class FakeEventSource {
      static instance: FakeEventSource | undefined;
      readonly listeners = new Map<string, EventListener>();
      readonly close = vi.fn();
      onerror: ((event: Event) => void) | null = null;

      constructor(readonly url: string) {
        FakeEventSource.instance = this;
      }

      addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
        if (typeof listener === "function") {
          this.listeners.set(type, listener);
        }
      }

      emit(type: string, data: unknown) {
        this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(data) }));
      }
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    const onProgress = vi.fn();
    const unsubscribe = subscribeToAnalysisProgress(job.events_url, { onProgress });
    const source = FakeEventSource.instance;

    expect(source?.url).toBe("/api/analysis/analysis-1/events");
    source?.emit("log", {
      analysis_id: "analysis-1",
      schema_version: "pipeline_progress_v1",
      stage: "calling_pi",
      progress: 85,
      message: "Generating coaching analysis.",
      done: false,
    });
    source?.emit("log", { analysis_id: "analysis-1", stage: "invalid" });
    expect(onProgress).toHaveBeenCalledTimes(1);
    expect(onProgress).toHaveBeenCalledWith(expect.objectContaining({ stage: "calling_pi", progress: 85 }));

    source?.emit("complete", {
      analysis_id: "analysis-1",
      stage: "complete",
      progress: 100,
      message: "Analysis complete.",
    });
    source?.onerror?.(new Event("error"));
    expect(source?.close).toHaveBeenCalledTimes(1);
    unsubscribe();
    expect(source?.close).toHaveBeenCalledTimes(2);
  });

  it("uploads one .dem in the documented multipart field and validates the manifest", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(manifest, 202));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["demo"], "match.dem", { type: "application/octet-stream" });

    await expect(uploadReplay(file)).resolves.toEqual(manifest);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/replay/upload");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("uploads through public Vercel Blob before importing the URL", async () => {
    const readyManifest = { ...manifest, visualization_status: "ready" };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(readyManifest, 202));
    vi.stubGlobal("fetch", fetchMock);
    blobUploadMock.mockResolvedValue({
      url: "https://store.public.blob.vercel-storage.com/uploads/match-123.dem",
    });
    const file = new File(["demo"], "match.dem", { type: "application/octet-stream" });
    const controller = new AbortController();

    await expect(uploadReplay(file, controller.signal, "blob")).resolves.toEqual(
      readyManifest,
    );
    expect(blobUploadMock).toHaveBeenCalledWith(
      "uploads/match.dem",
      file,
      expect.objectContaining({
        access: "public",
        handleUploadUrl: "/api/blob/upload",
        contentType: "application/octet-stream",
        multipart: false,
        abortSignal: controller.signal,
      }),
    );
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/replay/import-url");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      url: "https://store.public.blob.vercel-storage.com/uploads/match-123.dem",
      filename: "match.dem",
    });
    const [cleanupUrl, cleanupInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(cleanupUrl).toBe("/api/blob/cleanup");
    expect(cleanupInit.method).toBe("POST");
    expect(JSON.parse(String(cleanupInit.body))).toEqual({
      url: "https://store.public.blob.vercel-storage.com/uploads/match-123.dem",
    });
  });

  it("retains the temporary Blob when processing has not completed", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(manifest, 202));
    vi.stubGlobal("fetch", fetchMock);
    blobUploadMock.mockResolvedValue({
      url: "https://store.public.blob.vercel-storage.com/uploads/match-123.dem",
    });

    await expect(
      uploadReplay(new File(["demo"], "match.dem"), undefined, "blob"),
    ).resolves.toEqual(manifest);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("uses multipart Blob upload above 100 MB and rejects files above 1 GB", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(manifest, 202));
    vi.stubGlobal("fetch", fetchMock);
    blobUploadMock.mockResolvedValue({
      url: "https://store.public.blob.vercel-storage.com/uploads/large-123.dem",
    });
    const largeFile = new File(["demo"], "large.dem");
    Object.defineProperty(largeFile, "size", { value: 100 * 1024 * 1024 + 1 });

    await uploadReplay(largeFile, undefined, "blob");
    expect(blobUploadMock.mock.calls[0]?.[2]).toEqual(
      expect.objectContaining({ multipart: true }),
    );

    const oversizedFile = new File(["demo"], "oversized.dem");
    Object.defineProperty(oversizedFile, "size", { value: 1024 * 1024 * 1024 + 1 });
    blobUploadMock.mockClear();
    fetchMock.mockClear();

    await expect(uploadReplay(oversizedFile, undefined, "blob")).rejects.toMatchObject({
      kind: "invalid-file",
      operation: "upload",
      message: "Choose a .dem file smaller than 1 GB.",
    });
    expect(blobUploadMock).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("preserves Blob upload cancellation and hides provider failures", async () => {
    blobUploadMock
      .mockRejectedValueOnce(new DOMException("aborted", "AbortError"))
      .mockRejectedValueOnce(new Error("private Blob provider detail"));
    const file = new File(["demo"], "match.dem");

    await expect(uploadReplay(file, undefined, "blob")).rejects.toMatchObject({
      name: "AbortError",
    });
    await expect(uploadReplay(file, undefined, "blob")).rejects.toMatchObject({
      kind: "network",
      operation: "upload",
      message: "The replay could not be uploaded to temporary storage.",
    });
  });

  it("explains disabled and oversized Blob imports without exposing backend details", async () => {
    blobUploadMock.mockResolvedValue({
      url: "https://store.public.blob.vercel-storage.com/uploads/match-123.dem",
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ detail: "private route detail" }, 404))
        .mockResolvedValueOnce(jsonResponse({ detail: "private size detail" }, 413)),
    );
    const file = new File(["demo"], "match.dem");

    await expect(uploadReplay(file, undefined, "blob")).rejects.toMatchObject({
      kind: "not-found",
      status: 404,
      message: "Replay uploads are not enabled on the backend.",
    });
    await expect(uploadReplay(file, undefined, "blob")).rejects.toMatchObject({
      kind: "invalid-file",
      status: 413,
      message: "Choose a smaller .dem replay file.",
    });
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
      "/api/analysis/prepare",
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/replay/replay-1/json",
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
        jsonResponse({ analysis_id: "analysis-1", status: "ready", players: [selectablePlayer] }),
      )
      .mockResolvedValueOnce(jsonResponse(result));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAnalysisPlayers("analysis-1")).resolves.toEqual({
      state: "ready",
      value: { analysis_id: "analysis-1", status: "ready", players: [selectablePlayer] },
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
});
