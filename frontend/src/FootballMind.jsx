import { useState, useEffect, useRef } from "react";

let API_BASE = "";
try { if (import.meta?.env?.VITE_API_BASE) API_BASE = import.meta.env.VITE_API_BASE; } catch (e) {}

const C = {
  bg: "#0B1413", panel: "#10201C", panel2: "#0E1A18", line: "#1E322C",
  chalk: "#E9EFEA", mute: "#7E938B", home: "#34D399", draw: "#9AA7B2",
  away: "#F4A152", glow: "rgba(52,211,153,0.10)",
};

const pct = (x) => `${Math.round((x || 0) * 100)}%`;
const outcomeColor = (label, home, away) =>
  label?.startsWith(home) ? C.home : label?.startsWith(away) ? C.away : C.draw;

// ─── Country flag emoji lookup ─────────────────────────────────────────────
const FLAGS = {
  "Argentina": "🇦🇷", "Australia": "🇦🇺", "Belgium": "🇧🇪", "Brazil": "🇧🇷",
  "Canada": "🇨🇦", "Chile": "🇨🇱", "Colombia": "🇨🇴", "Croatia": "🇭🇷",
  "Czechia": "🇨🇿", "Czech Republic": "🇨🇿", "Denmark": "🇩🇰", "Ecuador": "🇪🇨",
  "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "France": "🇫🇷", "Germany": "🇩🇪", "Ghana": "🇬🇭",
  "Haiti": "🇭🇹", "Honduras": "🇭🇳", "Iran": "🇮🇷", "Italy": "🇮🇹",
  "Japan": "🇯🇵", "Jamaica": "🇯🇲", "Kenya": "🇰🇪", "Malaysia": "🇲🇾",
  "Mexico": "🇲🇽", "Morocco": "🇲🇦", "Netherlands": "🇳🇱", "Nigeria": "🇳🇬",
  "Norway": "🇳🇴", "Panama": "🇵🇦", "Paraguay": "🇵🇾", "Peru": "🇵🇪",
  "Poland": "🇵🇱", "Portugal": "🇵🇹", "Qatar": "🇶🇦", "Romania": "🇷🇴",
  "Saudi Arabia": "🇸🇦", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Senegal": "🇸🇳",
  "Serbia": "🇷🇸", "South Africa": "🇿🇦", "South Korea": "🇰🇷",
  "Spain": "🇪🇸", "Sweden": "🇸🇪", "Switzerland": "🇨🇭", "Turkey": "🇹🇷",
  "Ukraine": "🇺🇦", "United States": "🇺🇸", "USA": "🇺🇸", "Uruguay": "🇺🇾",
  "Venezuela": "🇻🇪", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "Algeria": "🇩🇿",
  "Ivory Coast": "🇨🇮", "Cameroon": "🇨🇲", "Egypt": "🇪🇬",
  "Cape Verde Islands": "🇨🇻", "Cape Verde": "🇨🇻", "Costa Rica": "🇨🇷",
  "Bosnia-Herzegovina": "🇧🇦", "New Zealand": "🇳🇿", "Cuba": "🇨🇺",
  "El Salvador": "🇸🇻", "Guatemala": "🇬🇹", "Trinidad and Tobago": "🇹🇹",
};

function flag(name) {
  if (!name) return "";
  const f = FLAGS[name];
  if (f) return f + " ";
  // try first word (e.g. "Manchester City FC" → no flag, "South Korea" → 🇰🇷)
  return "";
}

// ─── League tabs ──────────────────────────────────────────────────────────
const LEAGUES = [
  { code: "PL",  label: "Premier League",  short: "PL"  },
  { code: "PD",  label: "La Liga",         short: "La Liga" },
  { code: "BL1", label: "Bundesliga",      short: "Bundesliga" },
  { code: "SA",  label: "Serie A",         short: "Serie A" },
  { code: "FL1", label: "Ligue 1",         short: "Ligue 1" },
  { code: "CL",  label: "Champions League", short: "CL"  },
];

