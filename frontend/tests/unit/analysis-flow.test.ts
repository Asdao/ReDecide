import { describe, expect, it } from "vitest";
import decisionPacket from "../../../backend/tests/fixtures/decision_packet.valid.json";
import {
  analysisFlowReducer,
  initialAnalysisFlowState,
} from "@/domain/analysis-flow";
import { mapDisplayName } from "@/domain/maps";
import {
  isLandingChildHistoryEntry,
  landingHistoryViewFromState,
  landingViewFromSearch,
  landingViewHref,
  withLandingHistoryMarker,
} from "@/domain/landing-navigation";
import {
  mapAssetKey,
  mapThumbnailUrl,
  samplePreparationSchema,
  sampleReplayPreparationSchema,
  samplesResponseSchema,
} from "@/domain/samples";

const sample = {
  sample_id: "fixture-mirage-01",
  display_name: "Mirage post-contact example",
  description: "Low-health repeat exposure after first contact",
  map: "de_mirage",
  players: ["PlayerA"],
  recommended_player: "PlayerA",
  available: true,
};

const preparation = {
  stage: "PLAYER_SELECTION_REQUIRED" as const,
  analysis_id: "sample:fixture-mirage-01",
  players: ["PlayerA"],
  decision_packet: null,
  neutral_summary: null,
};

const replayPreparation = {
  sample_id: sample.sample_id,
  replay_id: "sample-replay-01",
  manifest: {
    schema_version: "replay_manifest_v1" as const,
    replay_id: "sample-replay-01",
    source: "Mirage post-contact example.dem",
    map: { name: "de_mirage", tick_rate: 64 },
    players: [{ player_id: "p1", display_name: "PlayerA", sides: ["CT"] }],
    rounds: [{ round_num: 1, start: 0, end: 100 }],
    visualization_status: "ready" as const,
    coaching_status: "ready" as const,
    visualization_unlocked: false,
  },
  analysis: {
    analysis_id: "sample-analysis-01",
    status: "ready" as const,
    players_available: true,
    result_available: false,
    selected_player_id: null,
    player_runs: {},
    logs_url: "/api/analysis/sample-analysis-01/logs",
    events_url: "/api/analysis/sample-analysis-01/events",
    result_url: "/api/analysis/sample-analysis-01/result",
  },
};

