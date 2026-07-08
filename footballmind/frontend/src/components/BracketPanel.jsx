import { useState, useEffect, useRef } from "react";
import { C, Flag } from "../fm/theme.js";

function fmtBracketTime(iso) {
  if (!iso) return "TBD";
  const d = new Date(iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((target - today) / 86400000);
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  if (diff === 0) return `Today, ${time}`;
  if (diff === 1) return `Tomorrow, ${time}`;
  const date = d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  return `${date}, ${time}`;
}

const ROUND_LABEL = {
  round_of_32: "Round of 32", round_of_16: "Round of 16",
  quarter_final: "Quarter-finals", semi_final: "Semi-finals",
  final: "Final",
};
const BRACKET_ORDER = ["round_of_32", "round_of_16", "quarter_final", "semi_final", "final"];

const BRACKET_MATCH_H = 76;
const BRACKET_GAP = 10;
const BRACKET_HEADER_H = 28;
const BRACKET_CONNECTOR_W = 24;

function bracketMatchTop(roundIndex, matchIndex) {
  const stride = BRACKET_MATCH_H + BRACKET_GAP;
  return matchIndex * stride * (2 ** roundIndex)
    + ((2 ** roundIndex) - 1) * stride / 2;
}

function bracketMatchCenterY(roundIndex, matchIndex) {
  return BRACKET_HEADER_H + bracketMatchTop(roundIndex, matchIndex) + BRACKET_MATCH_H / 2;
}

function BracketTeamRow({ name, goals, winner }) {
  const tbd = !name || name === "TBD";
  return (
    <div className="flex items-center gap-2 px-2.5 py-1.5"
      style={{ background: winner ? "rgba(52,211,153,0.08)" : "transparent" }}>
      <span className="flex h-4 w-5 shrink-0 items-center justify-center text-[10px] rounded-sm"
        style={{ background: tbd ? C.line : "transparent" }}>
        {tbd ? "🛡" : <Flag name={name} className="h-3 w-4" />}
      </span>
      <span className="min-w-0 flex-1 truncate text-xs font-medium"
        style={{ color: tbd ? C.mute : C.chalk }}>
        {tbd ? "TBD" : name}
      </span>
      {goals != null && (
        <span className="shrink-0 text-xs font-bold tabular-nums" style={{ color: C.chalk }}>{goals}</span>
      )}
    </div>
  );
}

function BracketMatchCard({ f }) {
  const finished = f.home_goals != null && f.away_goals != null;
  const homeWin = finished && f.home_goals > f.away_goals;
  const awayWin = finished && f.away_goals > f.home_goals;
  return (
    <div className="w-[168px] shrink-0 overflow-hidden rounded-lg border"
      style={{ borderColor: C.line, background: C.panel2 }}>
      <div className="px-2.5 py-1 text-[10px] font-medium truncate" style={{ color: C.mute }}>
        {finished ? "Full time" : fmtBracketTime(f.match_date)}
      </div>
      <div style={{ borderTop: `1px solid ${C.line}` }}>
        <BracketTeamRow name={f.home} goals={finished ? f.home_goals : null} winner={homeWin} />
        <div style={{ borderTop: `1px solid ${C.line}` }} />
        <BracketTeamRow name={f.away} goals={finished ? f.away_goals : null} winner={awayWin} />
      </div>
    </div>
  );
}

function BracketConnectors({ prevRoundIndex, matchCount, colHeight }) {
  const lines = [];
  for (let mi = 0; mi < matchCount; mi++) {
    const yTop = bracketMatchCenterY(prevRoundIndex, 2 * mi);
    const yBot = bracketMatchCenterY(prevRoundIndex, 2 * mi + 1);
    const yMid = (yTop + yBot) / 2;
    lines.push(
      <div key={`vt-${mi}`} className="absolute pointer-events-none"
        style={{
          left: BRACKET_CONNECTOR_W / 2, top: yTop, width: 1,
          height: yBot - yTop, background: C.line,
        }} />,
      <div key={`ht-${mi}`} className="absolute pointer-events-none"
        style={{
          left: 0, top: yTop, width: BRACKET_CONNECTOR_W / 2, height: 1,
          background: C.line,
        }} />,
      <div key={`hb-${mi}`} className="absolute pointer-events-none"
        style={{
          left: 0, top: yBot, width: BRACKET_CONNECTOR_W / 2, height: 1,
          background: C.line,
        }} />,
      <div key={`hm-${mi}`} className="absolute pointer-events-none"
        style={{
          left: BRACKET_CONNECTOR_W / 2, top: yMid,
          width: BRACKET_CONNECTOR_W / 2, height: 1, background: C.line,
        }} />
    );
  }
  return (
    <div className="relative shrink-0" style={{ width: BRACKET_CONNECTOR_W, height: colHeight + BRACKET_HEADER_H }}>
      {lines}
    </div>
  );
}

export function normaliseBracket(data) {
  if (Array.isArray(data)) {
    const byRound = Object.fromEntries(data.map((r) => [r.round, r]));
    return BRACKET_ORDER
      .filter((k) => byRound[k]?.matches?.length)
      .map((k) => ({ round: k, matches: byRound[k].matches }));
  }
  const b = data || {};
  return BRACKET_ORDER.filter((k) => b[k]?.length).map((k) => ({ round: k, matches: b[k] }));
}

export function BracketTree({ rounds, scrollRef: externalRef }) {
  const internalRef = useRef(null);
  const scrollRef = externalRef || internalRef;
  const firstCount = rounds[0]?.matches?.length ?? 0;
  const colHeight = firstCount > 0
    ? firstCount * (BRACKET_MATCH_H + BRACKET_GAP) - BRACKET_GAP
    : 0;

  if (!rounds.length) {
    return (
      <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>
        No knockout matches yet — check back once the group stage finishes.
      </div>
    );
  }

  return (
    <div className="relative min-w-0 max-w-full px-2 pb-3 pt-1">
      <button type="button" aria-label="Scroll bracket left"
        onClick={() => scrollRef.current?.scrollBy({ left: -220, behavior: "smooth" })}
        className="absolute left-1 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border text-sm"
        style={{ borderColor: C.line, background: C.panel2, color: C.chalk }}>
        ‹
      </button>
      <button type="button" aria-label="Scroll bracket right"
        onClick={() => scrollRef.current?.scrollBy({ left: 220, behavior: "smooth" })}
        className="absolute right-1 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border text-sm"
        style={{ borderColor: C.line, background: C.panel2, color: C.chalk }}>
        ›
      </button>
      <div
        ref={scrollRef}
        className="max-w-full overflow-x-auto overflow-y-hidden overscroll-x-contain px-8 pb-1"
        style={{ scrollbarWidth: "thin", WebkitOverflowScrolling: "touch" }}>
        <div className="inline-flex min-w-max items-start gap-0">
          {rounds.map(({ round, matches }, ri) => (
            <div key={round} className="flex shrink-0 items-start">
              {ri > 0 && (
                <BracketConnectors
                  prevRoundIndex={ri - 1}
                  matchCount={matches.length}
                  colHeight={colHeight}
                />
              )}
              <div className="shrink-0 px-2">
                <div className="mb-2 flex items-end justify-center text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: C.mute, height: BRACKET_HEADER_H }}>
                  {ROUND_LABEL[round] ?? round}
                </div>
                <div className="relative" style={{ height: colHeight, width: 168 }}>
                  {matches.map((f, mi) => (
                    <div key={mi} className="absolute left-0 right-0"
                      style={{ top: bracketMatchTop(ri, mi) }}>
                      <BracketMatchCard f={f} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function BracketPanel({ apiBase, offline, defaultComp = "WC" }) {
  const [bracket, setBracket] = useState(null);
  const [open, setOpen] = useState(true);
  const [comp, setComp] = useState(defaultComp);
  const scrollRef = useRef(null);

  function load(c) {
    if (!apiBase || offline) return;
    fetch(`${apiBase}/api/bracket?comp=${c}`)
      .then((r) => r.json())
      .then((d) => setBracket(normaliseBracket(d.bracket)))
      .catch(() => setBracket([]));
  }

  useEffect(() => {
    setComp(defaultComp);
  }, [defaultComp]);

  useEffect(() => {
    if (open && apiBase && !offline) load(comp);
  }, [open, apiBase, offline, comp]);

  const rounds = bracket ?? [];

  return (
    <div className="min-w-0 overflow-hidden rounded-xl border" style={{ borderColor: C.line, background: C.panel }}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left transition-opacity hover:opacity-70"
        style={{ borderBottom: open ? `1px solid ${C.line}` : "none" }}>
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          🏆 Tournament Bracket
        </span>
        <span className="text-xs" style={{ color: C.mute }}>{open ? "hide ▴" : "show ▾"}</span>
      </button>

      {open && (
        <div className="min-w-0 overflow-hidden">
          <div className="flex gap-1 overflow-x-auto px-3 pt-2 pb-1" style={{ scrollbarWidth: "none" }}>
            {[["WC", "🌍 World Cup"], ["CL", "⭐ Champions League"]].map(([c, lbl]) => (
              <button key={c} type="button" onClick={() => { setComp(c); setBracket(null); load(c); }}
                className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
                style={{ background: c === comp ? C.home : C.line, color: c === comp ? "#08120F" : C.mute }}>
                {lbl}
              </button>
            ))}
          </div>

          {bracket === null ? (
            <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>Loading…</div>
          ) : (
            <BracketTree rounds={rounds} scrollRef={scrollRef} />
          )}
        </div>
      )}
    </div>
  );
}
