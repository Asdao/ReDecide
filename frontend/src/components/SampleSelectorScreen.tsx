"use client";

import Image from "next/image";
import { useState } from "react";
import { mapDisplayName } from "@/domain/maps";
import {
  mapThumbnailUrl,
  type SamplePreparation,
  type SampleSummary,
} from "@/domain/samples";

type SampleSelectorScreenProps = {
  status: "loading" | "ready" | "error";
  samples: SampleSummary[];
  selectingSampleId?: string;
  selectedSampleId?: string;
  preparation?: SamplePreparation;
  selectionFailedId?: string;
  onBack: () => void;
  onRetry: () => void;
  onSelect: (sampleId: string) => void;
};

function MapThumbnail({ map }: { map: string }) {
  const thumbnailUrl = mapThumbnailUrl(map);
  const displayName = mapDisplayName(map);
  const [failedUrl, setFailedUrl] = useState<string>();

  if (failedUrl === thumbnailUrl) {
    return (
      <span className="sample-map-fallback" aria-label={`No thumbnail available for ${displayName}`}>
        <span>Map image unavailable</span>
        <strong>{displayName}</strong>
      </span>
    );
  }

  return (
    <Image
      className="sample-map-image"
      src={thumbnailUrl}
      alt={`${displayName} map thumbnail`}
      width={320}
      height={180}
      sizes="(max-width: 560px) 100vw, 220px"
      onError={() => setFailedUrl(thumbnailUrl)}
    />
  );
}

function SampleBar({
  sample,
  isSelecting,
  isSelected,
  selectionFailed,
  onSelect,
}: {
  sample: SampleSummary;
  isSelecting: boolean;
  isSelected: boolean;
  selectionFailed: boolean;
  onSelect: (sampleId: string) => void;
}) {
  const unavailable = !sample.available;
  const displayMapName = mapDisplayName(sample.map);
  const statusLabel = unavailable
    ? "Unavailable"
    : isSelecting
      ? "Preparing…"
      : isSelected
        ? "Selected"
        : selectionFailed
          ? "Try again"
          : "Select match";

  return (
    <li>
      <button
        className={`sample-bar${isSelecting ? " loading-border" : ""}${isSelected ? " selected" : ""}${selectionFailed ? " failed" : ""}`}
        type="button"
        disabled={unavailable || isSelecting}
        aria-busy={isSelecting}
        aria-pressed={isSelected}
        onClick={() => onSelect(sample.sample_id)}
      >
        <span className="sample-map-media">
          <MapThumbnail map={sample.map} />
        </span>
        <span className="sample-bar-copy">
          <span className="sample-bar-heading">
            <strong>{sample.display_name}</strong>
            <span className="sample-map-name">{displayMapName}</span>
          </span>
          <span className="sample-description">{sample.description}</span>
        </span>
        <span className="sample-select-label">{statusLabel}</span>
      </button>
      {selectionFailed ? (
        <p className="sample-row-error" role="alert">
          This match could not be prepared. Select it to try again.
        </p>
      ) : null}
    </li>
  );
}

export function SampleSelectorScreen({
  status,
  samples,
  selectingSampleId,
  selectedSampleId,
  preparation,
  selectionFailedId,
  onBack,
  onRetry,
  onSelect,
}: SampleSelectorScreenProps) {
  return (
    <section className="sample-screen" id="main-content" aria-labelledby="samples-title">
      <div className="sample-panel">
        <p className="kicker">Sample matches</p>
        <div className="sample-title-row">
          <div>
            <h1 id="samples-title" tabIndex={-1}>
              Choose a <span className="accent-word">match</span>.
            </h1>
            <p className="sample-summary">
              Pick a sample replay to inspect one of its decisions.
            </p>
          </div>
          <button className="secondary" type="button" onClick={onBack}>
            Back to start
          </button>
        </div>

        {status === "loading" ? (
          <div
            className="sample-list-state loading-border"
            role="status"
            aria-live="polite"
            aria-busy="true"
          >
            Loading sample matches…
          </div>
        ) : null}

        {status === "error" ? (
          <div className="sample-list-state sample-list-error" role="alert">
            <p>We couldn&apos;t load the sample matches from the backend.</p>
            <button className="primary" type="button" onClick={onRetry}>
              Try again
            </button>
          </div>
        ) : null}

        {status === "ready" && samples.length === 0 ? (
          <div className="sample-list-state">
            <p>No sample matches are available right now.</p>
          </div>
        ) : null}

        {status === "ready" && samples.length > 0 ? (
          <ul className="sample-list" aria-label="Available sample matches" aria-busy={Boolean(selectingSampleId)}>
            {samples.map((sample) => (
              <SampleBar
                key={sample.sample_id}
                sample={sample}
                isSelecting={selectingSampleId === sample.sample_id}
                isSelected={selectedSampleId === sample.sample_id}
                selectionFailed={selectionFailedId === sample.sample_id}
                onSelect={onSelect}
              />
            ))}
          </ul>
        ) : null}

        {preparation ? (
          <p className="sample-selection-note" role="status" aria-live="polite">
            Match selected. The backend found {preparation.players.length}{" "}
            {preparation.players.length === 1 ? "player" : "players"} for the next step.
          </p>
        ) : null}

        <p className="sample-attribution">
          Map thumbnails from{" "}
          <a
            href="https://github.com/MurkyYT/cs2-map-icons/tree/main/images/thumbs"
            target="_blank"
            rel="noopener noreferrer"
          >
            MurkyYT/cs2-map-icons
          </a>
          .
        </p>
      </div>
    </section>
  );
}