// ─── Suggestion chips ─────────────────────────────────────────────────────
const CHIPS = [
  "Predict Mexico vs USA",
  "Predict Spain vs Germany",
  "Predict Arsenal vs Chelsea",
  "Predict Brazil vs Argentina",
];

// ─── Intent parser ────────────────────────────────────────────────────────
function parseVs(msg) {
  const m = msg.match(/^\s*(?:predict|forecast)?\s*(.+?)\s+(?:vs\.?|versus|v|against)\s+(.+?)\s*[?.!]*$/i);
  if (!m) return null;
  const clean = (s) => s
    .replace(/^(who\s+will\s+win\s+|who\s+wins\s+|will\s+|can\s+|the\s+|a\s+)/i, "")
    .replace(/\s+(match|game|fixture|this weekend|today|tomorrow|on \w+)\b.*$/i, "")
    .trim();
  return { home: clean(m[1]), away: clean(m[2]) };
}

// ─── Stage badge labels ───────────────────────────────────────────────────
const STAGE_BADGE = {
  group: "GS", GROUP_STAGE: "GS", group_stage: "GS",
  round_of_32: "R32", LAST_32: "R32",
  round_of_16: "R16", LAST_16: "R16",
  quarter_final: "QF", QUARTER_FINALS: "QF",
  semi_final: "SF", SEMI_FINALS: "SF",
  final: "Final", FINAL: "Final",
};

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { weekday: "short", month: "short", day: "numeric" })
    + " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

// ─── Demo data ────────────────────────────────────────────────────────────
const DEMO_FIXTURES = [
  { home: "Mexico", away: "South Africa", match_date: "2026-06-11T19:00:00Z", stage: "GROUP_STAGE" },
  { home: "USA", away: "Canada", match_date: "2026-06-12T19:00:00Z", stage: "GROUP_STAGE" },
  { home: "Spain", away: "Cape Verde Islands", match_date: "2026-06-13T19:00:00Z", stage: "GROUP_STAGE" },
  { home: "Brazil", away: "Morocco", match_date: "2026-06-13T15:00:00Z", stage: "GROUP_STAGE" },
];

const DEMO_STANDINGS = [
  { rank: 1, team: "Arsenal FC",          GD: 44, Pts: 85 },
  { rank: 2, team: "Manchester City FC",  GD: 42, Pts: 78 },
  { rank: 3, team: "Manchester United FC",GD: 19, Pts: 71 },
  { rank: 4, team: "Aston Villa FC",      GD:  7, Pts: 65 },
  { rank: 5, team: "Liverpool FC",        GD: 10, Pts: 60 },
];

function demoPredict(home, away) {
  const edge = (home.length - away.length) * 0.04;
  let h = 0.42 + edge, d = 0.27, a = 0.31 - edge;
  const s = h + d + a; h /= s; d /= s; a /= s;
  const label = h >= d && h >= a ? home : a >= d ? away : "Draw";
  return {
    prediction: label, confidence: Math.max(h, d, a),
    home_win_prob: h, draw_prob: d, away_win_prob: a,
    reasoning: `${home} edged on current form; expected goals ${(1.3 + edge).toFixed(2)}-${(1.1 - edge).toFixed(2)}.`,
    key_factors: [`Form favours ${h > a ? home : away}`, "Home advantage applied", "Demo estimate"],
  };
}

