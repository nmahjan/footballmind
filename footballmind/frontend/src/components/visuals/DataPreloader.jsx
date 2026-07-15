import { C } from "../../fm/theme.js";

export default function DataPreloader({
  loading,
  loadingText = "Loading match intelligence",
  position = "fixed",
  zIndex = 40,
}) {
  if (!loading) return null;
  return (
    <div
      className={`data-preloader data-preloader-${position}`}
      role="status"
      aria-live="polite"
      aria-label={loadingText}
      style={{ zIndex, "--preloader-bg": C.bg, "--preloader-accent": C.home }}>
      <div className="data-preloader-panel">
        <div className="data-preloader-mark" aria-hidden="true">
          {Array.from({ length: 8 }).map((_, i) => (
            <span key={i} style={{ "--i": i }} />
          ))}
        </div>
        <div>
          <div className="data-preloader-title">Football Mind</div>
          <div className="data-preloader-copy">{loadingText}</div>
        </div>
      </div>
      <div className="data-preloader-progress" aria-hidden="true" />
    </div>
  );
}
