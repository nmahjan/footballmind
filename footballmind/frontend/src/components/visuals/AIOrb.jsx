import { C } from "../../fm/theme.js";

export default function AIOrb({ size = 54, active = false, className = "", label = "" }) {
  return (
    <span
      className={`ai-orb ${active ? "ai-orb-active" : ""} ${className}`}
      aria-hidden="true"
      style={{
        "--ai-orb-size": `${size}px`,
        "--ai-orb-c1": C.home,
        "--ai-orb-c2": C.blue,
        "--ai-orb-c3": C.warning,
      }}>
      <span className="ai-orb-core" />
      <span className="ai-orb-ring" />
      {label ? <span className="ai-orb-label">{label}</span> : null}
    </span>
  );
}
