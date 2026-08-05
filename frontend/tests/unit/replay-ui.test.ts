import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import backendResult from "../../../backend/tests/fixtures/analysis_api_result.json";
import { LandingScreen } from "@/components/LandingScreen";
import { ReplayFlowScreen } from "@/components/ReplayFlowScreen";
import type { ReplayAnalysisFlowState } from "@/domain/analysis-flow";
import {
  analysisJobSchema,
  analysisPlayersSchema,
  replayAnalysisResultSchema,
  replayManifestSchema,
} from "@/domain/replay";

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
  status: "ready",
  players_available: true,
  result_available: false,
  logs_url: "/api/analysis/analysis-1/logs",
  events_url: "/api/analysis/analysis-1/events",
  result_url: "/api/analysis/analysis-1/result",
});
const players = analysisPlayersSchema.parse({
  analysis_id: "analysis-1",
  status: "ready",
  players: backendResult.players,
}).players;
const result = replayAnalysisResultSchema.parse({
  ...backendResult,
  replay_outcome: {
    eventual_winner: "CT",
    round_score: { CT: 1, T: 0 },
    source: "round_score",
  },
});

const callbacks = {
  onBack: () => undefined,
  onRetryUpload: () => undefined,
  onRetryPrepare: () => undefined,
  onRetryPlayers: () => undefined,
  onSelectPlayer: () => undefined,
  onRetryCoaching: () => undefined,
  onRetryRecovery: () => undefined,
};

function renderReplayState(state: ReplayAnalysisFlowState): string {
  return renderToStaticMarkup(createElement(ReplayFlowScreen, { state, ...callbacks }));
}

describe("uploaded replay screens", () => {
  it("renders an enabled, labelled .dem picker on the landing screen", () => {
    const html = renderToStaticMarkup(
      createElement(LandingScreen, {
        onOpenExample: () => undefined,
        onSelectReplay: () => undefined,
      }),
    );

    expect(html).toContain('for="demo-upload"');
    expect(html).toContain('id="demo-upload"');
    expect(html).toContain('accept=".dem"');
    expect(html).not.toContain('id="demo-upload" type="file" accept=".dem" disabled');
    expect(html).toContain("uploaded once");
  });

  it("renders display names and disables players without a coaching decision", () => {
    const unavailablePlayer = { ...players[0], decision_ids: [] };
    const html = renderReplayState({
      status: "choosing-player",
      file,
      manifest,
      analysis,
      players: [unavailablePlayer, players[1]],
    });

    expect(html).toContain("CT One");
    expect(html).toContain("T One");
    expect(html).toContain("No coaching moment");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>[\s\S]*?CT One/);
    expect(html).toContain('aria-label="Players available for coaching"');
  });

  it("sets truthful expectations during the long coaching request", () => {
    const html = renderReplayState({
      status: "running-coaching",
      file,
      manifest,
      analysis,
      players,
      selectedPlayer: players[1],
      requestId: "coach-1",
    });

    expect(html).toContain("around 30 seconds");
    expect(html).toContain("will not be uploaded again");
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain('aria-busy="true"');
  });

  it("renders validated coaching without exposing the later match outcome", () => {
    const html = renderReplayState({
      status: "result",
      file,
      manifest,
      analysis,
      players,
      selectedPlayer: players[1],
      result,
    });

    expect(html).toContain("What could be done better");
    expect(html).toContain("Break line of sight after first contact and wait for support.");
    expect(html).toContain("T One");
    expect(html).not.toContain("eventual_winner");
    expect(html).not.toContain("round_score");
  });
});