describe("backend sample flow", () => {
  it("maps landing views to stable, query-preserving history URLs", () => {
    expect(landingViewFromSearch("")).toBe("home");
    expect(landingViewFromSearch("?view=samples")).toBe("samples");
    expect(landingViewFromSearch("?view=showcase&utm_source=test")).toBe("showcase");
    expect(landingViewFromSearch("?view=unknown")).toBe("home");

    expect(landingViewHref("samples", "?utm_source=test")).toBe(
      "/?utm_source=test&view=samples",
    );
    expect(landingViewHref("showcase", "?view=samples&utm_source=test")).toBe(
      "/?view=showcase&utm_source=test",
    );
    expect(landingViewHref("home", "?view=showcase&utm_source=test")).toBe(
      "/?utm_source=test",
    );
  });

  it("marks only owned sample and showcase entries as child history views", () => {
    const existingState = { nextInternal: "preserved" };
    const home = withLandingHistoryMarker(existingState, "home", false);
    const showcase = withLandingHistoryMarker(home, "showcase", true);
    const upload = withLandingHistoryMarker(home, "upload", true);
    const uploadViewer = withLandingHistoryMarker(upload, "upload-viewer", true);

    expect(home).toMatchObject(existingState);
    expect(isLandingChildHistoryEntry(home)).toBe(false);
    expect(isLandingChildHistoryEntry(showcase)).toBe(true);
    expect(isLandingChildHistoryEntry(showcase, "showcase")).toBe(true);
    expect(isLandingChildHistoryEntry(showcase, "samples")).toBe(false);
    expect(isLandingChildHistoryEntry(upload)).toBe(true);
    expect(isLandingChildHistoryEntry(upload, "upload")).toBe(true);
    expect(isLandingChildHistoryEntry(uploadViewer, "upload-viewer")).toBe(true);
    expect(landingHistoryViewFromState(upload)).toBe("upload");
    expect(landingHistoryViewFromState(uploadViewer)).toBe("upload-viewer");
    expect(isLandingChildHistoryEntry(null)).toBe(false);
  });

  it("validates zero, one, and many sample responses", () => {
    expect(samplesResponseSchema.parse({ samples: [] }).samples).toEqual([]);
    expect(samplesResponseSchema.parse({ samples: [sample] }).samples).toHaveLength(1);
    expect(samplesResponseSchema.parse({ samples: [sample, { ...sample, sample_id: "two" }] }).samples).toHaveLength(2);
  });

  it("enforces the backend sample invariants and stage payload", () => {
    expect(() =>
      samplesResponseSchema.parse({
        samples: [{ ...sample, players: ["PlayerA", "PlayerA"] }],
      }),
    ).toThrow("sample players must be unique");
    expect(() =>
      samplesResponseSchema.parse({
        samples: [{ ...sample, recommended_player: "MissingPlayer" }],
      }),
    ).toThrow("recommended_player must appear in players");
    expect(samplePreparationSchema.parse(preparation)).toEqual(preparation);
    expect(() =>
      samplePreparationSchema.parse({ ...preparation, decision_packet: {} }),
    ).toThrow();
    expect(
      samplePreparationSchema.parse({
        stage: "INTENT_REQUIRED",
        analysis_id: "fixture-analysis-01",
        players: ["PlayerA"],
        decision_packet: decisionPacket,
        neutral_summary: {
          timestamp_seconds: 96.45,
          text: "PlayerA exposed again 0.9 seconds after contact",
        },
      }).stage,
    ).toBe("INTENT_REQUIRED");
    expect(sampleReplayPreparationSchema.parse(replayPreparation)).toEqual(replayPreparation);
  });

  it("moves from the landing page to a loaded backend list", () => {
    const loading = analysisFlowReducer(initialAnalysisFlowState, { type: "OPEN_SAMPLES" });
    expect(loading).toEqual({ status: "loading-samples" });

    const ready = analysisFlowReducer(loading, { type: "SAMPLES_LOADED", samples: [sample] });
    expect(ready).toEqual({ status: "samples-ready", samples: [sample] });
  });

  it("selects an available sample and preserves the backend preparation", () => {
    const ready = { status: "samples-ready" as const, samples: [sample] };
    const selecting = analysisFlowReducer(ready, {
      type: "SELECT_SAMPLE",
      sampleId: sample.sample_id,
    });
    expect(selecting).toEqual({
      status: "selecting-sample",
      samples: [sample],
      sampleId: sample.sample_id,
    });

    expect(
      analysisFlowReducer(selecting, {
        type: "SAMPLE_SELECTED",
        sampleId: sample.sample_id,
        preparation,
      }),
    ).toEqual({
      status: "sample-selected",
      samples: [sample],
      sampleId: sample.sample_id,
      preparation,
    });

    const waiting = analysisFlowReducer(selecting, {
      type: "SAMPLE_REPLAY_READY",
      sampleId: sample.sample_id,
      sourceName: "Mirage post-contact example",
      preparation: replayPreparation,
      playersRequestId: "players-1",
    });
    expect(waiting).toMatchObject({
      status: "waiting-for-players",
      sampleId: sample.sample_id,
      manifest: replayPreparation.manifest,
      analysis: replayPreparation.analysis,
      requestId: "players-1",
    });
  });

  it("does not select an unavailable sample", () => {
    const unavailable = { ...sample, available: false };
    const ready = { status: "samples-ready" as const, samples: [unavailable] };
    expect(
      analysisFlowReducer(ready, { type: "SELECT_SAMPLE", sampleId: unavailable.sample_id }),
    ).toEqual(ready);
  });

  it("supports safe list and selection errors, retry, and reset", () => {
    const loading = analysisFlowReducer(initialAnalysisFlowState, { type: "OPEN_SAMPLES" });
    const failed = analysisFlowReducer(loading, { type: "SAMPLES_FAILED" });
    expect(failed).toEqual({ status: "samples-error" });

    const retrying = analysisFlowReducer(failed, { type: "OPEN_SAMPLES" });
    expect(retrying).toEqual({ status: "loading-samples" });
    expect(analysisFlowReducer(retrying, { type: "RESET" })).toEqual({ status: "choose" });
  });

  it("maps backend map names to the repository thumbnail convention", () => {
    expect(mapAssetKey("de_mirage")).toBe("de_mirage");
    expect(mapAssetKey("Mirage")).toBe("de_mirage");
    expect(mapAssetKey("Office")).toBe("cs_office");
    expect(mapAssetKey("Pool Day")).toBe("ar_pool_day");
    expect(mapThumbnailUrl("de_mirage")).toBe("/maps/de_mirage.png");
  });

  it.each([
    ["de_ancient", "Ancient"],
    ["de_anubis", "Anubis"],
    ["de_cache", "Cache"],
    ["de_dust2", "Dust II"],
    ["de_inferno", "Inferno"],
    ["de_mirage", "Mirage"],
    ["de_nuke", "Nuke"],
    ["de_overpass", "Overpass"],
    ["de_train", "Train"],
    ["de_vertigo", "Vertigo"],
    ["cs_agency", "Agency"],
    ["cs_italy", "Italy"],
    ["cs_office", "Office"],
    ["ar_baggage", "Baggage"],
    ["ar_pool_day", "Pool Day"],
    ["ar_shoots", "Shoots"],
    ["ar_shoots_night", "Shoots (Night)"],
    ["de_cbble", "Cobblestone"],
    ["de_eldorado", "El Dorado"],
    ["de_stmarc", "St. Marc"],
    ["workshop/123456/de_el_dorado.vpk", "El Dorado"],
    ["custom_community_map", "Custom Community Map"],
  ])("formats the CS2 map identifier %s as %s", (mapId, expectedName) => {
    expect(mapDisplayName(mapId)).toBe(expectedName);
  });
});
