type LandingScreenProps = {
  onOpenExample: () => void;
};

export function LandingScreen({ onOpenExample }: LandingScreenProps) {
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
          <button className="primary" type="button" onClick={onOpenExample} aria-describedby="demo-note">
            Try a sample match
          </button>
          <label className="secondary" htmlFor="demo-upload" aria-describedby="upload-help">
            Upload a *.dem
          </label>
          <input id="demo-upload" type="file" accept=".dem" disabled />
        </div>
        <p className="source-note" id="demo-note">
          Opens a saved demo example. It is not a new backend analysis.
        </p>
        <p className="privacy" id="upload-help">
          Replay upload will be enabled after the analysis service is connected.
        </p>
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
