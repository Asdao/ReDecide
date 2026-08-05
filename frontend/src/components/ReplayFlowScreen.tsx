import type { ReplayAnalysisFlowState } from "@/domain/analysis-flow";
import type { AnalysisPlayer } from "@/domain/replay";

type ReplayFlowScreenProps = {
  state: ReplayAnalysisFlowState;
  onBack: () => void;
  onRetryUpload: () => void;
  onRetryPrepare: () => void;
  onRetryPlayers: () => void;
  onSelectPlayer: (playerId: string) => void;
  onRetryCoaching: () => void;
  onRetryRecovery: () => void;
};

function playerName(player: AnalysisPlayer): string {
  return player.display_name ?? "Unnamed player";
}

function playerSides(player: AnalysisPlayer): string {
  const sides = [...new Set(Object.values(player.side_by_round))].map((side) =>
    side.toUpperCase(),
  );
  return sides.length > 0 ? sides.join(" / ") : "Side unavailable";
}

function replayProgressMessage(state: ReplayAnalysisFlowState): string {
  switch (state.status) {
    case "uploading":
      return `Uploading ${state.file.name}.`;
    case "preparing-analysis":
      return "The replay was uploaded. Preparing player and decision data.";
    case "waiting-for-players":
      return "Waiting for the backend to finish preparing the player list.";
    case "running-coaching":
      return `Generating coaching for ${playerName(state.selectedPlayer)}.`;
    case "recovering-result":
      return "Checking whether coaching completed without starting another coaching request.";
    case "choosing-player":
      return "Player selection is ready.";
    case "result":
      return `Coaching for ${playerName(state.selectedPlayer)} is ready.`;
    case "upload-error":
    case "analysis-prepare-error":
    case "players-error":
    case "coaching-error":
    case "result-recovery-error":
      return "";
  }
}

function ReplaySummary({ state }: { state: Exclude<ReplayAnalysisFlowState, { status: "uploading" | "upload-error" }> }) {
  return (
    <dl className="replay-summary" aria-label="Uploaded replay summary">
      <div>
        <dt>File</dt>
        <dd>{state.file.name}</dd>
      </div>
      <div>
        <dt>Map</dt>
        <dd>{state.manifest.map.name}</dd>
      </div>
      <div>
        <dt>Rounds</dt>
        <dd>{state.manifest.rounds.length}</dd>
      </div>
      <div>
        <dt>Players found</dt>
        <dd>{state.manifest.players.length}</dd>
      </div>
    </dl>
  );
}

function ProgressPanel({ title, copy }: { title: string; copy: string }) {
  return (
    <div className="replay-progress-card" aria-busy="true">
      <span className="replay-progress-marker" aria-hidden="true" />
      <div>
        <h2>{title}</h2>
        <p>{copy}</p>
      </div>
    </div>
  );
}

function ErrorPanel({
  message,
  retryable,
  retryLabel,
  onRetry,
  onBack,
}: {
  message: string;
  retryable: boolean;
  retryLabel: string;
  onRetry: () => void;
  onBack: () => void;
}) {
  return (
    <div className="replay-error-card" role="alert">
      <p>{message}</p>
      <div className="replay-inline-actions">
        {retryable ? (
          <button className="primary" type="button" onClick={onRetry}>
            {retryLabel}
          </button>
        ) : null}
        <button className="secondary" type="button" onClick={onBack}>
          Choose another replay
        </button>
      </div>
    </div>
  );
}

