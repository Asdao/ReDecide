export function ProductHeader({
  brandHref = "#main-content",
  label = "Outcome-blind decision coaching",
}: {
  brandHref?: string;
  label?: string;
}) {
  return (
    <nav className="topbar" aria-label="Product">
      <a
        className="brand"
        href={brandHref}
        aria-label={brandHref === "#main-content" ? "Skip to main content" : "Back to RE:DECIDE home"}
      >
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
      <span className="eyebrow">{label}</span>
    </nav>
  );
}
