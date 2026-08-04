import type { DecisionPacket } from "@/domain/contracts";

type ProgressStatus = "loading" | "ready" | "error";

type AnalysisProgressScreenProps = {
  status: ProgressStatus;
  packet?: DecisionPacket;
  onBack: () => void;
  onRetry: () => void;
};

const stages = [
  "Parse replay events",
  "Find a post-contact decision",
  "Freeze what was knowable",
] as const;

function stageState(status: ProgressStatus, index: number) {
  if (status === "ready") {
    return { className: "complete", label: "Saved result" };
  }

  if (status === "error") {
    return index === 0
      ? { className: "failed", label: "Could not check" }
      : { className: "waiting", label: "Not started" };
  }

  return index === 0
    ? { className: "current", label: "Checking saved data" }
    : { className: "waiting", label: "Waiting" };
}

export function AnalysisProgressScreen({
  status,
  packet,
  onBack,
  onRetry,
}: AnalysisProgressScreenProps) {
  const isReady = status === "ready";
  const isError = status === "error";

  return (
    <section className="progress-screen" id="main-content" aria-labelledby="progress-title">
      <div className="progress-panel">
        <p className="kicker">Saved demo example</p>
        <h1 id="progress-title" tabIndex={-1}>
          {isError ? "We couldn't open the example." : isReady ? "The decision is ready." : "Preparing the decision."}
        </h1>

        {isError ? (
          <p className="progress-summary" role="alert">
            The saved example could not be checked. Try again or return to the start.
          </p>
        ) : (
          <p className="progress-summary">
            This is saved data, so these replay steps were completed when the example was prepared.
            The browser is only checking that saved result now.
          </p>
        )}

        <ol className="progress-list" aria-label="Analysis stages" aria-live="polite">
          {stages.map((stage, index) => {
            const stageStatus = stageState(status, index);
            return (
              <li className={stageStatus.className} key={stage}>
                <span className="progress-marker" aria-hidden="true" />
                <span className="progress-copy">
                  <strong>{stage}</strong>
                  <span>{stageStatus.label}</span>
                </span>
              </li>
            );
          })}
        </ol>

        {packet ? (
          <dl className="sample-details" aria-label="Saved example details">
            <div>
              <dt>Map</dt>
              <dd>{packet.map}</dd>
            </div>
            <div>
              <dt>Round</dt>
              <dd>{packet.round_number}</dd>
            </div>
            <div>
              <dt>Player</dt>
              <dd>{packet.player}</dd>
            </div>
          </dl>
        ) : null}

        {isReady ? (
          <p className="next-step-note">The intent question will be added in the next step.</p>
        ) : null}

        <div className="progress-actions">
          {isError ? (
            <button className="primary" type="button" onClick={onRetry}>
              Try again
            </button>
          ) : null}
          <button className="secondary" type="button" onClick={onBack}>
            Back to start
          </button>
        </div>
      </div>
    </section>
  );
}
