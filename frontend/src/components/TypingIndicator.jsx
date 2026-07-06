import { C } from "../fm/theme.js";

const LOAD_MESSAGES = {
  waking: "Waking up backend…",
  waking_slow: "Still waking up — Render free tier can take ~30 seconds",
  predict: "Running prediction model…",
  compare: "Comparing teams…",
  standings: "Fetching standings…",
  llm: "Searching squad data…",
  thinking: "Thinking…",
  still_thinking: "Still working on it…",
};

export function guessLoadPhase(text, backendStatus) {
  if (backendStatus === "connecting" || backendStatus === "unreachable") return "waking";
  const low = text.toLowerCase();
  if (/\b(predict|forecast)\b/.test(low) || /\bvs\.?\b|\bversus\b/.test(low)) return "predict";
  if (/\bcompare\b|\bwho('s| is) better\b/.test(low)) return "compare";
  if (/\btable\b|\bstanding\b/.test(low)) return "standings";
  if (/\b(squad|scorer|player|lineup|formation)\b/.test(low)) return "llm";
  return "thinking";
}

export default function TypingIndicator({ phase }) {
  const msg = LOAD_MESSAGES[phase] || LOAD_MESSAGES.thinking;
  return (
    <div className="flex justify-start">
      <div className="rounded-xl px-3.5 py-2.5 text-sm" style={{ background: C.panel, color: C.mute }}>
        <div className="flex items-center gap-2.5">
          <span className="flex items-center gap-1" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="fm-typing-dot inline-block h-1.5 w-1.5 rounded-full"
                style={{ background: C.home, animationDelay: `${i * 0.18}s` }}
              />
            ))}
          </span>
          <span className="text-xs leading-snug">{msg}</span>
        </div>
      </div>
    </div>
  );
}
