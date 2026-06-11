import { useState, useEffect, useRef } from "react";

// Point this at your Flask API. In Vite set VITE_API_BASE; empty falls back to
// interactive demo data so the UI still works without a backend.
let API_BASE = "";
try { if (import.meta && import.meta.env && import.meta.env.VITE_API_BASE) API_BASE = import.meta.env.VITE_API_BASE; } catch (e) {}

// Floodlit-pitch palette. Outcome colors carry meaning (home / draw / away).
const C = {
  bg: "#0B1413", panel: "#10201C", panel2: "#0E1A18", line: "#1E322C",
  chalk: "#E9EFEA", mute: "#7E938B", home: "#34D399", draw: "#9AA7B2",
  away: "#F4A152", glow: "rgba(52,211,153,0.10)",
};

const pct = (x) => `${Math.round((x || 0) * 100)}%`;
const outcomeColor = (label, home, away) =>
  label?.startsWith(home) ? C.home : label?.startsWith(away) ? C.away : C.draw;

// Client-side "X vs Y" parse — for the card title, and for the offline demo.
function parseVs(msg) {
  const m = msg.match(/^\s*(?:predict|forecast)?\s*(.+?)\s+(?:vs\.?|versus|v|against)\s+(.+?)\s*[?.!]*$/i);
  if (!m) return null;
  const clean = (s) => s.replace(/^(the|a)\s+/i, "").replace(/\s+(match|game|fixture|this weekend|today|tomorrow|on \w+)\b.*$/i, "").trim();
  return { home: clean(m[1]), away: clean(m[2]) };
}

const DEMO_STANDINGS = [
  { rank: 1, team: "Arsenal", P: 24, W: 17, D: 4, L: 3, GD: 31, Pts: 55 },
  { rank: 2, team: "Liverpool", P: 24, W: 16, D: 5, L: 3, GD: 28, Pts: 53 },
  { rank: 3, team: "Manchester City", P: 24, W: 15, D: 6, L: 3, GD: 30, Pts: 51 },
  { rank: 4, team: "Aston Villa", P: 24, W: 13, D: 5, L: 6, GD: 12, Pts: 44 },
  { rank: 5, team: "Tottenham", P: 24, W: 12, D: 4, L: 8, GD: 9, Pts: 40 },
];

function demoPredict(home, away) {
  // deterministic-ish from name lengths so it feels stable
  const edge = ((home.length - away.length) * 0.04);
  let h = 0.42 + edge, d = 0.27, a = 0.31 - edge;
  const s = h + d + a; h /= s; d /= s; a /= s;
  const label = h >= d && h >= a ? home : a >= d ? away : "Draw";
  return {
    prediction: label, confidence: Math.max(h, d, a),
    home_win_prob: h, draw_prob: d, away_win_prob: a,
    reasoning: `${home} edged on current form against ${away}; expected goals ${(1.3 + edge).toFixed(2)}-${(1.1 - edge).toFixed(2)}.`,
    key_factors: [`Form favours ${h > a ? home : away}`, "Home advantage applied", "Demo estimate"],
  };
}

