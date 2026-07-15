import { useRef, useEffect } from "react";
import { BracketTree, normaliseBracket } from "./BracketPanel.jsx";
import PredictionCard from "./PredictionCard.jsx";
import MarkdownBody from "./MarkdownBody.jsx";
import TypingIndicator from "./TypingIndicator.jsx";
import { C } from "../fm/theme.js";
import { COMP_LABELS } from "../fm/demo.js";

const CHIPS = [
  "Predict Netherlands vs Morocco",
  "Show World Cup knockout bracket",
  "Predict Spain vs Germany",
  "Predict Brazil vs Argentina",
];

const PLAYER_CHIPS = [
  "Who is top scorer in the Premier League?",
  "Tell me about Brazil's squad and how they play",
  "What formation does Manchester City use?",
  "Who are Spain's key midfielders?",
];

export default function ChatPanel({
  messages,
  busy,
  loadPhase,
  input,
  setInput,
  send,
  startNewChat,
  sidebarMode,
  venueMode,
  setVenueMode,
  chatComp,
  apiBase,
  stretchHeight,
}) {
  const scroller = useRef(null);
  const showChips = messages.length === 0;
  const chips = sidebarMode === "players" ? PLAYER_CHIPS : CHIPS;

  useEffect(() => {
    scroller.current?.scrollTo(0, scroller.current.scrollHeight);
  }, [messages, busy, loadPhase]);

  const stretched = stretchHeight != null && stretchHeight > 0;
  const panelHeight = stretched ? Math.max(stretchHeight, 560) : null;
  const mobilePanelHeight = "min(760px, calc(100svh - 8.25rem))";

  return (
    <section
      className="flex w-full shrink-0 flex-col rounded-lg border md:min-h-0"
      style={{
        borderColor: C.line,
        background: C.panel2,
        boxShadow: "0 18px 60px rgba(0,0,0,0.18)",
        ...(stretched ? {
          minHeight: panelHeight,
          height: panelHeight,
          maxHeight: panelHeight,
        } : {
          minHeight: mobilePanelHeight,
        }),
      }}>
      <div className="flex items-center justify-between border-b px-4 py-2.5" style={{ borderColor: C.line }}>
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em]" style={{ color: C.mute }}>Command Chat</span>
        <button
          type="button"
          onClick={startNewChat}
          disabled={busy}
          title="Start a fresh conversation"
          className="rounded border px-2.5 py-1 text-[10px] font-semibold transition-opacity hover:opacity-80 disabled:opacity-40"
          style={{ borderColor: C.line, color: C.chalk, background: C.elevated }}>
          New chat
        </button>
      </div>

      <div
        ref={scroller}
        className={`min-h-0 flex-1 space-y-4 overflow-y-auto p-4 ${messages.length === 0 ? "flex flex-col justify-center" : ""}`}
        style={stretched ? undefined : { maxHeight: "min(720px, 72svh)" }}>
        {messages.length === 0 && (
          <div className={`text-center ${stretched ? "" : "mt-6"}`}>
            <div className="text-sm" style={{ color: C.chalk }}>
              {sidebarMode === "players"
                ? "Ask about players, squads, or why a team works."
                : "Ask anything about a match."}
            </div>
            <div className="mt-1 text-xs" style={{ color: C.mute }}>
              {sidebarMode === "players"
                ? "Switch to Players on the right, tap a name, or type a question below."
                : "Tap a fixture on the right, or browse standings below."}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <div className="max-w-[85%]">
              <div className="rounded-lg border px-3.5 py-2 text-sm"
                style={{
                  borderColor: m.role === "user" ? "transparent" : C.lineSoft,
                  background: m.role === "user" ? C.home : C.panel,
                  color: m.role === "user" ? "#003919" : C.chalk,
                }}>
                {m.role === "user" ? m.text : <MarkdownBody text={m.text} />}
              </div>
              {m.prediction && m.teams && (
                <PredictionCard
                  p={m.prediction}
                  home={m.teams.home}
                  away={m.teams.away}
                  comp={m.comp ?? chatComp}
                  neutral={m.neutral ?? null}
                  apiBase={apiBase}
                />
              )}
              {m.bracket && (
                <div className="mt-2 w-full min-w-0 max-w-full overflow-hidden rounded-lg border p-1"
                  style={{ borderColor: C.line, background: C.panel }}>
                  <BracketTree rounds={normaliseBracket(m.bracket)} />
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && loadPhase && <TypingIndicator phase={loadPhase} />}
      </div>

      {showChips && (
        <div className="flex flex-wrap gap-2 px-3 pt-2 pb-0">
          {chips.map((c) => (
            <button key={c} onClick={() => send(c)}
              className="rounded-md border px-3 py-1 text-[11px] font-medium transition-opacity hover:opacity-70"
              style={{ borderColor: C.line, color: C.chalk, background: C.elevated }}>
              {c}
            </button>
          ))}
        </div>
      )}

      <div className="border-t px-3 pt-2 pb-0" style={{ borderColor: C.line }}>
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-[10px] font-medium" style={{ color: C.mute }}>
            Context: <span style={{ color: C.chalk }}>{COMP_LABELS[chatComp] ?? chatComp}</span>
          </span>
          <span className="text-[10px] font-medium" style={{ color: C.mute }}>Venue:</span>
          {[
            [null,  "⚡ Auto",    "auto-detect based on teams"],
            [false, "🏠 Home",   "home team has advantage"],
            [true,  "🏟 Neutral","no home advantage"],
          ].map(([val, label, title]) => (
            <button key={String(val)} title={title}
              onClick={() => setVenueMode(val)}
              className="rounded px-2 py-0.5 text-[10px] font-semibold transition-colors"
              style={{
                background: venueMode === val ? (val === false ? C.warning : val === true ? C.home : C.elevated) : C.line,
                color: venueMode === val ? "#0D1117" : C.mute,
              }}>
              {label}
            </button>
          ))}
        </div>
        <div className="flex gap-2 pb-3">
          <input
            value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder={sidebarMode === "players"
              ? "Who are Brazil's key players?"
              : "Predict Mexico vs South Korea in Mexico"}
            className="flex-1 rounded-md px-3 py-2 text-sm outline-none transition-shadow focus:shadow-[0_0_0_2px_rgba(0,255,133,0.20)]"
            style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }} />
          <button onClick={() => send()} disabled={busy}
            className="rounded-md px-4 py-2 text-sm font-semibold disabled:opacity-50"
            style={{ background: C.home, color: "#003919" }}>Ask</button>
        </div>
      </div>
    </section>
  );
}
