"use client";

import Image from "next/image";
import { mapDisplayName } from "@/domain/maps";
import type { ProcessedReplaySummary } from "@/domain/processed-replays";

type ProcessedReplaySelectorScreenProps = {
  replays: readonly ProcessedReplaySummary[];
  onBack: () => void;
  onSelect: (replayId: string) => void;
};

export function ProcessedReplaySelectorScreen({
  replays,
  onBack,
  onSelect,
}: ProcessedReplaySelectorScreenProps) {
  return (
    <section className="sample-screen" id="main-content" aria-labelledby="processed-replays-title">
      <div className="sample-panel">
        <p className="kicker">Processed replays</p>
        <div className="sample-title-row">
          <div>
            <h1 id="processed-replays-title" tabIndex={-1}>
              Choose a <span className="accent-word">replay</span>.
            </h1>
            <p className="sample-summary">
              Choose a processed save, then select the player perspective to open.
            </p>
          </div>
          <button className="secondary" type="button" onClick={onBack}>
            Back to start
          </button>
        </div>

        <ul className="sample-list" aria-label="Available processed replays">
          {replays.map((replay) => {
            const mapName = mapDisplayName(replay.map);
            return (
              <li key={replay.replayId}>
                <button
                  className="sample-bar processed-replay-bar"
                  type="button"
                  onClick={() => onSelect(replay.replayId)}
                >
                  <span className="sample-map-media processed-replay-media">
                    <Image
                      className="processed-replay-image"
                      src={`/radars/${replay.map}.png`}
                      alt={`${mapName} tactical radar`}
                      width={320}
                      height={320}
                      sizes="(max-width: 560px) 100vw, 220px"
                    />
                  </span>
                  <span className="sample-bar-copy">
                    <span className="sample-bar-heading">
                      <strong>{replay.displayName}</strong>
                      <span className="sample-map-name">{mapName}</span>
                    </span>
                    <span className="sample-description">{replay.description}</span>
                    <span className="sample-meta">
                      {replay.rounds} rounds · {replay.players} players
                    </span>
                    <span
                      className={`processed-analysis-status${replay.analysisAvailable ? " available" : " unavailable"}`}
                    >
                      {replay.analysisAvailable ? "Saved analysis included" : "No saved analysis"}
                    </span>
                  </span>
                  <span className="sample-select-label">Choose player</span>
                </button>
              </li>
            );
          })}
        </ul>

        <p className="sample-attribution">
          Radar images from Valve&apos;s CS2 assets, distributed by{" "}
          <a
            href="https://github.com/MurkyYT/cs2-map-icons/tree/main/images/radars"
            target="_blank"
            rel="noreferrer"
          >
            MurkyYT/cs2-map-icons
          </a>
          .
        </p>
      </div>
    </section>
  );
}
