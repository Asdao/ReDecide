import type { ShowcasePlayer, ShowcaseReplay } from "@/domain/replay-viewer";
import { playerDisplayName } from "@/domain/replay-viewer";

type ShowcasePlayerScreenProps =
  | {
      status: "loading";
      onBack: () => void;
      onRetry: () => void;
      onSelectPlayer: (player: ShowcasePlayer) => void;
    }
  | {
      status: "error";
      message: string;
      onBack: () => void;
      onRetry: () => void;
      onSelectPlayer: (player: ShowcasePlayer) => void;
    }
  | {
      status: "ready";
      replay: ShowcaseReplay;
      onBack: () => void;
      onRetry: () => void;
      onSelectPlayer: (player: ShowcasePlayer) => void;
    };

export function ShowcasePlayerScreen(props: ShowcasePlayerScreenProps) {
  return (
    <section className="replay-screen" id="main-content" aria-labelledby="replay-title">
      <div className="replay-panel">
        <div className="replay-title-row">
          <div>
            <p className="kicker">Mirage showcase</p>
            <h1 id="replay-title" tabIndex={-1}>
              Choose your <span className="accent-word">player.</span>
            </h1>
          </div>
          <button className="secondary" type="button" onClick={props.onBack}>
            Back to start
          </button>
        </div>

        {props.status === "loading" ? (
          <div className="replay-progress-card loading-border" aria-busy="true">
            <div>
              <h2>Loading the processed replay</h2>
              <p>
                The showcase is already parsed, so no demo upload or backend analysis is needed.
              </p>
            </div>
            <p className="sr-only" aria-live="polite">
              Loading the Mirage showcase player list.
            </p>
          </div>
        ) : null}

        {props.status === "error" ? (
          <div className="replay-error-card" role="alert">
            <p>{props.message}</p>
            <div className="replay-inline-actions">
              <button className="primary" type="button" onClick={props.onRetry}>
                Try again
              </button>
              <button className="secondary" type="button" onClick={props.onBack}>
                Back to start
              </button>
            </div>
          </div>
        ) : null}

        {props.status === "ready" ? (
          <>
            <dl className="replay-summary" aria-label="Showcase replay summary">
              <div>
                <dt>Replay</dt>
                <dd>Mirage showcase</dd>
              </div>
              <div>
                <dt>Map</dt>
                <dd>Mirage</dd>
              </div>
              <div>
                <dt>Rounds</dt>
                <dd>{props.replay.rounds.length}</dd>
              </div>
              <div>
                <dt>Players found</dt>
                <dd>{props.replay.players.length}</dd>
              </div>
            </dl>
            <div className="replay-player-section">
              <div className="replay-section-copy">
                <h2>Whose perspective should we analyse?</h2>
                <p>
                  Your player stays blue on the radar. Teammates are green and opponents are red.
                </p>
              </div>
              <ul className="replay-player-list" aria-label="Players available in the showcase">
                {props.replay.players.map((player) => (
                  <li key={player.player_id}>
                    <button
                      className="replay-player-button"
                      type="button"
                      onClick={() => props.onSelectPlayer(player)}
                    >
                      <span>
                        <strong>{playerDisplayName(player)}</strong>
                        <small>{player.sides.map((side) => side.toUpperCase()).join(" / ")}</small>
                      </span>
                      <span className="replay-player-action">Open analysis</span>
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
