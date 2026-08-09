"use client";

import Image from "next/image";
import { mapDisplayName } from "@/domain/maps";
import type { AnalysisPlayer, AnalysisProgressEvent, ReplayManifest } from "@/domain/replay";
import { radarOverviewForMap } from "@/domain/replay-viewer";
import { ProductHeader } from "./ProductHeader";

type ReplayMapLoadingScreenProps = {
  manifest: ReplayManifest;
  player: AnalysisPlayer;
  phase: "coaching" | "recovery" | "visualization";
  progress?: AnalysisProgressEvent;
  onReturnToPlayers: () => void;
};

function playerName(player: AnalysisPlayer): string {
  return player.display_name ?? "Unnamed player";
}

const phaseCopy = {
  coaching: {
    title: "Analysing decision",
    detail: "Coaching can take around 30 seconds. The map will become interactive when it is ready.",
    timeline: "Waiting for player coaching",
  },
  recovery: {
    title: "Checking completed coaching",
    detail: "We are checking the saved result without starting another coaching request.",
    timeline: "Recovering the coaching result",
  },
  visualization: {
    title: "Loading replay positions",
    detail: "Coaching is complete. Player positions and timeline events are being attached to the map.",
    timeline: "Preparing the interactive timeline",
  },
} as const;

export function ReplayMapLoadingScreen({
  manifest,
  player,
  phase,
  progress,
  onReturnToPlayers,
}: ReplayMapLoadingScreenProps) {
  const mapName = mapDisplayName(manifest.map.name);
  const overview = radarOverviewForMap(manifest.map.name);
  const copy = phaseCopy[phase];

  return (
    <main className="shell analysis-shell">
      <ProductHeader brandHref="/" label={`${mapName} replay viewer`} />
      <section
        className="analysis-workspace"
        id="main-content"
        aria-label={`Preparing ${mapName} replay viewer`}
        aria-busy="true"
      >
        <p className="sr-only" aria-live="polite" aria-atomic="true">
          {copy.title}. {progress?.message ?? copy.detail}
        </p>
        <header className="analysis-toolbar">
          <div>
            <p className="eyebrow">Uploaded replay · {mapName}</p>
            <h1>{playerName(player)}</h1>
          </div>
          <div className="analysis-toolbar-controls">
            <button
              className="secondary analysis-player-return"
              type="button"
              onClick={onReturnToPlayers}
            >
              Back to player selection
            </button>
          </div>
        </header>

        <div className="analysis-stage">
          <section className="radar-panel" aria-label={`Loading ${mapName} tactical radar`}>
            <div className="radar-heading">
              <div>
                <p className="eyebrow">Replay workspace</p>
                <h2>{copy.title}</h2>
              </div>
            </div>
            <div className="radar-indicators replay-map-loading-indicators" aria-hidden="true">
              <section className="selected-player-health unavailable">
                <div className="selected-player-health-label">
                  <span>Health</span>
                  <strong>—</strong>
                </div>
                <div className="selected-player-health-track">
                  <span style={{ width: "0%" }} />
                </div>
              </section>
              <section className="radar-win-rate baseline">
                <div className="radar-win-rate-values">
                  <strong className="friendly-team"><span>CT</span>50.0%</strong>
                  <p>Win rate</p>
                  <strong className="enemy-team">50.0%<span>T</span></strong>
                </div>
                <div className="win-rate-track">
                  <span className="win-rate-friendly" style={{ width: "50%" }} />
                  <span className="win-rate-enemy" style={{ width: "50%" }} />
                </div>
              </section>
            </div>
            <div className="radar-frame replay-map-loading-frame">
              {overview ? (
                <Image
                  src={overview.image}
                  alt={`${mapName} tactical radar`}
                  fill
                  priority
                  sizes="(max-width: 900px) 100vw, calc(100vh - 22rem)"
                />
              ) : null}
              <div className="replay-map-loading-copy">
                <strong>{copy.title}</strong>
                <span>{progress?.message ?? copy.detail}</span>
              </div>
            </div>
          </section>
        </div>

        <section className="replay-timeline replay-timeline-loading" aria-label="Replay timeline loading">
          <span>{copy.timeline}</span>
          <div aria-hidden="true" />
        </section>
      </section>
    </main>
  );
}