export function ReplayFlowScreen({
  state,
  onBack,
  onRetryUpload,
  onRetryPrepare,
  onRetryPlayers,
  onSelectPlayer,
  onRetryCoaching,
  onRetryRecovery,
}: ReplayFlowScreenProps) {
  const heading =
    state.status === "choosing-player"
      ? "Choose your player."
      : state.status === "result"
        ? "Replay the decision."
        : "Preparing your replay.";

  return (
    <section className="replay-screen" id="main-content" aria-labelledby="replay-title">
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {replayProgressMessage(state)}
      </p>
      <div className="replay-panel">
        <div className="replay-title-row">
          <div>
            <p className="kicker">Uploaded replay</p>
            <h1 id="replay-title" tabIndex={-1}>
              {heading}
            </h1>
          </div>
          <button className="secondary" type="button" onClick={onBack}>
            Back to start
          </button>
        </div>

        {state.status !== "uploading" && state.status !== "upload-error" ? (
          <ReplaySummary state={state} />
        ) : null}

        {state.status === "uploading" ? (
          <ProgressPanel
            title={`Uploading ${state.file.name}`}
            copy="Keep this page open while the backend parses the demo. The file is uploaded once."
          />
        ) : null}

        {state.status === "preparing-analysis" ? (
          <ProgressPanel
            title="Preparing the analysis"
            copy="Player identities and decision moments are being indexed from the uploaded replay."
          />
        ) : null}

        {state.status === "waiting-for-players" ? (
          <ProgressPanel
            title="Finding selectable players"
            copy="This list comes from the analysis service and may take a little while to become available."
          />
        ) : null}

        {state.status === "running-coaching" ? (
          <ProgressPanel
            title={`Coaching ${playerName(state.selectedPlayer)}`}
            copy="The coaching request can take around 30 seconds. The replay will not be uploaded again."
          />
        ) : null}

        {state.status === "recovering-result" ? (
          <ProgressPanel
            title="Checking for completed coaching"
            copy="The request ended before a response arrived. We are checking the saved result without starting another model call."
          />
        ) : null}

        {state.status === "upload-error" ? (
          <ErrorPanel
            message={state.error.message}
            retryable={state.error.retryable}
            retryLabel="Retry upload"
            onRetry={onRetryUpload}
            onBack={onBack}
          />
        ) : null}

        {state.status === "analysis-prepare-error" ? (
          <ErrorPanel
            message={state.error.message}
            retryable={state.error.retryable}
            retryLabel="Retry preparation"
            onRetry={onRetryPrepare}
            onBack={onBack}
          />
        ) : null}

        {state.status === "players-error" ? (
          <ErrorPanel
            message={state.error.message}
            retryable={state.error.retryable}
            retryLabel="Check players again"
            onRetry={onRetryPlayers}
            onBack={onBack}
          />
        ) : null}

        {state.status === "coaching-error" ? (
          <ErrorPanel
            message={state.error.message}
            retryable={state.error.retryable}
            retryLabel="Retry coaching"
            onRetry={onRetryCoaching}
            onBack={onBack}
          />
        ) : null}

        {state.status === "result-recovery-error" ? (
          <ErrorPanel
            message={state.error.message}
            retryable={state.error.retryable}
            retryLabel="Check result again"
            onRetry={onRetryRecovery}
            onBack={onBack}
          />
        ) : null}

        {state.status === "choosing-player" ? (
          <div className="replay-player-section">
            <div className="replay-section-copy">
              <h2>Whose perspective should we analyse?</h2>
            </div>
            <ul className="replay-player-list" aria-label="Players available for coaching">
              {state.players.map((player) => {
                const unavailable = player.decision_ids.length === 0;
                return (
                  <li key={player.player_id}>
                    <button
                      className="replay-player-button"
                      type="button"
                      disabled={unavailable}
                      onClick={() => onSelectPlayer(player.player_id)}
                    >
                      <span>
                        <strong>{playerName(player)}</strong>
                        <small>
                          {playerSides(player)} · {player.rounds.length}{" "}
                          {player.rounds.length === 1 ? "round" : "rounds"}
                        </small>
                      </span>
                      <span className="replay-player-action">
                        {unavailable ? "No coaching moment" : "Analyze player"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}

        {state.status === "result" ? (
          <article className="coaching-result" aria-labelledby="coaching-result-title">
            <div className="coaching-result-heading">
              <p className="eyebrow">Coaching complete</p>
              <h2 id="coaching-result-title">
                {playerName(state.selectedPlayer)} · Round {state.result.selected_decision.round_number}
              </h2>
              <p>
                {state.result.selected_decision.event_category} decision at tick{" "}
                {state.result.selected_decision.decision_open_tick}
              </p>
            </div>
            <div className="coaching-advice">
              <p className="eyebrow">What could be done better</p>
              <p>{state.result.coach_analysis.what_could_be_done_better}</p>
            </div>
            <dl className="decision-details">
              <div>
                <dt>Observed action</dt>
                <dd>{state.result.selected_decision.observed_action.replaceAll("_", " ")}</dd>
              </div>
              <div>
                <dt>Role</dt>
                <dd>{state.result.selected_decision.role}</dd>
              </div>
              <div>
                <dt>Side</dt>
                <dd>{state.result.selected_decision.side.toUpperCase()}</dd>
              </div>
            </dl>
          </article>
        ) : null}
      </div>
    </section>
  );
}
