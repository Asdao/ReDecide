import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import backendResult from "../../../backend/tests/fixtures/analysis_api_result.json";
import { LandingScreen } from "@/components/LandingScreen";
import { ProductHeader } from "@/components/ProductHeader";
import { ProcessedReplaySelectorScreen } from "@/components/ProcessedReplaySelectorScreen";
import { ProcessedReplayPlayerScreen } from "@/components/ProcessedReplayPlayerScreen";
import { ReplayAnalysisScreen } from "@/components/ReplayAnalysisScreen";
import { ReplayFlowScreen } from "@/components/ReplayFlowScreen";
import { ReplayMapLoadingScreen } from "@/components/ReplayMapLoadingScreen";
import { SampleSelectorScreen } from "@/components/SampleSelectorScreen";
import { PROCESSED_REPLAYS } from "@/domain/processed-replays";
import type { ReplayAnalysisFlowState } from "@/domain/analysis-flow";
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
const uploadedReplay: ProcessedReplay = {
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

const callbacks = {
  onBack: () => undefined,
  onRetryUpload: () => undefined,
  onRetryPrepare: () => undefined,
  onRetryPlayers: () => undefined,
  onSelectPlayer: () => undefined,
  onRetryCoaching: () => undefined,
  onRetryRecovery: () => undefined,
  onRetryVisualization: () => undefined,
  onReturnToPlayers: () => undefined,
};

function renderReplayState(state: ReplayAnalysisFlowState): string {
  return renderToStaticMarkup(createElement(ReplayFlowScreen, { state, ...callbacks }));
}

describe("uploaded replay screens", () => {
  it("renders an enabled, labelled .dem picker on the landing screen", () => {
    const html = renderToStaticMarkup(
      createElement(LandingScreen, {
        onOpenSamples: () => undefined,
        onOpenShowcase: () => undefined,
        onSelectReplay: () => undefined,
      }),
    );

    expect(html).toContain('for="demo-upload"');
    expect(html).toContain('id="demo-upload"');
    expect(html).toContain('accept=".dem"');
    expect(html).not.toContain('id="demo-upload" type="file" accept=".dem" disabled');
    expect(html).toContain('<label class="primary" for="demo-upload"');
    expect(html).toContain("Upload your match and view its analysis.");
  });

  it("uses the animated border without square markers on every loading screen", () => {
    const uploadHtml = renderReplayState({
      status: "uploading",
      file,
      requestId: "upload-1",
    });
    const sampleHtml = renderToStaticMarkup(
      createElement(SampleSelectorScreen, {
        status: "loading",
        samples: [],
        onBack: () => undefined,
        onRetry: () => undefined,
        onSelect: () => undefined,
      }),
    );
    const analysisHtml = renderToStaticMarkup(
      createElement(ReplayAnalysisScreen, {}),
    );
    const processedPlayerHtml = renderToStaticMarkup(
      createElement(ProcessedReplayPlayerScreen, {
        status: "loading",
        summary: PROCESSED_REPLAYS[0],
        onBack: () => undefined,
        onRetry: () => undefined,
        onSelectPlayer: () => undefined,
      }),
    );
    const mapLoadingHtml = renderToStaticMarkup(
      createElement(ReplayMapLoadingScreen, {
        manifest,
        player: players[1],
        phase: "coaching",
        onReturnToPlayers: () => undefined,
      }),
    );

    for (const html of [uploadHtml, sampleHtml, processedPlayerHtml, analysisHtml, mapLoadingHtml]) {
      expect(html).toContain("loading-border");
      expect(html).not.toContain("loading-marker");
      expect(html).not.toContain("progress-marker");
    }
    expect(sampleHtml).toContain('aria-busy="true"');
  });

  it("renders display names and disables players without a coaching decision", () => {
    const unavailablePlayer = { ...players[0], decision_ids: [] };
    const nukeManifest = replayManifestSchema.parse({
      ...manifest,
      map: { ...manifest.map, name: "de_nuke" },
    });
    const html = renderReplayState({
      status: "choosing-player",
      file,
      manifest: nukeManifest,
      analysis,
      players: [unavailablePlayer, players[1]],
    });

    expect(html).toContain("CT One");
    expect(html).toContain("T One");
    expect(html).toContain("<dt>Map</dt><dd>Nuke</dd>");
    expect(html).not.toContain("de_nuke");
    expect(html).toContain('<span class="accent-word">player.</span>');
    expect(html).toContain("No coaching moment");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>[\s\S]*?CT One/);
    expect(html).toContain('aria-label="Players available for coaching"');
  });

  it("sets truthful expectations during the long coaching request", () => {
    const html = renderToStaticMarkup(createElement(ReplayMapLoadingScreen, {
      manifest,
      player: players[1],
      phase: "coaching",
      onReturnToPlayers: () => undefined,
    }));

    expect(html).toContain("around 30 seconds");
    expect(html).toContain("T One");
    expect(html).toContain("%2Fradars%2Fde_mirage.png");
    expect(html).toContain("radar-frame loading-border replay-map-loading-frame");
    expect(html).toContain("Back to player selection");
    expect(html).not.toContain("Perspective");
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain('aria-busy="true"');
  });

  it("keeps uploaded replay perspective fixed inside the map workspace", () => {
    const html = renderToStaticMarkup(createElement(ReplayAnalysisScreen, {
      initialPlayerId: "t1",
      initialReplay: uploadedReplay,
      initialAnalysis: result,
      uploaded: true,
      onChoosePlayer: () => undefined,
    }));

    expect(html).toContain("T One");
    expect(html).toContain("Choose another player");
    expect(html).not.toContain("Perspective");
    expect(html).not.toContain("eventual_winner");
    expect(html).not.toContain("round_score");
  });

  it("labels time between rounds without repeating the round in the timeline legend", () => {
    const waitingReplay: ProcessedReplay = {
      ...uploadedReplay,
      rounds: [{ round_num: 1, start: 100, end: 300 }],
      ticks: uploadedReplay.ticks.map((tick) => ({ ...tick, tick: 50 })),
    };
    const html = renderToStaticMarkup(createElement(ReplayAnalysisScreen, {
      initialPlayerId: "t1",
      initialReplay: waitingReplay,
      initialAnalysis: result,
      uploaded: true,
      onChoosePlayer: () => undefined,
    }));

    expect(html).toContain("Waiting for next round");
    const caption = html.match(/<div class="timeline-caption">[\s\S]*?<\/div>/)?.[0];
    expect(caption).toContain('<span><i class="damage"></i>Damage</span>');
    expect(caption).not.toContain("Round");
  });

  it("uses one keyboard tab stop for timeline markers", () => {
    const eventReplay: ProcessedReplay = {
      ...uploadedReplay,
      events: [
        {
          event_id: "damage-1",
          event: "damage",
          tick: 150,
          round_num: 1,
          attacker_id: "ct1",
          victim_id: "t1",
          damage_health: 20,
        },
        {
          event_id: "death-1",
          event: "kill",
          tick: 250,
          round_num: 1,
          attacker_id: "ct1",
          victim_id: "t1",
        },
      ],
      ticks: [
        uploadedReplay.ticks[0],
        { ...uploadedReplay.ticks[0], tick: 300 },
      ],
    };
    const html = renderToStaticMarkup(createElement(ReplayAnalysisScreen, {
      initialPlayerId: "t1",
      initialReplay: eventReplay,
      uploaded: true,
      onChoosePlayer: () => undefined,
    }));

    expect(html.match(/class="damage"[^>]*tabindex="0"/g)).toHaveLength(1);
    expect(html.match(/class="death"[^>]*tabindex="-1"/g)).toHaveLength(1);
    expect(html).toContain("Damage and death markers for T One");
  });

  it("uses one blocking alert and hides retry for a non-retryable upload rejection", () => {
    const html = renderReplayState({
      status: "upload-error",
      file,
      error: {
        code: "invalid-file",
        message: "Choose a valid .dem replay file.",
        retryable: false,
      },
    });

    expect(html.match(/role="alert"/g)).toHaveLength(1);
    expect(html).toContain("Choose a valid .dem replay file.");
    expect(html).not.toContain("Retry upload");
    expect(html).toContain('class="secondary replay-reset-button"');
    expect(html).toContain('Choose another <span class="accent-word">replay</span>');
  });
});

