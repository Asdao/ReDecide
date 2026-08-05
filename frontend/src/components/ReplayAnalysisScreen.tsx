"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getProcessedReplay, getProcessedReplayAnalysis } from "@/adapters/processed-replay";
import { mapDisplayName } from "@/domain/maps";
import type { ReplayAnalysisResult } from "@/domain/replay";
import {
  buildReplayFrames,
  firstEventCrossed,
  formatReplayTime,
  interpolatedSnapshotsAtTick,
  playerDisplayName,
  playerTimelineEvents,
  radarOverviewForMap,
  roundAtTick,
  worldToRadar,
  type ProcessedReplay,
  type ReplayEvent,
} from "@/domain/replay-viewer";
import { ProductHeader } from "./ProductHeader";

const PLAYBACK_RATES = [0.5, 1, 2, 4, 8];

function eventLabel(event: ReplayEvent): string {
  switch (event.event) {
    case "kill":
      return event.headshot ? "Headshot death" : "Death";
    case "damage":
      return "Damage received";
    default:
      return event.event.replaceAll("_", " ");
  }
}

function markerLabel(displayName: string | null): string {
  if (!displayName) return "?";
  const words = displayName.split(/\s+/).filter(Boolean);
  if (words.length > 1) {
    return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase();
  }
  return displayName.replace(/[^a-z0-9]/gi, "").slice(0, 2).toUpperCase() || "?";
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function eventMatchesAnalysis(event: ReplayEvent, analysis: ReplayAnalysisResult): boolean {
  const decision = analysis.selected_decision;
  const playerMatches = decision.role === "victim"
    ? event.victim_id === decision.player_id
    : event.attacker_id === decision.player_id;
  return (
    event.tick === decision.contact_tick &&
    event.round_num === decision.round_number &&
    event.event === decision.event_category &&
    playerMatches
  );
}

export function ReplayAnalysisScreen({
  initialPlayerId,
  replayId,
  initialReplay,
  initialAnalysis,
  uploaded = false,
  onChoosePlayer,
}: {
  initialPlayerId?: string;
  replayId?: string;
  initialReplay?: ProcessedReplay;
  initialAnalysis?: ReplayAnalysisResult;
  uploaded?: boolean;
  onChoosePlayer?: () => void;
}) {
  const initialTick = initialReplay?.ticks[0]?.tick ?? initialReplay?.rounds[0]?.start ?? 0;
  const [replay, setReplay] = useState<ProcessedReplay | undefined>(initialReplay);
  const [analysis, setAnalysis] = useState<ReplayAnalysisResult | undefined>(initialAnalysis);
  const [loadError, setLoadError] = useState<string>();
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [currentTick, setCurrentTick] = useState(initialTick);
  const [playing, setPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [selectedPlayerId, setSelectedPlayerId] = useState(initialPlayerId ?? "");
  const [selectedEventId, setSelectedEventId] = useState<string>();
  const currentTickRef = useRef(initialTick);
  const lastAnimationTime = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (initialReplay) {
      return;
    }

    const controller = new AbortController();
    let active = true;
    Promise.all([
      getProcessedReplay(replayId, controller.signal),
      getProcessedReplayAnalysis(replayId, controller.signal),
    ])
      .then(([replayValue, analysisValue]) => {
        if (!active) return;
        if (
          analysisValue &&
          (analysisValue.replay_id !== replayValue.replay_id ||
            analysisValue.source !== replayValue.source ||
            analysisValue.map_name !== replayValue.map.name)
        ) {
          throw new Error("The saved analysis did not match the processed replay.");
        }
        const firstTick = replayValue.ticks[0]?.tick ?? replayValue.rounds[0].start;
        setReplay(replayValue);
        setAnalysis(analysisValue);
        currentTickRef.current = firstTick;
        setCurrentTick(firstTick);
        setSelectedPlayerId((current) =>
          replayValue.players.some(({ player_id }) => player_id === current)
            ? current
            : replayValue.players[0].player_id,
        );
      })
      .catch((error: unknown) => {
        if (active && !(error instanceof DOMException && error.name === "AbortError")) {
          setLoadError(error instanceof Error ? error.message : "The replay could not be loaded.");
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [initialAnalysis, initialReplay, loadAttempt, replayId]);

  const frames = useMemo(() => (replay ? buildReplayFrames(replay.ticks) : []), [replay]);
  const firstTick = frames[0]?.tick ?? 0;
  const lastTick = frames.at(-1)?.tick ?? 0;
  const currentSnapshots = useMemo(
    () => interpolatedSnapshotsAtTick(frames, currentTick),
    [currentTick, frames],
  );
  const currentRound = replay ? roundAtTick(replay.rounds, currentTick) : undefined;
  const selectedPlayer = replay?.players.find(({ player_id }) => player_id === selectedPlayerId);
  const selectedSnapshot = currentSnapshots.find(
    ({ player_id }) => player_id === selectedPlayerId,
  );
  const selectedEvent = replay?.events.find(({ event_id }) => event_id === selectedEventId);

  const timelineEvents = useMemo(
    () => (replay ? playerTimelineEvents(replay.events, selectedPlayerId) : []),
    [replay, selectedPlayerId],
  );
  const analysisEventId = useMemo(
    () => analysis ? timelineEvents.find((event) => eventMatchesAnalysis(event, analysis))?.event_id : undefined,
    [analysis, timelineEvents],
  );
  const selectedEventHasAnalysis = Boolean(
    analysis && selectedEvent && eventMatchesAnalysis(selectedEvent, analysis),
  );

  const namesById = useMemo(
    () =>
      new Map(
        replay?.players.map((player) => [player.player_id, playerDisplayName(player)]) ?? [],
      ),
    [replay],
  );

  useEffect(() => {
    if (!playing || !replay || lastTick <= firstTick) {
      lastAnimationTime.current = undefined;
      return;
    }

    let animationFrame = 0;
    const animate = (time: number) => {
      const previous = lastAnimationTime.current ?? time;
      lastAnimationTime.current = time;
      const elapsedSeconds = Math.min((time - previous) / 1000, 0.25);
      const previousTick = currentTickRef.current;
      const nextTick = Math.min(
        lastTick,
        previousTick + elapsedSeconds * replay.map.tick_rate * playbackRate,
      );
      const reachedEvent = firstEventCrossed(timelineEvents, previousTick, nextTick);

      if (reachedEvent) {
        currentTickRef.current = reachedEvent.tick;
        setCurrentTick(reachedEvent.tick);
        setSelectedEventId(reachedEvent.event_id);
        setPlaying(false);
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
        return;
      }

      currentTickRef.current = nextTick;
      setCurrentTick(nextTick);
      if (nextTick >= lastTick) {
        setPlaying(false);
        return;
      }
      animationFrame = requestAnimationFrame(animate);
    };
    animationFrame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrame);
  }, [firstTick, lastTick, playbackRate, playing, replay, timelineEvents]);

  const seek = useCallback(
    (tick: number, eventId?: string) => {
      setPlaying(false);
      const nextTick = clamp(tick, firstTick, lastTick);
      currentTickRef.current = nextTick;
      setCurrentTick(nextTick);
      setSelectedEventId(eventId);
    },
    [firstTick, lastTick],
  );

  const changePerspective = useCallback((playerId: string) => {
    if (uploaded) return;
    setSelectedPlayerId(playerId);
    setSelectedEventId(undefined);
  }, [uploaded]);

  if (!replay) {
    return (
      <main className="shell analysis-loading-shell">
        <ProductHeader brandHref="/" label={uploaded ? "Uploaded replay viewer" : "Processed replay viewer"} />
        <section className="analysis-load-state" id="main-content" aria-live="polite">
          {loadError ? (
            <>
              <p className="eyebrow">Replay unavailable</p>
              <h1>The replay could not be opened.</h1>
              <p>{loadError}</p>
              <button
                className="primary"
                type="button"
                onClick={() => {
                  setLoadError(undefined);
                  setLoadAttempt((n) => n + 1);
                }}
              >
                Try again
              </button>
            </>
          ) : (
            <div className="analysis-load-card loading-border" aria-busy="true">
              <h1>Loading processed replay</h1>
              <p>Preparing the processed positions and timeline in your browser.</p>
            </div>
          )}
        </section>
      </main>
    );
  }

  const mapName = mapDisplayName(replay.map.name);
  const radarOverview = radarOverviewForMap(replay.map.name);
  if (!radarOverview) {
    return (
      <main className="shell analysis-loading-shell">
        <ProductHeader brandHref="/" label={uploaded ? "Uploaded replay viewer" : "Processed replay viewer"} />
        <section className="analysis-load-state" id="main-content" role="alert">
          <p className="eyebrow">Radar unavailable</p>
          <h1>{mapName} is not supported yet.</h1>
          <p>This replay is valid, but its reviewed radar metadata is not bundled.</p>
          {uploaded && onChoosePlayer ? (
            <button className="secondary" type="button" onClick={onChoosePlayer}>
              Back to player selection
            </button>
          ) : null}
        </section>
      </main>
    );
  }

  const duration = Math.max(1, lastTick - firstTick);
  const elapsed = formatReplayTime(currentTick, firstTick, replay.map.tick_rate);
  const total = formatReplayTime(lastTick, firstTick, replay.map.tick_rate);

  return (
    <main className="shell analysis-shell">
      <ProductHeader brandHref="/" label={`${mapName} replay viewer`} />
      <section className="analysis-workspace" id="main-content" aria-label={`${mapName} replay viewer`}>
        <header className="analysis-toolbar">
          <div>
            <p className="eyebrow">{uploaded ? "Uploaded replay" : "Processed replay"} · {mapName}</p>
            <h1>{selectedPlayer ? playerDisplayName(selectedPlayer) : "Player perspective"}</h1>
          </div>
          <div className="analysis-toolbar-controls">
            {uploaded && onChoosePlayer ? (
              <button className="secondary analysis-player-return" type="button" onClick={onChoosePlayer}>
                Choose another player
              </button>
            ) : (
              <label>
                <span>Perspective</span>
                <select
                  value={selectedPlayerId}
                  onChange={(event) => changePerspective(event.currentTarget.value)}
                >
                  {replay.players.map((player) => (
                    <option value={player.player_id} key={player.player_id}>
                      {playerDisplayName(player)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              <span>Round</span>
              <select
                value={currentRound?.round_num ?? replay.rounds[0].round_num}
                onChange={(event) => {
                  const round = replay.rounds.find(
                    ({ round_num }) => round_num === Number(event.currentTarget.value),
                  );
                  if (round) seek(round.freeze_end ?? round.start);
                }}
              >
                {replay.rounds.map((round) => (
                  <option value={round.round_num} key={round.round_num}>
                    Round {round.round_num}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </header>

        <div className={`analysis-stage${selectedEvent ? " inspector-open" : ""}`}>
          <ul className="radar-legend" aria-label="Radar player legend">
            <li><span className="legend-dot selected" />Selected</li>
            <li><span className="legend-dot ally" />Teammate</li>
            <li><span className="legend-dot enemy" />Opponent</li>
            <li><span className="legend-dot dead" />Eliminated</li>
          </ul>

          {selectedEvent ? (
            <aside className="analysis-inspector" aria-labelledby="inspector-title">
              <div className="inspector-heading">
                <p className="eyebrow">Moment inspector</p>
                <h2 id="inspector-title">{eventLabel(selectedEvent)}</h2>
              </div>
              <p className="inspector-summary">
                {selectedEvent.event === "kill"
                  ? `${namesById.get(selectedEvent.victim_id ?? "") ?? "The selected player"} was eliminated by ${namesById.get(selectedEvent.attacker_id ?? "") ?? "an opponent"}.`
                  : `${namesById.get(selectedEvent.victim_id ?? "") ?? "The selected player"} took ${selectedEvent.damage_health ?? "unknown"} damage from ${namesById.get(selectedEvent.attacker_id ?? "") ?? "an opponent"}.`}
              </p>
              <dl className="inspector-facts">
                <div><dt>Round</dt><dd>{selectedEvent.round_num}</dd></div>
                <div><dt>Replay time</dt><dd>{formatReplayTime(selectedEvent.tick, firstTick, replay.map.tick_rate)}</dd></div>
                <div><dt>Tick</dt><dd>{selectedEvent.tick}</dd></div>
                <div><dt>Weapon</dt><dd>{selectedEvent.weapon?.replaceAll("_", " ") ?? "—"}</dd></div>
              </dl>
              {selectedEventHasAnalysis && analysis ? (
                <section className="saved-coaching" aria-labelledby="saved-coaching-title">
                  <p className="eyebrow">Coaching</p>
                  <h3 id="saved-coaching-title">What could be done better</h3>
                  <p>{analysis.coach_analysis.what_could_be_done_better}</p>
                </section>
              ) : null}
            </aside>
          ) : null}

          <section className="radar-panel" aria-label={`2D ${mapName} radar`}>
            <div className="radar-heading">
              <div>
                <p className="eyebrow">Live position</p>
                <h2>
                  {currentRound
                    ? `Round ${currentRound.round_num}`
                    : "Waiting for next round"}
                </h2>
              </div>
              <div className="radar-status" aria-live="polite">
                <span>{selectedSnapshot?.place ?? "Position unavailable"}</span>
                <strong>{selectedSnapshot?.side.toUpperCase() ?? "—"}</strong>
              </div>
            </div>
            <div className="radar-frame">
              <Image
                src={radarOverview.image}
                alt={`${mapName} tactical radar`}
                fill
                priority
                sizes="(max-width: 900px) 100vw, calc(100vh - 22rem)"
              />
              <div className="radar-overlay">
                {currentSnapshots.map((snapshot) => {
                  const position = worldToRadar(snapshot.X, snapshot.Y, radarOverview);
                  const isSelected = snapshot.player_id === selectedPlayerId;
                  const relation = isSelected
                    ? "selected"
                    : snapshot.side === selectedSnapshot?.side
                      ? "ally"
                      : "enemy";
                  return (
                    uploaded ? (
                      <span
                        className={`player-marker ${relation} side-${snapshot.side}${snapshot.alive ? "" : " dead"}`}
                        style={{ left: `${position.left}%`, top: `${position.top}%` }}
                        key={snapshot.player_id}
                        title={`${snapshot.display_name ?? snapshot.player_id} · ${snapshot.side.toUpperCase()} · ${snapshot.health} HP${snapshot.alive ? "" : " · eliminated"}`}
                        aria-label={`${snapshot.display_name ?? snapshot.player_id}, ${relation}, ${snapshot.health} health`}
                      >
                        <span>{markerLabel(snapshot.display_name)}</span>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className={`player-marker ${relation} side-${snapshot.side}${snapshot.alive ? "" : " dead"}`}
                        style={{ left: `${position.left}%`, top: `${position.top}%` }}
                        key={snapshot.player_id}
                        title={`${snapshot.display_name ?? snapshot.player_id} · ${snapshot.side.toUpperCase()} · ${snapshot.health} HP${snapshot.alive ? "" : " · eliminated"}`}
                        aria-label={`${snapshot.display_name ?? snapshot.player_id}, ${relation}, ${snapshot.health} health`}
                        onClick={() => changePerspective(snapshot.player_id)}
                      >
                        <span>{markerLabel(snapshot.display_name)}</span>
                      </button>
                    )
                  );
                })}
              </div>
            </div>
          </section>
        </div>

        <section className="replay-timeline" aria-label="Replay timeline">
          <div className="playback-controls">
            <button type="button" onClick={() => seek(currentTick - replay.map.tick_rate * 5)} aria-label="Rewind 5 seconds">−5s</button>
            <button
              className="play-toggle"
              type="button"
              onClick={() => {
                if (!playing) setSelectedEventId(undefined);
                setPlaying(!playing);
              }}
              aria-label={playing ? "Pause replay" : "Play replay"}
            >
              {playing ? "Pause" : "Play"}
            </button>
            <button type="button" onClick={() => seek(currentTick + replay.map.tick_rate * 5)} aria-label="Fast-forward 5 seconds">+5s</button>
            <label className="speed-control">
              <span className="sr-only">Playback speed</span>
              <select value={playbackRate} onChange={(event) => setPlaybackRate(Number(event.currentTarget.value))}>
                {PLAYBACK_RATES.map((rate) => <option value={rate} key={rate}>{rate}×</option>)}
              </select>
            </label>
            <output aria-label="Current replay time">{elapsed} / {total}</output>
          </div>
          <div className="timeline-track-wrap">
            <div className="round-track" aria-label="Jump to a replay round">
              {replay.rounds.map((round) => {
                const start = ((round.start - firstTick) / duration) * 100;
                const width = (((round.official_end ?? round.end) - round.start) / duration) * 100;
                return (
                  <button
                    type="button"
                    key={round.round_num}
                    className={round.round_num === currentRound?.round_num ? "active" : ""}
                    style={{ left: `${start}%`, width: `${width}%` }}
                    data-label={`Round ${round.round_num}`}
                    aria-label={`Jump to the start of round ${round.round_num}`}
                    onClick={(event) => {
                      event.currentTarget.blur();
                      seek(round.start);
                    }}
                  />
                );
              })}
            </div>
            <input
              className="timeline-range"
              type="range"
              min={firstTick}
              max={lastTick}
              step={1}
              value={Math.round(currentTick)}
              aria-label="Replay position"
              aria-valuetext={`${elapsed}, round ${currentRound?.round_num ?? "unknown"}`}
              onChange={(event) => seek(Number(event.currentTarget.value))}
            />
            <div
              className="event-track"
              aria-label={`Damage and death markers for ${selectedPlayer ? playerDisplayName(selectedPlayer) : "the selected player"}`}
            >
              {timelineEvents.map((event) => (
                <button
                  type="button"
                  className={`${event.event === "kill" ? "death" : "damage"}${analysisEventId === event.event_id ? " coaching" : ""}${selectedEventId === event.event_id ? " selected" : ""}`}
                  style={{ left: `${((event.tick - firstTick) / duration) * 100}%` }}
                  key={event.event_id}
                  title={`Round ${event.round_num}: ${eventLabel(event)}${analysisEventId === event.event_id ? " · Saved analysis" : ""}`}
                  aria-label={`Round ${event.round_num}, ${eventLabel(event)}, ${formatReplayTime(event.tick, firstTick, replay.map.tick_rate)}${analysisEventId === event.event_id ? ", saved analysis" : ""}`}
                  onClick={(clickEvent) => {
                    clickEvent.currentTarget.blur();
                    seek(event.tick, event.event_id);
                  }}
                />
              ))}
            </div>
          </div>
          <div className="timeline-caption">
            <span><i className="damage" />Damage</span>
            <span><i className="death" />Death</span>
            {analysisEventId ? <span><i className="coaching" />Analysis</span> : null}
            <span>Tick {Math.round(currentTick)}</span>
          </div>
        </section>
      </section>
    </main>
  );
}
