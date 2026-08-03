export default function Home() {
  return (
    <main className="shell">
      <nav className="topbar" aria-label="Product">
        <a className="brand" href="#main-content" aria-label="RE:DECIDE home">
          <span aria-hidden="true">RE:</span>DECIDE
          <svg
            className="brand-outline"
            viewBox="0 0 100 40"
            preserveAspectRatio="none"
            aria-hidden="true"
            focusable="false"
          >
            <rect x="0.75" y="0.75" width="98.5" height="38.5" pathLength="100" />
          </svg>
        </a>
        <span className="eyebrow">Outcome-blind decision coaching</span>
      </nav>

      <section className="hero" id="main-content" aria-labelledby="page-title">
        <div className="hero-copy">
          <p className="kicker">One moment. One choice. Better next time.</p>
          <h1 id="page-title">
            Don&apos;t replay the match.
            <span> Replay the decision.</span>
          </h1>
          <p className="lede">
            We judge the choice using only what was knowable at that moment.
            <br></br>
            Not whether you later won, died, or lost the round.
          </p>

          <div className="actions" aria-label="Choose an analysis source">
            <button className="primary" type="button" disabled aria-describedby="setup-note">
              Try a sample match
            </button>
            <label className="secondary" htmlFor="demo-upload" aria-describedby="upload-help setup-note">
              Upload a *.dem
            </label>
            <input id="demo-upload" type="file" accept=".dem" disabled />
          </div>
          <p className="privacy" id="upload-help">
            Replay data is sent to the configured analysis service.
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
    </main>
  );
}
