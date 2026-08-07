type LandingScreenProps = {
  onOpenSamples: () => void;
  onOpenShowcase: () => void;
  onSelectReplay: (file: File) => void;
};

export function LandingScreen({
  onOpenSamples,
  onOpenShowcase,
  onSelectReplay,
}: LandingScreenProps) {
  return (
    <section className="hero" id="main-content" aria-labelledby="page-title">
      <div className="hero-copy">
        <p className="kicker">One moment. One choice. Better next time.</p>
        <h1 id="page-title" tabIndex={-1}>
          Don&apos;t replay the match.
          <span> Replay the decision.</span>
        </h1>
        <p className="lede">
          We judge the choice using only what was knowable at that moment.
          <br />
          Not whether you later won, died, or lost the round.
        </p>

        <div className="actions" aria-label="Choose an analysis source">
          <label
            className="primary"
            htmlFor="demo-upload"
            aria-describedby="upload-help"
          >
            Upload a *.dem
          </label>
          <input
            id="demo-upload"
            type="file"
            accept=".dem"
            onChange={(event) => {
              const selectedFile = event.currentTarget.files?.[0];
              if (selectedFile) {
                onSelectReplay(selectedFile);
              }
            }}
          />
          <button
            className="secondary"
            type="button"
            onClick={onOpenSamples}
            aria-describedby="sample-note"
          >
            Use a sample match
          </button>
          <button
            className="secondary"
            type="button"
            onClick={onOpenShowcase}
            aria-describedby="showcase-note"
          >
            Open processed replays
          </button>
        </div>
        <div className="action-notes">
          <p className="action-note action-note-accent" id="upload-help">
            Upload your match and view its analysis.
          </p>
          <p className="action-note action-note-steel" id="sample-note">
            Choose from the sample matches currently available from the backend.
          </p>
          <p className="action-note action-note-steel" id="showcase-note">
            Choose an already-processed replay and go straight to its analysis.
          </p>
        </div>
      </div>

      <aside className="boundary-card" aria-labelledby="boundary-title">
        <p className="eyebrow">The knowledge boundary</p>
        <h2 id="boundary-title">Judge the moment, not the outcome.</h2>
        <ol className="boundary-preview">
          <li>
            <strong>Known</strong>
            <span>Replay facts before the choice</span>
          </li>
          <li>
            <strong>Decision</strong>
            <span>The moment an option opened</span>
          </li>
          <li>
            <strong>Action</strong>
            <span>The immediate response</span>
          </li>
          <li className="hidden-future">
            <strong>Hidden</strong>
            <span>Everything after is hidden from the coach</span>
          </li>
        </ol>
      </aside>
    </section>
  );
}