// ─── Components ───────────────────────────────────────────────────────────
function ProbBar({ home, draw, away, homeName, awayName }) {
  const seg = [
    { k: homeName, v: home, c: C.home },
    { k: "Draw",   v: draw, c: C.draw },
    { k: awayName, v: away, c: C.away },
  ];
  return (
    <div>
      <div className="flex h-7 w-full overflow-hidden rounded-md" style={{ background: C.panel2 }}>
        {seg.map((s, i) => (
          <div key={i} className="flex items-center justify-center"
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
  const [copied, setCopied] = useState(false);

  function share() {
    const txt = `${flag(home)}${home} ${pct(p.home_win_prob)} · Draw ${pct(p.draw_prob)} · ${flag(away)}${away} ${pct(p.away_win_prob)}\nPrediction: ${p.prediction} (${pct(p.confidence)} confidence)\nvia FootballMind`;
    navigator.clipboard?.writeText(txt).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="mt-2 rounded-xl border p-4" style={{ borderColor: C.line, background: C.panel, boxShadow: `0 0 0 1px ${C.glow}` }}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold" style={{ color: C.chalk }}>
          {flag(home)}{home} <span style={{ color: C.mute }}>vs</span> {flag(away)}{away}
        </div>
        <div className="flex items-center gap-2">
          <div className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold" style={{ background: color, color: "#08120F" }}>
            {p.prediction} · {pct(p.confidence)}
          </div>
          <button onClick={share} title="Copy prediction"
            className="rounded px-1.5 py-0.5 text-[11px] transition-opacity hover:opacity-70"
            style={{ background: C.line, color: copied ? C.home : C.mute }}>
            {copied ? "✓" : "⎘"}
          </button>
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

function FixturesPanel({ wcFixtures, plFixtures, onClickFixture }) {
  const [tab, setTab] = useState("wc");
  const rows = tab === "wc" ? wcFixtures : plFixtures;
  const title = tab === "wc" ? "World Cup 2026" : "Premier League";

  return (
    <div className="rounded-xl border" style={{ borderColor: C.line, background: C.panel }}>
      <div className="border-b px-4 pt-3 pb-0" style={{ borderColor: C.line }}>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          Upcoming Fixtures
        </div>
        <div className="flex gap-1 pb-2">
          {[["wc", "🌍 World Cup"], ["pl", "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League"]].map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)}
              className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
              style={{ background: k === tab ? C.home : C.line, color: k === tab ? "#08120F" : C.mute }}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div>
        {rows.slice(0, 6).map((f, i) => (
          <button key={i} onClick={() => onClickFixture(f)}
            className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-opacity hover:opacity-70"
            style={{ background: "transparent", borderTop: i > 0 ? `1px solid ${C.line}` : "none" }}>
            <span className="shrink-0 rounded px-2 py-0.5 text-center text-[10px] font-semibold"
              style={{ background: C.line, color: C.mute, minWidth: "2.25rem" }}>
              {STAGE_BADGE[f.stage] ?? "GS"}
            </span>
            <span className="flex min-w-0 flex-1 items-center gap-1 text-xs font-medium" style={{ color: C.chalk }}>
              <span className="truncate">{flag(f.home)}{f.home}</span>
              <span className="shrink-0 text-[10px]" style={{ color: C.mute }}>vs</span>
              <span className="truncate">{flag(f.away)}{f.away}</span>
            </span>
            {f.home_goals != null
              ? <span className="shrink-0 text-xs font-bold tabular-nums" style={{ color: C.home }}>
                  {f.home_goals}–{f.away_goals}
                </span>
              : <span className="shrink-0 text-[10px] whitespace-nowrap" style={{ color: C.mute }}>
                  {fmtDate(f.match_date)}
                </span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function GroupsPanel({ groups }) {
  const letters = Object.keys(groups).sort();
  const [open, setOpen] = useState(letters[0] ?? null);

  if (letters.length === 0) return null;

  return (
    <div className="rounded-xl border" style={{ borderColor: C.line, background: C.panel }}>
      <div className="border-b px-4 py-2.5 text-xs font-semibold uppercase tracking-wider"
        style={{ borderColor: C.line, color: C.mute }}>
        WC Group Standings
      </div>
      {/* Group tabs */}
      <div className="flex flex-wrap gap-1 px-3 pt-2 pb-1">
        {letters.map((g) => (
          <button key={g} onClick={() => setOpen(g)}
            className="rounded px-2 py-0.5 text-[11px] font-semibold transition-colors"
            style={{ background: g === open ? C.home : C.line, color: g === open ? "#08120F" : C.mute }}>
            {g}
          </button>
        ))}
      </div>
      {open && groups[open] && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase" style={{ color: C.mute }}>
              <th className="px-3 py-1 text-left font-medium">Team</th>
              <th className="px-2 py-1 text-center font-medium">W</th>
              <th className="px-2 py-1 text-center font-medium">D</th>
              <th className="px-2 py-1 text-center font-medium">L</th>
              <th className="px-2 py-1 text-right font-medium">GD</th>
              <th className="px-3 py-1 text-right font-medium">Pts</th>
            </tr>
          </thead>
          <tbody>
            {groups[open].map((r, i) => (
              <tr key={i} className="border-t" style={{ borderColor: C.line }}>
                <td className="px-3 py-1.5 text-xs" style={{ color: C.chalk }}>
                  {flag(r.team)}{r.team}
                </td>
                <td className="px-2 py-1.5 text-center text-xs tabular-nums" style={{ color: C.chalk }}>{r.W}</td>
                <td className="px-2 py-1.5 text-center text-xs tabular-nums" style={{ color: C.mute }}>{r.D}</td>
                <td className="px-2 py-1.5 text-center text-xs tabular-nums" style={{ color: C.mute }}>{r.L}</td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums" style={{ color: C.mute }}>
                  {r.GD > 0 ? `+${r.GD}` : r.GD}
                </td>
                <td className="px-3 py-1.5 text-right text-xs font-bold tabular-nums" style={{ color: r.Pts > 0 ? C.home : C.chalk }}>
                  {r.Pts}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function StandingsPanel({ apiBase, offline }) {
  const [activeComp, setActiveComp] = useState("PL");
  const [rows, setRows] = useState(DEMO_STANDINGS);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!apiBase || offline) { setRows(DEMO_STANDINGS); return; }
    setLoading(true);
    fetch(`${apiBase}/api/standings?comp=${activeComp}`)
      .then((r) => r.json())
      .then((d) => { if (Array.isArray(d) && d.length) setRows(d); else setRows([]); })
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [activeComp, apiBase, offline]);

  const label = LEAGUES.find((l) => l.code === activeComp)?.label ?? activeComp;

  return (
    <div className="rounded-xl border" style={{ borderColor: C.line, background: C.panel }}>
      {/* Header + league tabs */}
      <div className="border-b px-4 pt-3 pb-0" style={{ borderColor: C.line }}>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          League Table
        </div>
        {/* Scrollable tab row */}
        <div className="flex gap-1 overflow-x-auto pb-2 scrollbar-none" style={{ scrollbarWidth: "none" }}>
          {LEAGUES.map((l) => (
            <button key={l.code} onClick={() => setActiveComp(l.code)}
              className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
              style={{
                background: l.code === activeComp ? C.home : C.line,
                color: l.code === activeComp ? "#08120F" : C.mute,
              }}>
              {l.short}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="px-4 py-6 text-center text-xs" style={{ color: C.mute }}>Loading {label}…</div>
      ) : rows.length === 0 ? (
        <div className="px-4 py-6 text-center text-xs" style={{ color: C.mute }}>
          No data yet for {label}.<br />Run a sync to populate.
        </div>
      ) : (
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
                <td className="px-2 py-2 max-w-[140px] truncate" style={{ color: C.chalk }}>{r.team}</td>
                <td className="px-2 py-2 text-right tabular-nums" style={{ color: C.mute }}>
                  {r.GD > 0 ? `+${r.GD}` : r.GD}
                </td>
                <td className="px-3 py-2 text-right font-semibold tabular-nums" style={{ color: C.chalk }}>{r.Pts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
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

// ─── Main app ─────────────────────────────────────────────────────────────
export default function FootballMind() {
  const [sessionId] = useState(() => (crypto?.randomUUID?.() || String(Math.random())));
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [wcFixtures, setWcFixtures] = useState(DEMO_FIXTURES);
  const [plFixtures, setPlFixtures] = useState([]);
  const [groups, setGroups] = useState({});
  const [summary, setSummary] = useState(null);
  const [offline, setOffline] = useState(false);
  const scroller = useRef(null);

  useEffect(() => {
    if (!API_BASE) { setOffline(true); setSummary({ graded: 0, correct: 0, hit_rate: null }); return; }
    fetch(`${API_BASE}/api/predictions`).then((r) => r.json())
      .then((d) => setSummary(d.summary)).catch(() => {});
    fetch(`${API_BASE}/api/fixtures?comp=WC&limit=16`).then((r) => r.json())
      .then((d) => d.fixtures?.length && setWcFixtures(d.fixtures)).catch(() => {});
    fetch(`${API_BASE}/api/fixtures?comp=PL&limit=10`).then((r) => r.json())
      .then((d) => d.fixtures?.length && setPlFixtures(d.fixtures)).catch(() => {});
    fetch(`${API_BASE}/api/groups?comp=WC`).then((r) => r.json())
      .then((d) => d.groups && setGroups(d.groups)).catch(() => {});
  }, []);

  useEffect(() => { scroller.current?.scrollTo(0, scroller.current.scrollHeight); }, [messages, busy]);

  function handleFixtureClick(f) {
    setInput(`Predict ${f.home} vs ${f.away}`);
    // scroll chat into view on mobile
    scroller.current?.scrollIntoView({ behavior: "smooth" });
  }

  async function send(text) {
    text = (text ?? input).trim();
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
    } catch {
      if (teams) {
        const p = demoPredict(teams.home, teams.away);
        setMessages((m) => [...m, { role: "bot", text: `${p.prediction} (${pct(p.confidence)} confidence). ${p.reasoning}`, prediction: p, teams, demo: true }]);
      } else {
        setMessages((m) => [...m, { role: "bot", text: 'Try a matchup like "Predict Mexico vs USA", or "show the table".', demo: true }]);
      }
    } finally { setBusy(false); }
  }

  const showChips = messages.length === 0;

  return (
    <div className="flex min-h-screen w-full flex-col font-sans" style={{ background: C.bg, color: C.chalk }}>
      <header className="flex items-center justify-between border-b px-5 py-3" style={{ borderColor: C.line }}>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold tracking-tight">Football Mind</span>
          <span className="text-xs" style={{ color: C.mute }}>match intelligence</span>
        </div>
        {offline && (
          <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.away }}>
            demo data
          </span>
        )}
      </header>

      <div className="flex flex-1 flex-col gap-4 p-4 md:flex-row">
        {/* ── Chat panel ── */}
        <section className="flex min-h-[60vh] flex-1 flex-col rounded-xl border md:basis-[60%]"
          style={{ borderColor: C.line, background: C.panel2 }}>
          <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto p-4" style={{ maxHeight: "70vh" }}>
            {messages.length === 0 && (
              <div className="mt-10 text-center">
                <div className="text-sm" style={{ color: C.chalk }}>Ask anything about a match.</div>
                <div className="mt-1 text-xs" style={{ color: C.mute }}>
                  Tap a fixture on the right, or type a question below.
                </div>
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

          {/* Suggestion chips */}
          {showChips && (
            <div className="flex flex-wrap gap-2 border-t px-3 pt-3 pb-0" style={{ borderColor: C.line }}>
              {CHIPS.map((c) => (
                <button key={c} onClick={() => send(c)}
                  className="rounded-full border px-3 py-1 text-[11px] font-medium transition-opacity hover:opacity-70"
                  style={{ borderColor: C.line, color: C.chalk, background: C.panel }}>
                  {c}
                </button>
              ))}
            </div>
          )}

          {/* Input row */}
          <div className="flex gap-2 border-t p-3" style={{ borderColor: C.line }}>
            <input
              value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Predict Mexico vs South Africa"
              className="flex-1 rounded-lg px-3 py-2 text-sm outline-none"
              style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }} />
            <button onClick={() => send()} disabled={busy}
              className="rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
              style={{ background: C.home, color: "#08120F" }}>Ask</button>
          </div>
        </section>

        {/* ── Sidebar ── */}
        <aside className="flex flex-col gap-4 md:basis-[40%]">
          <AccuracyPanel summary={summary} />
          <FixturesPanel wcFixtures={wcFixtures} plFixtures={plFixtures} onClickFixture={handleFixtureClick} />
          {Object.keys(groups).length > 0 && <GroupsPanel groups={groups} />}
          <StandingsPanel apiBase={API_BASE} offline={offline} />
        </aside>
      </div>
    </div>
  );
}