function ProbBar({ home, draw, away, homeName, awayName }) {
  const seg = [
    { k: homeName, v: home, c: C.home },
    { k: "Draw", v: draw, c: C.draw },
    { k: awayName, v: away, c: C.away },
  ];
  return (
    <div>
      <div className="flex h-7 w-full overflow-hidden rounded-md" style={{ background: C.panel2 }}>
        {seg.map((s, i) => (
          <div key={i} className="flex items-center justify-center transition-all"
            style={{ width: pct(s.v), background: s.c, minWidth: s.v > 0.06 ? undefined : 0 }}>
            <span className="px-1 text-[11px] font-semibold tabular-nums" style={{ color: "#08120F" }}>
              {s.v > 0.12 ? pct(s.v) : ""}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px]" style={{ color: C.mute }}>
        {seg.map((s, i) => (
          <span key={i} className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: s.c }} />
            {s.k} <span className="tabular-nums" style={{ color: C.chalk }}>{pct(s.v)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function PredictionCard({ p, home, away }) {
  const color = outcomeColor(p.prediction, home, away);
  return (
    <div className="mt-2 rounded-xl border p-4" style={{ borderColor: C.line, background: C.panel, boxShadow: `0 0 0 1px ${C.glow}` }}>
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold" style={{ color: C.chalk }}>
          {home} <span style={{ color: C.mute }}>vs</span> {away}
        </div>
        <div className="rounded-full px-2.5 py-0.5 text-xs font-semibold" style={{ background: color, color: "#08120F" }}>
          {p.prediction} · {pct(p.confidence)}
        </div>
      </div>
      <div className="mt-3">
        <ProbBar home={p.home_win_prob} draw={p.draw_prob} away={p.away_win_prob} homeName={home} awayName={away} />
      </div>
      {p.key_factors?.length > 0 && (
        <ul className="mt-3 space-y-1">
          {p.key_factors.map((f, i) => (
            <li key={i} className="flex gap-2 text-xs" style={{ color: C.mute }}>
              <span style={{ color: color }}>▸</span>{f}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StandingsTable({ rows }) {
  return (
    <div className="rounded-xl border" style={{ borderColor: C.line, background: C.panel }}>
      <div className="border-b px-4 py-2.5 text-xs font-semibold uppercase tracking-wider" style={{ borderColor: C.line, color: C.mute }}>
        Premier League
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[11px] uppercase" style={{ color: C.mute }}>
            <th className="px-3 py-1.5 text-left font-medium">#</th>
            <th className="px-2 py-1.5 text-left font-medium">Club</th>
            <th className="px-2 py-1.5 text-right font-medium">GD</th>
            <th className="px-3 py-1.5 text-right font-medium">Pts</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.rank} className="border-t" style={{ borderColor: C.line }}>
              <td className="px-3 py-2 tabular-nums" style={{ color: C.mute }}>{r.rank}</td>
              <td className="px-2 py-2" style={{ color: C.chalk }}>{r.team}</td>
              <td className="px-2 py-2 text-right tabular-nums" style={{ color: C.mute }}>{r.GD > 0 ? `+${r.GD}` : r.GD}</td>
              <td className="px-3 py-2 text-right font-semibold tabular-nums" style={{ color: C.chalk }}>{r.Pts}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AccuracyPanel({ summary }) {
  const rate = summary?.hit_rate;
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: C.line, background: C.panel }}>
      <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
        How did my predictions do?
      </div>
      <div className="mt-3 flex items-end gap-2">
        <span className="text-4xl font-bold tabular-nums" style={{ color: rate == null ? C.mute : C.home }}>
          {rate == null ? "—" : pct(rate)}
        </span>
        <span className="mb-1 text-xs" style={{ color: C.mute }}>hit rate</span>
      </div>
      <div className="mt-1 text-xs" style={{ color: C.mute }}>
        {summary?.graded ? `${summary.correct}/${summary.graded} graded` : "No graded predictions yet"}
      </div>
    </div>
  );
}

export default function FootballMind() {
  const [sessionId] = useState(() => (crypto?.randomUUID?.() || String(Math.random())));
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [standings, setStandings] = useState(DEMO_STANDINGS);
  const [summary, setSummary] = useState(null);
  const [offline, setOffline] = useState(false);
  const scroller = useRef(null);

  useEffect(() => {
    if (!API_BASE) { setOffline(true); setSummary({ graded: 0, correct: 0, hit_rate: null }); return; }
    fetch(`${API_BASE}/api/standings?comp=PL`).then((r) => r.json())
      .then((d) => Array.isArray(d) && d.length && setStandings(d)).catch(() => setOffline(true));
    fetch(`${API_BASE}/api/predictions`).then((r) => r.json())
      .then((d) => setSummary(d.summary)).catch(() => {});
  }, []);

  useEffect(() => { scroller.current?.scrollTo(0, scroller.current.scrollHeight); }, [messages, busy]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    const teams = parseVs(text);
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      if (!API_BASE) throw new Error("offline");
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      if (!res.ok) throw new Error("bad status");
      const data = await res.json();
      setMessages((m) => [...m, { role: "bot", text: data.reply, prediction: data.prediction, teams }]);
    } catch (e) {
      // offline / unreachable -> local demo
      if (teams) {
        const p = demoPredict(teams.home, teams.away);
        setMessages((m) => [...m, { role: "bot", text: `${p.prediction} (${pct(p.confidence)} confidence). ${p.reasoning}`, prediction: p, teams, demo: true }]);
      } else {
        setMessages((m) => [...m, { role: "bot", text: "Try a matchup like \u201cPredict Arsenal vs Chelsea\u201d, or ask for the table.", demo: true }]);
      }
    } finally { setBusy(false); }
  }

  return (
    <div className="flex min-h-screen w-full flex-col font-sans" style={{ background: C.bg, color: C.chalk }}>
      <header className="flex items-center justify-between border-b px-5 py-3" style={{ borderColor: C.line }}>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold tracking-tight">FootballMind</span>
          <span className="text-xs" style={{ color: C.mute }}>match intelligence</span>
        </div>
        {offline && <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.away }}>demo data</span>}
      </header>

      <div className="flex flex-1 flex-col gap-4 p-4 md:flex-row">
        {/* Chat — the main panel */}
        <section className="flex min-h-[60vh] flex-1 flex-col rounded-xl border md:basis-[60%]" style={{ borderColor: C.line, background: C.panel2 }}>
          <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto p-4" style={{ maxHeight: "70vh" }}>
            {messages.length === 0 && (
              <div className="mt-10 text-center">
                <div className="text-sm" style={{ color: C.chalk }}>Ask anything about a match.</div>
                <div className="mt-1 text-xs" style={{ color: C.mute }}>e.g. &ldquo;Predict Arsenal vs Chelsea&rdquo; &middot; &ldquo;show the table&rdquo;</div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
                <div className="max-w-[85%]">
                  <div className="rounded-xl px-3.5 py-2 text-sm"
                    style={{ background: m.role === "user" ? C.home : C.panel, color: m.role === "user" ? "#08120F" : C.chalk }}>
                    {m.text}
                  </div>
                  {m.prediction && m.teams && (
                    <PredictionCard p={m.prediction} home={m.teams.home} away={m.teams.away} />
                  )}
                </div>
              </div>
            ))}
            {busy && <div className="text-xs" style={{ color: C.mute }}>Reading the match&hellip;</div>}
          </div>
          <div className="flex gap-2 border-t p-3" style={{ borderColor: C.line }}>
            <input
              value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Predict Arsenal vs Chelsea"
              className="flex-1 rounded-lg px-3 py-2 text-sm outline-none"
              style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }} />
            <button onClick={send} disabled={busy}
              className="rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
              style={{ background: C.home, color: "#08120F" }}>Ask</button>
          </div>
        </section>

        {/* Sidebar */}
        <aside className="flex flex-col gap-4 md:basis-[40%]">
          <AccuracyPanel summary={summary} />
          <StandingsTable rows={standings} />
        </aside>
      </div>
    </div>
  );
}
