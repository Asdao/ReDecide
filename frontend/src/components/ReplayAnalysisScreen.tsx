"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { getProcessedReplay, getProcessedReplayAnalysis } from "@/adapters/processed-replay";
import { mapDisplayName } from "@/domain/maps";
import {
  momentIntentReducer,
  type MomentIntentSubmission,
} from "@/domain/moment-intent";
import type { ReplayAnalysisEntry, ReplayAnalysisResult } from "@/domain/replay";
import {
  analysisTimelineEvents,
  analysisEntryForEvent,
  buildReplayFrames,
  eventMatchesAnalysis,
  firstEventCrossed,
  formatReplayTime,
  interpolatedSnapshotsAtTick,
  playerDisplayName,
  radarOverviewForMap,
  replayEventIsDeath,
  roundAtTick,
  winProbabilityAtMoment,
  winRateForPerspective,
  worldToRadar,
  type ProcessedReplay,
  type ReplayEvent,
} from "@/domain/replay-viewer";
import { submitPlayerIntent, type IntentCoachingResponse } from "@/adapters/replay-api";
import { isAbortError } from "@/lib/http";
import { ProductHeader } from "./ProductHeader";

const PLAYBACK_RATES = [0.5, 1, 2, 4, 8];

function eventLabel(
  event: ReplayEvent,
  analysis?: ReplayAnalysisEntry,
): string {
  if (event.event === "kill") {
    return event.headshot ? "Headshot death" : "Death";
  }
  if (analysis && eventMatchesAnalysis(event, analysis)) {
    if (analysis.selected_decision.event_category === "damage") {
      return analysis.selected_decision.role === "attacker" ? "Damage dealt" : "Damage received";
    }
    return "Analysis point";
  }
  if (replayEventIsDeath(event)) {
    return event.headshot ? "Headshot death" : "Death";
  }
  switch (event.event) {
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

function formatProbability(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function ReplayAnalysisScreen({
  initialPlayerId,
  replayId,
  analysisId,
  initialReplay,
  initialAnalysis,
  uploaded = false,
  onChoosePlayer,
  submitMomentIntent,
}: {
  initialPlayerId?: string;
  replayId?: string;
  analysisId?: string;
  initialReplay?: ProcessedReplay;
  initialAnalysis?: ReplayAnalysisResult;
  uploaded?: boolean;
  onChoosePlayer?: () => void;
  submitMomentIntent?: MomentIntentSubmission;
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
  const [intentInputText, setIntentInputText] = useState("");
  const [intentLoading, setIntentLoading] = useState(false);
  const [intentResponse, setIntentResponse] = useState<IntentCoachingResponse>();
  const [intentError, setIntentError] = useState<string>();
  const [intentDrafts, setIntentDrafts] = useState<Readonly<Record<string, string>>>({});
  const [intentStates, dispatchIntent] = useReducer(momentIntentReducer, {});
  const currentTickRef = useRef(initialTick);
  const lastAnimationTime = useRef<number | undefined>(undefined);
  const eventMarkerRefs = useRef(new Map<string, HTMLButtonElement>());
  const intentRequestId = useRef(0);
  const intentControllers = useRef(new Map<string, AbortController>());

  useEffect(() => () => {
    for (const controller of intentControllers.current.values()) {
      controller.abort();
    }
    intentControllers.current.clear();
  }, []);

  const handleIntentSubmit = async () => {
    if (!intentInputText.trim() || !selectedPlayerId) return;
    setIntentLoading(true);
    setIntentError(undefined);
    try {
      const activeAnalysisId = analysis?.replay_id ?? replayId ?? "sample:fixture-mirage-01";
      const activeDecisionId = analysis?.selected_decision?.decision_id ?? "r1:p1:t2579";
      const result = await submitPlayerIntent(
        activeAnalysisId,
        selectedPlayerId,
        activeDecisionId,
        intentInputText.trim(),
      );
      setIntentResponse(result);
    } catch (err: unknown) {
      setIntentError(err instanceof Error ? err.message : "Could not evaluate intent.");
    } finally {
      setIntentLoading(false);
    }
  };

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
        if (active && !isAbortError(error)) {
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
  const selectedHealth = selectedSnapshot
    ? clamp(selectedSnapshot.health, 0, 100)
    : undefined;
  const selectedHealthLevel = selectedHealth === undefined
    ? "unavailable"
    : selectedHealth < 20
      ? "critical"
      : selectedHealth < 60
        ? "low"
        : "healthy";
  const timelineEvents = useMemo(
    () => (replay ? analysisTimelineEvents(replay.events, selectedPlayerId, analysis) : []),
    [analysis, replay, selectedPlayerId],
  );
  const selectedEvent = timelineEvents.find(({ event_id }) => event_id === selectedEventId);
  const analysisByEventId = useMemo(
    () => new Map(
      timelineEvents.flatMap((event) => {
        const entry = analysisEntryForEvent(event, analysis);
        return entry ? [[event.event_id, entry] as const] : [];
      }),
    ),
    [analysis, timelineEvents],
  );
  const selectedEventAnalysis = selectedEvent ? analysisByEventId.get(selectedEvent.event_id) : undefined;
  const selectedEventHasAnalysis = Boolean(selectedEventAnalysis);
  const analysisEventIds = useMemo(() => new Set(analysisByEventId.keys()), [analysisByEventId]);
  const analysedEvents = useMemo(
    () => timelineEvents.filter((event) => analysisEventIds.has(event.event_id)),
    [analysisEventIds, timelineEvents],
  );
  const selectedEventKind = selectedEvent?.event === "kill"
    ? "death"
    : selectedEventHasAnalysis
      ? "analysis"
      : selectedEvent && replayEventIsDeath(selectedEvent)
        ? "death"
        : "damage";
  const selectedIntentState = selectedEventId ? intentStates[selectedEventId] : undefined;
  const selectedIntentDraft = selectedEventId ? intentDrafts[selectedEventId] ?? "" : "";
  const currentWinProbability = useMemo(
    () => currentRound && analysis
      ? winProbabilityAtMoment(
          analysis.win_estimator.timeline,
          currentRound.round_num,
          currentTick,
        )
      : undefined,
    [analysis, currentRound, currentTick],
  );
  const selectedAnalysisPlayer = analysis?.players.find(
    ({ player_id }) => player_id === selectedPlayerId,
  );
  const selectedSide = (
    currentRound
      ? selectedAnalysisPlayer?.side_by_round[String(currentRound.round_num)]
      : undefined
  ) ?? selectedSnapshot?.side ?? "ct";
  const winRate = winRateForPerspective(
    currentWinProbability,
    selectedSide,
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

  const moveEventMarkerFocus = useCallback(
    (eventIndex: number, direction: "first" | "last" | "next" | "previous") => {
      if (timelineEvents.length === 0) return;

      const targetIndex =
        direction === "first"
          ? 0
          : direction === "last"
            ? timelineEvents.length - 1
            : direction === "next"
              ? Math.min(eventIndex + 1, timelineEvents.length - 1)
              : Math.max(eventIndex - 1, 0);
      const targetEvent = timelineEvents[targetIndex];
      seek(targetEvent.tick, targetEvent.event_id);
      requestAnimationFrame(() => eventMarkerRefs.current.get(targetEvent.event_id)?.focus());
    },
    [seek, timelineEvents],
  );

  const requestContextualAnalysis = useCallback((keyPointId: string, intent: string) => {
    if (!submitMomentIntent || !analysisId || !replay || !selectedPlayerId) return;

    intentControllers.current.get(keyPointId)?.abort();
    const controller = new AbortController();
    const requestId = ++intentRequestId.current;
    intentControllers.current.set(keyPointId, controller);
    dispatchIntent({ type: "SUBMIT", keyPointId, intent, requestId });

    submitMomentIntent({
      replayId: replay.replay_id,
      analysisId,
      playerId: selectedPlayerId,
      keyPointId,
      intent,
    }, controller.signal)
      .then((coaching) => {
        const normalizedCoaching = coaching.trim();
        if (!normalizedCoaching) {
          throw new Error("The contextual analysis response was empty.");
        }
        dispatchIntent({ type: "SUCCEED", keyPointId, coaching: normalizedCoaching, requestId });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        dispatchIntent({
          type: "FAIL",
          keyPointId,
          requestId,
          message: error instanceof Error
            ? error.message
            : "The new analysis could not be generated.",
        });
      })
      .finally(() => {
        if (intentControllers.current.get(keyPointId) === controller) {
          intentControllers.current.delete(keyPointId);
        }
      });
  }, [analysisId, replay, selectedPlayerId, submitMomentIntent]);

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
            <aside
              className={`analysis-inspector ${selectedEventKind}`}
              aria-labelledby="inspector-title"
            >
              <div className="inspector-heading">
                <p className="eyebrow">Moment inspector</p>
                <h2 id="inspector-title">
                  {eventLabel(selectedEvent, selectedEventAnalysis)}
                </h2>
              </div>
              <p className="inspector-summary">
                {selectedEventHasAnalysis && selectedEventAnalysis?.selected_decision.role === "attacker"
                  ? `${namesById.get(selectedEvent.attacker_id ?? "") ?? "The selected player"} dealt ${selectedEvent.damage_health ?? "unknown"} damage to ${namesById.get(selectedEvent.victim_id ?? "") ?? "an opponent"}.`
                  : replayEventIsDeath(selectedEvent)
                  ? `${namesById.get(selectedEvent.victim_id ?? "") ?? "The selected player"} was eliminated by ${namesById.get(selectedEvent.attacker_id ?? "") ?? "an opponent"}.`
                  : `${namesById.get(selectedEvent.victim_id ?? "") ?? "The selected player"} took ${selectedEvent.damage_health ?? "unknown"} damage from ${namesById.get(selectedEvent.attacker_id ?? "") ?? "an opponent"}.`}
              </p>
              <dl className="inspector-facts">
                <div><dt>Round</dt><dd>{selectedEvent.round_num}</dd></div>
                <div><dt>Replay time</dt><dd>{formatReplayTime(selectedEvent.tick, firstTick, replay.map.tick_rate)}</dd></div>
                <div><dt>Tick</dt><dd>{selectedEvent.tick}</dd></div>
                <div><dt>Weapon</dt><dd>{selectedEvent.weapon?.replaceAll("_", " ") ?? "—"}</dd></div>
              </dl>
              {selectedEventHasAnalysis && selectedEventAnalysis ? (
                <section
                  className={`saved-coaching${selectedIntentState?.status === "generating" ? " loading-border" : ""}`}
                  aria-labelledby="saved-coaching-title"
                  aria-busy={selectedIntentState?.status === "generating"}
                >
                  <p className="eyebrow">Coaching</p>
                  <h3 id="saved-coaching-title">What could be done better</h3>
                  <p>
                    {selectedIntentState?.status === "complete"
                      ? selectedIntentState.coaching
                      : selectedEventAnalysis.coach_analysis.what_could_be_done_better}
                  </p>
                  {selectedIntentState?.status === "generating" ? (
                    <p className="coaching-generation-status" role="status">
                      Generating new analysis...
                    </p>
                  ) : null}
                </section>
              ) : null}
              {selectedEventHasAnalysis && selectedEvent && selectedEventAnalysis ? (
                <section className="moment-intent" aria-labelledby="moment-intent-title">
                  <p id="moment-intent-title">
                    Want to add more context for your analysis? Send us your intent at this moment.
                  </p>
                  {selectedIntentState ? (
                    <div className="submitted-intent">
                      <p className="eyebrow">Your intent</p>
                      <blockquote>{selectedIntentState.intent}</blockquote>
                    </div>
                  ) : null}
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      const intent = selectedIntentDraft.trim();
                      if (!intent || selectedIntentState || !submitMomentIntent || !analysisId) return;
                      requestContextualAnalysis(selectedEvent.event_id, intent);
                    }}
                  >
                    <label className="sr-only" htmlFor={`moment-intent-${selectedEvent.event_id}`}>
                      Your intent at this moment
                    </label>
                    <textarea
                      id={`moment-intent-${selectedEvent.event_id}`}
                      value={selectedIntentState ? "" : selectedIntentDraft}
                      placeholder={selectedIntentState ? "Intent sent" : "What were you trying to do?"}
                      disabled={Boolean(selectedIntentState) || !submitMomentIntent || !analysisId}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setIntentDrafts((current) => ({
                          ...current,
                          [selectedEvent.event_id]: value,
                        }));
                      }}
                    />
                    <button
                      type="submit"
                      disabled={
                        Boolean(selectedIntentState) ||
                        !selectedIntentDraft.trim() ||
                        !submitMomentIntent ||
                        !analysisId
                      }
                    >
                      Send
                    </button>
                  </form>
                  {!submitMomentIntent || !analysisId ? (
                    <p className="moment-intent-unavailable">
                      Intent follow-up will be enabled when backend support is connected.
                    </p>
                  ) : null}
                  {selectedIntentState?.status === "error" ? (
                    <div className="moment-intent-error" role="alert">
                      <p>{selectedIntentState.message}</p>
                      <button
                        type="button"
                        onClick={() => requestContextualAnalysis(
                          selectedEvent.event_id,
                          selectedIntentState.intent,
                        )}
                      >
                        Try analysis again
                      </button>
                    </div>
                  ) : null}
                </section>
              ) : null}

              <section className="intent-coaching-section" aria-label="In-depth intent analysis">
                <p className="eyebrow">Action Intent & Context</p>
                <h3 id="intent-section-title">What were you trying to achieve?</h3>
                <div className="intent-input-container">
                  <textarea
                    value={intentInputText}
                    onChange={(event) => setIntentInputText(event.target.value)}
                    placeholder='e.g. "I expected my teammate to swing with me from Banana."'
                    maxLength={240}
                    rows={2}
                    disabled={intentLoading}
                  />
                  <button
                    type="button"
                    className="primary intent-submit-button"
                    onClick={handleIntentSubmit}
                    disabled={!intentInputText.trim() || intentLoading}
                  >
                    {intentLoading ? "Analyzing Intent..." : "Get In-Depth Analysis"}
                  </button>
                </div>
                {intentError ? <p className="intent-error-text">{intentError}</p> : null}
                {intentResponse ? (
                  <div className="intent-response-card">
                    <h4>In-Depth CS2 Tactical Breakdown</h4>
                    <p><strong>Feasibility:</strong> {intentResponse.intent_feasibility}</p>
                    <p><strong>Coordination Gap:</strong> {intentResponse.coordination_gap}</p>
                    <p><strong>Adjustment:</strong> {intentResponse.recommended_cs2_adjustment}</p>
                    <p className="intent-explanation-body">{intentResponse.in_depth_coaching}</p>
                  </div>
                ) : null}
              </section>
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
            <div className="radar-indicators">
              <section className={`selected-player-health ${selectedHealthLevel}`} aria-label="Player health">
                <div className="selected-player-health-label">
                  <span>Health</span>
                  <strong>{selectedHealth === undefined ? "—" : `${Math.round(selectedHealth)} HP`}</strong>
                </div>
                <div
                  className="selected-player-health-track"
                  role="progressbar"
                  aria-label={`${selectedPlayer ? playerDisplayName(selectedPlayer) : "Selected player"} health`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={selectedHealth === undefined ? undefined : Math.round(selectedHealth)}
                  aria-valuetext={selectedHealth === undefined ? "Health unavailable" : `${Math.round(selectedHealth)} health`}
                >
                  <span style={{ width: selectedHealth === undefined ? "0%" : `${selectedHealth}%` }} />
                </div>
              </section>
              <section
                className={`radar-win-rate${winRate.isBaseline ? " baseline" : ""}`}
                aria-label="Win rate"
              >
                <div className="radar-win-rate-values">
                  <strong className="friendly-team">
                    <span>{winRate.friendlyTeam}</span>
                    {formatProbability(winRate.friendlyProbability)}
                  </strong>
                  <p>Win rate</p>
                  <strong className="enemy-team">
                    {formatProbability(winRate.enemyProbability)}
                    <span>{winRate.enemyTeam}</span>
                  </strong>
                </div>
                <div
                  className="win-rate-track"
                  role="img"
                  aria-label={`${winRate.friendlyTeam} ${formatProbability(winRate.friendlyProbability)}, ${winRate.enemyTeam} ${formatProbability(winRate.enemyProbability)}${winRate.isBaseline ? ", baseline estimate" : ""}`}
                >
                  <span
                    className="win-rate-friendly"
                    style={{ width: formatProbability(winRate.friendlyProbability) }}
                  />
                  <span
                    className="win-rate-enemy"
                    style={{ width: formatProbability(winRate.enemyProbability) }}
                  />
                </div>
              </section>
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
              {timelineEvents.map((event, eventIndex) => (
                <button
                  type="button"
                  className={`${event.event === "kill" ? "death" : analysisEventIds.has(event.event_id) ? "coaching" : replayEventIsDeath(event) ? "death" : "damage"}${selectedEventId === event.event_id ? " selected" : ""}`}
                  style={{ left: `${((event.tick - firstTick) / duration) * 100}%` }}
                  key={event.event_id}
                  ref={(element) => {
                    if (element) {
                      eventMarkerRefs.current.set(event.event_id, element);
                    } else {
                      eventMarkerRefs.current.delete(event.event_id);
                    }
                  }}
                  tabIndex={
                    selectedEventId === event.event_id ||
                    (!selectedEventId && eventIndex === 0)
                      ? 0
                      : -1
                  }
                  title={`Round ${event.round_num}: ${eventLabel(event, analysisByEventId.get(event.event_id))}${analysisEventIds.has(event.event_id) ? " · Saved analysis" : ""}`}
                  aria-label={`Round ${event.round_num}, ${eventLabel(event, analysisByEventId.get(event.event_id))}, ${formatReplayTime(event.tick, firstTick, replay.map.tick_rate)}${analysisEventIds.has(event.event_id) ? ", saved analysis" : ""}`}
                  onClick={(clickEvent) => {
                    clickEvent.currentTarget.blur();
                    seek(event.tick, event.event_id);
                  }}
                  onKeyDown={(keyEvent) => {
                    const direction =
                      keyEvent.key === "ArrowRight"
                        ? "next"
                        : keyEvent.key === "ArrowLeft"
                          ? "previous"
                          : keyEvent.key === "Home"
                            ? "first"
                            : keyEvent.key === "End"
                              ? "last"
                              : undefined;
                    if (direction) {
                      keyEvent.preventDefault();
                      moveEventMarkerFocus(eventIndex, direction);
                    }
                  }}
                />
              ))}
            </div>
          </div>
          <div className="timeline-caption">
            <span><i className="damage" />Damage</span>
            <span><i className="death" />Death</span>
            {analysedEvents.length > 0 ? <span><i className="coaching" />Analysis</span> : null}
            <span>Tick {Math.round(currentTick)}</span>
          </div>
        </section>
      </section>
    </main>
  );
}
