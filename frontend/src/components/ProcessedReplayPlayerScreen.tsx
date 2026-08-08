import { mapDisplayName } from "@/domain/maps";
import type { ProcessedReplaySummary } from "@/domain/processed-replays";
import { playerDisplayName, type ProcessedReplay, type ReplayPlayer } from "@/domain/replay-viewer";

type ProcessedReplayPlayerScreenProps = {
  status: "loading" | "ready" | "error";
  summary: ProcessedReplaySummary;
  replay?: ProcessedReplay;
  message?: string;
  onBack: () => void;
  onRetry: () => void;
  onSelectPlayer: (player: ReplayPlayer) => void;
};

export function ProcessedReplayPlayerScreen({
  status,
  summary,
  replay,
  message,
  onBack,
  onRetry,
  onSelectPlayer,
}: ProcessedReplayPlayerScreenProps) {
  const mapName = mapDisplayName(summary.map);

  return (
    <section className="replay-screen" id="main-content" aria-labelledby="replay-title">
      <div className="replay-panel">
        <div className="replay-title-row">
          <div>
            <p className="kicker">{summary.displayName}</p>
            <h1 id="replay-title" tabIndex={-1}>
              Choose your <span className="accent-word">player.</span>
            </h1>
          </div>
          <button className="secondary" type="button" onClick={onBack}>
            Back to replays
          </button>
        </div>

        {status === "loading" ? (
          <div className="replay-progress-card loading-border" aria-busy="true">
            <div>
              <h2>Loading replay players</h2>
              <p>Preparing the saved player perspectives for {mapName}.</p>
            </div>
            <p className="sr-only" aria-live="polite">
              Loading the processed replay player list.
            </p>
          </div>
        ) : null}

        {status === "error" ? (
          <div className="replay-error-card" role="alert">
            <p>{message ?? "The processed replay could not be loaded."}</p>
            <div className="replay-inline-actions">
              <button className="primary" type="button" onClick={onRetry}>
                Try again
              </button>
              <button className="secondary" type="button" onClick={onBack}>
                Back to replays
              </button>
            </div>
          </div>
        ) : null}

        {status === "ready" && replay ? (
          <>
            <dl className="replay-summary" aria-label="Processed replay summary">
              <div>
                <dt>Replay</dt>
                <dd>{summary.displayName}</dd>
              </div>
              <div>
                <dt>Map</dt>
                <dd>{mapName}</dd>
              </div>
              <div>
                <dt>Rounds</dt>
                <dd>{replay.rounds.length}</dd>
              </div>
              <div>
                <dt>Analysis</dt>
                <dd>{summary.analysisAvailable ? "Included" : "Not included"}</dd>
              </div>
            </dl>
            <div className="replay-player-section">
              <div className="replay-section-copy">
                <h2>Whose perspective should we show?</h2>
                <p>
                  Your selected player stays blue. Teammates are green and opponents are red.
                </p>
              </div>
              <ul className="replay-player-list" aria-label="Players available in the processed replay">
                {replay.players.map((player) => (
                  <li key={player.player_id}>
                    <button
                      className="replay-player-button"
                      type="button"
                      onClick={() => onSelectPlayer(player)}
                    >
                      <span>
                        <strong>{playerDisplayName(player)}</strong>
                        <small>
                          {player.sides.map((side) => side.toUpperCase()).join(" / ")}
                          {summary.analysisAvailable ? " · Saved analysis" : " · Replay only"}
                        </small>
                      </span>
                      <span className="replay-player-action">
                        {summary.analysisAvailable ? "Open analysis" : "Open perspective"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
