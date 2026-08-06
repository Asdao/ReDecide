import { afterEach, describe, expect, it, vi } from "vitest";
import { getSamples, selectSample } from "@/adapters/samples-api";

const manifest = {
  schema_version: "replay_manifest_v1",
  replay_id: "sample-replay-01",
  source: "sample.dem",
  map: { name: "de_mirage", tick_rate: 64 },
  players: [{ player_id: "p1", display_name: "PlayerA", sides: ["CT"] }],
  rounds: [{ round_num: 1, start: 0, end: 100 }],
  visualization_status: "ready",
  coaching_status: "ready",
  visualization_unlocked: false,
};

const analysis = {
  analysis_id: "sample-analysis-01",
  status: "ready",
  players_available: true,
  result_available: false,
  selected_player_id: null,
  player_runs: {},
  logs_url: "/api/analysis/sample-analysis-01/logs",
  events_url: "/api/analysis/sample-analysis-01/events",
  result_url: "/api/analysis/sample-analysis-01/result",
};

afterEach(() => vi.restoreAllMocks());

describe("sample API adapter", () => {
  it("loads the backend sample catalog", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          samples: [
            {
              sample_id: "sample-01",
              display_name: "Mirage sample",
              description: "A hosted sample replay",
              map: "de_mirage",
              players: [],
              recommended_player: null,
              available: true,
            },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getSamples()).resolves.toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/samples",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("returns the real replay envelope for sample selection", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ sample_id: "sample-01", replay_id: manifest.replay_id, manifest, analysis }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(selectSample("sample-01")).resolves.toMatchObject({
      sample_id: "sample-01",
      replay_id: "sample-replay-01",
      analysis: { analysis_id: "sample-analysis-01" },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/analyze",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ sample_id: "sample-01" }),
      }),
    );
  });
});