describe("sample replay screens", () => {
  it("offers backend samples and the processed showcase as separate actions", () => {
    const html = renderToStaticMarkup(
      createElement(LandingScreen, {
        onOpenSamples: () => undefined,
        onOpenShowcase: () => undefined,
        onSelectReplay: () => undefined,
      }),
    );

    expect(html).toContain("Use a sample match");
    expect(html).toContain('<button class="secondary" type="button" aria-describedby="sample-note"');
    expect(html).toContain("currently available from the backend");
    expect(html).toContain("Open processed replays");
    expect(html).toContain("already-processed replay");
    expect(html).toContain("go straight to its analysis");
    expect(html).toContain('class="action-note action-note-accent"');
    expect(html.match(/class="action-note action-note-steel"/g)).toHaveLength(2);
  });

  it("gives the product logo a home navigation target", () => {
    const html = renderToStaticMarkup(
      createElement(ProductHeader, {
        brandHref: "/",
      }),
    );

    expect(html).toContain('href="/"');
    expect(html).toContain('aria-label="Back to RE:DECIDE home"');
  });

  it("lists both processed saves and their analysis availability", () => {
    const html = renderToStaticMarkup(
      createElement(ProcessedReplaySelectorScreen, {
        replays: PROCESSED_REPLAYS,
        onBack: () => undefined,
        onSelect: () => undefined,
      }),
    );

    expect(html).toContain("Mirage showcase");
    expect(html).toContain("Inferno processed replay");
    expect(html).toContain("No saved analysis");
    expect(html).toContain("Saved analysis included");
    expect(html.match(/Choose player/g)).toHaveLength(2);
    expect(html).not.toContain("Choose your");
    expect(html).toContain(
      'href="https://github.com/MurkyYT/cs2-map-icons/tree/main/images/radars"',
    );
    expect(html).toContain('target="_blank"');
    expect(html).toContain("MurkyYT/cs2-map-icons</a>");
  });

  it("shows the selected replay's players before opening the renderer", () => {
    const replay = {
      schema_version: "replay_visualization_v1" as const,
      replay_id: "mirage-showcase",
      source: "mirage.dem",
      map: { name: "de_mirage", tick_rate: 64 },
      players: manifest.players.map((player) => ({
        ...player,
        sides: player.sides.map((side) => side.toLowerCase()),
      })),
      rounds: [{ round_num: 1, start: 100, end: 300 }],
      events: [],
      ticks: [],
    };
    const html = renderToStaticMarkup(
      createElement(ProcessedReplayPlayerScreen, {
        status: "ready",
        summary: PROCESSED_REPLAYS[0],
        replay,
        onBack: () => undefined,
        onRetry: () => undefined,
        onSelectPlayer: () => undefined,
      }),
    );

    expect(html).toContain("Choose your");
    expect(html).toContain("CT One");
    expect(html).toContain("T One");
    expect(html).toContain("Open perspective");
    expect(html).toContain("Back to replays");
    expect(html).toContain("Not included");
  });

  it("identifies the player with saved analysis in the Inferno roster", () => {
    const infernoSummary = PROCESSED_REPLAYS[1];
    const replay = {
      schema_version: "replay_visualization_v1" as const,
      replay_id: "inferno-replay",
      source: "inferno.dem",
      map: { name: "de_inferno", tick_rate: 64 },
      players: [
        { player_id: infernoSummary.analysisPlayerId!, display_name: "flameZ", sides: ["t"] },
        { player_id: "other-player", display_name: "Other", sides: ["ct"] },
      ],
      rounds: [{ round_num: 1, start: 1, end: 100 }],
      events: [],
      ticks: [],
    };
    const html = renderToStaticMarkup(
      createElement(ProcessedReplayPlayerScreen, {
        status: "ready",
        summary: infernoSummary,
        replay,
        onBack: () => undefined,
        onRetry: () => undefined,
        onSelectPlayer: () => undefined,
      }),
    );

    expect(html).toContain("Included");
    expect(html).toContain("Saved analysis");
    expect(html).toContain("Replay only");
    expect(html).toContain("Open analysis");
  });

  it("uses an official map name instead of the backend map identifier", () => {
    const html = renderToStaticMarkup(
      createElement(SampleSelectorScreen, {
        status: "ready",
        samples: [
          {
            sample_id: "nuke-sample",
            display_name: "Nuke example",
            description: "A sample coaching moment",
            map: "de_nuke",
            players: ["Player One"],
            recommended_player: "Player One",
            available: true,
          },
        ],
        onBack: () => undefined,
        onRetry: () => undefined,
        onSelect: () => undefined,
      }),
    );

    expect(html).toContain('<span class="sample-map-name">Nuke</span>');
    expect(html).toContain('alt="Nuke map thumbnail"');
    expect(html).toContain('Choose a <span class="accent-word">match</span>.');
  });
});
