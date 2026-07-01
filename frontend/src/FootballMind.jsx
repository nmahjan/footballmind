import { useState, useEffect, useRef } from "react";
import BracketPanel from "./components/BracketPanel.jsx";
import SyncHealthPanel from "./components/SyncHealthPanel.jsx";
import PlayersSidebar, { SidebarModeToggle, CardPredictedLineups } from "./components/PlayersSidebar.jsx";
import FixturesPanel from "./components/FixturesPanel.jsx";
import GroupsPanel from "./components/GroupsPanel.jsx";
import StandingsPanel from "./components/StandingsPanel.jsx";
import CalibrationPanel from "./components/CalibrationPanel.jsx";
import RankingsPanel from "./components/RankingsPanel.jsx";
import { C, flag } from "./fm/theme.js";
import { pct, outcomeColor } from "./fm/format.js";
import { DEMO_FIXTURES, demoPredict, COMP_LABELS } from "./fm/demo.js";

let API_BASE = "";
try { if (import.meta?.env?.VITE_API_BASE) API_BASE = import.meta.env.VITE_API_BASE; } catch (e) {}

// ─── Suggestion chips ─────────────────────────────────────────────────────
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

const SESSION_KEY = "footballmind_session_id";
const ADMIN_KEY_STORAGE = "footballmind_admin_key";

function getAdminKey() {
  try { return localStorage.getItem(ADMIN_KEY_STORAGE) || ""; } catch { return ""; }
}

function saveAdminKeyFromUrl() {
  try {
    const k = new URLSearchParams(window.location.search).get("admin_key");
    if (k) localStorage.setItem(ADMIN_KEY_STORAGE, k);
  } catch { /* ignore */ }
}

function getOrCreateSessionId() {
  try {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = createNewSessionId();
    }
    return id;
  } catch {
    return crypto?.randomUUID?.() || String(Math.random());
  }
}

function createNewSessionId() {
  const id = crypto?.randomUUID?.() || String(Math.random());
  try { localStorage.setItem(SESSION_KEY, id); } catch { /* ignore */ }
  return id;
}

function formatPlayerMeta(p) {
  const parts = [];
  if (p.line_role) parts.push(p.line_role);
  const eafc = p.eafc;
  if (eafc?.preferred_foot) parts.push(eafc.preferred_foot);
  if (eafc?.overall_rating) parts.push(`OVR ${eafc.overall_rating}`);
  return parts.length ? parts.join(" · ") : null;
}

function formatEafc(eafc) {
  return formatPlayerMeta({ eafc });
}

const LOAD_MESSAGES = {
  waking: "Waking up backend…",
  waking_slow: "Still waking up — Render free tier can take ~30 seconds",
  predict: "Running prediction model…",
  compare: "Comparing players…",
  standings: "Loading standings…",
  llm: "Consulting FootballMind AI…",
  thinking: "Thinking…",
  still_thinking: "Almost there — complex questions can take a few seconds",
};

function guessLoadPhase(text, backendStatus) {
  if (backendStatus === "connecting" || backendStatus === "unreachable") return "waking";
  const low = text.toLowerCase();
  if (/\b(predict|forecast)\b/.test(low) || /\bvs\.?\b|\bversus\b/.test(low)) return "predict";
  if (/\bcompare\b|\bwho('s| is) better\b/.test(low)) return "compare";
  if (/\btable\b|\bstanding\b/.test(low)) return "standings";
  if (/\b(squad|scorer|player|lineup|formation)\b/.test(low)) return "llm";
  return "thinking";
}

function TypingIndicator({ phase }) {
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

async function pingBackend(apiBase, timeoutMs = 28000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${apiBase}/api/health`, { signal: ctrl.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

async function readApiError(res) {
  try {
    const data = await res.json();
    return data.message || data.detail || data.error || `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}


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

const VALID_COMPS = new Set(["WC", "PL", "PD", "BL1", "SA", "FL1", "CL", "DED", "MLS"]);
const DEEPLINK_STORAGE_KEY = "fm_deeplink_search";
const PREDICTION_CACHE_KEY = "fm_prediction_cache";

function deepLinkParamsHasPredict(params) {
  return Boolean(
    params.get("predict")?.trim() ||
    (params.get("home")?.trim() && params.get("away")?.trim())
  );
}

/** Query params (legacy) or hash (LinkedIn / in-app browsers often strip ?predict=). */
function getDeepLinkParams() {
  if (typeof window === "undefined") return new URLSearchParams();
  const fromSearch = new URLSearchParams(window.location.search);
  if (deepLinkParamsHasPredict(fromSearch)) return fromSearch;
  const raw = window.location.hash.replace(/^#/, "").trim();
  if (raw) {
    const fromHash = new URLSearchParams(raw);
    if (deepLinkParamsHasPredict(fromHash)) return fromHash;
  }
  return fromSearch;
}

function deepLinkSignature() {
  const params = getDeepLinkParams();
  return deepLinkParamsHasPredict(params) ? params.toString() : "";
}

function buildPredictUrl(home, away, { comp, neutral } = {}) {
  const url = new URL(window.location.href);
  url.search = "";
  const params = new URLSearchParams();
  params.set("predict", `${home} vs ${away}`);
  if (comp && comp !== "WC") params.set("comp", comp);
  if (neutral === true) params.set("neutral", "1");
  else if (neutral === false) params.set("neutral", "0");
  url.hash = params.toString();
  return url.toString();
}

function clearDeepLinkParams() {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  for (const key of ["predict", "home", "away", "comp", "neutral"]) {
    url.searchParams.delete(key);
  }
  url.hash = "";
  const qs = url.searchParams.toString();
  window.history.replaceState(null, "", url.pathname + (qs ? `?${qs}` : ""));
}

function markDeepLinkHandled(sig = deepLinkSignature()) {
  try { sessionStorage.setItem(DEEPLINK_STORAGE_KEY, sig || ""); } catch { /* ignore */ }
}

function deepLinkAlreadyHandled(sig = deepLinkSignature()) {
  try { return sessionStorage.getItem(DEEPLINK_STORAGE_KEY) === (sig || ""); } catch { return false; }
}

function savePredictionCache(query, entry) {
  try {
    const key = (query || "").trim().toLowerCase();
    if (!key) return;
    const cache = JSON.parse(sessionStorage.getItem(PREDICTION_CACHE_KEY) || "{}");
    cache[key] = entry;
    const keys = Object.keys(cache);
    if (keys.length > 24) {
      for (const k of keys.slice(0, keys.length - 24)) delete cache[k];
    }
    sessionStorage.setItem(PREDICTION_CACHE_KEY, JSON.stringify(cache));
  } catch { /* ignore */ }
}

function loadPredictionCache(query) {
  try {
    const cache = JSON.parse(sessionStorage.getItem(PREDICTION_CACHE_KEY) || "{}");
    return cache[(query || "").trim().toLowerCase()] || null;
  } catch { return null; }
}

function syncPredictUrl(home, away, comp, neutral) {
  if (!home || !away || typeof window === "undefined") return;
  const next = buildPredictUrl(home, away, { comp, neutral });
  if (window.location.href !== next) {
    window.history.replaceState(null, "", next);
  }
  markDeepLinkHandled(deepLinkSignature());
}

function parseDeepLinkSearch() {
  const params = getDeepLinkParams();
  const predict = params.get("predict")?.trim();
  const home = params.get("home")?.trim();
  const away = params.get("away")?.trim();
  let query = null;
  if (predict) {
    query = /^predict\b/i.test(predict) ? predict : `Predict ${predict}`;
  } else if (home && away) {
    query = `Predict ${home} vs ${away}`;
  }
  if (!query) return null;
  const comp = params.get("comp")?.trim().toUpperCase();
  const neutralRaw = params.get("neutral");
  let neutral = null;
  if (neutralRaw === "1" || neutralRaw === "true") neutral = true;
  else if (neutralRaw === "0" || neutralRaw === "false") neutral = false;
  return { query, comp: comp && VALID_COMPS.has(comp) ? comp : null, neutral };
}

function hasDeepLinkPredict() {
  return deepLinkParamsHasPredict(getDeepLinkParams());
}

// ─── Stage badge labels ───────────────────────────────────────────────────

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

function AdvanceBar({ prog, homeName, awayName }) {
  const ha = prog?.home_advance ?? 0.5;
  const aa = prog?.away_advance ?? 0.5;
  const seg = [
    { k: homeName, v: ha, c: C.home },
    { k: awayName, v: aa, c: C.away },
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
            {s.k} advance <span className="tabular-nums" style={{ color: C.chalk }}>{pct(s.v)}</span>
          </span>
        ))}
      </div>
      <p className="mt-1 text-[10px]" style={{ color: C.mute }}>
        Knockout — extra time &amp; penalties if level after 90
      </p>
    </div>
  );
}

const FORM_COLOR = { W: C.home, D: C.draw, L: C.away };

function inlineFormat(text) {
  if (!text) return text;
  const parts = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(<strong key={`b-${m.index}`}>{m[1]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : parts;
}

/** LLM replies often cram markdown onto one line — split before headings/rules. */
function normalizeMarkdown(text) {
  return (text || "")
    .replace(/\s+(#{1,3}\s)/g, "\n\n$1")
    .replace(/\s+---\s+/g, "\n\n---\n\n")
    .trim();
}

function MarkdownBody({ text, size = "sm" }) {
  const body = normalizeMarkdown(text);
  const lines = body.split("\n");
  const out = [];
  let listItems = null;
  const textSize = size === "xs" ? "text-xs" : "text-sm";

  function flushList() {
    if (listItems?.length) {
      out.push(
        <ul key={`ul-${out.length}`} className={`my-1.5 ml-4 list-disc space-y-0.5 ${textSize}`}>
          {listItems}
        </ul>
      );
      listItems = null;
    }
  }

  lines.forEach((line, i) => {
    const t = line.trim();
    if (!t) return;
    if (t === "---" || t === "***") {
      flushList();
      out.push(<hr key={`hr-${i}`} className="my-2 border-t" style={{ borderColor: C.line }} />);
      return;
    }
    if (t.startsWith("### ")) {
      flushList();
      out.push(
        <h4 key={i} className={`mt-2 mb-0.5 ${textSize} font-semibold`} style={{ color: C.chalk }}>
          {inlineFormat(t.slice(4))}
        </h4>
      );
      return;
    }
    if (t.startsWith("## ")) {
      flushList();
      out.push(
        <h3 key={i} className={`mt-2 mb-0.5 ${textSize} font-semibold`} style={{ color: C.chalk }}>
          {inlineFormat(t.slice(3))}
        </h3>
      );
      return;
    }
    if (t.startsWith("# ")) {
      flushList();
      out.push(
        <h2 key={i} className={`mt-2 mb-0.5 ${textSize} font-bold`} style={{ color: C.chalk }}>
          {inlineFormat(t.slice(2))}
        </h2>
      );
      return;
    }
    if (t.startsWith("- ") || t.startsWith("* ")) {
      if (!listItems) listItems = [];
      listItems.push(
        <li key={i} style={{ color: C.chalk }}>{inlineFormat(t.slice(2))}</li>
      );
      return;
    }
    flushList();
    out.push(
      <p key={i} className={`${textSize} leading-relaxed mb-1`} style={{ color: C.chalk }}>
        {inlineFormat(t)}
      </p>
    );
  });
  flushList();
  return <div>{out}</div>;
}

function FormDots({ results, label }) {
  if (!results?.length) return null;
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px]" style={{ color: C.mute }}>{label}</span>
      {results.map((r, i) => (
        <span key={i} className="inline-flex h-4 w-4 items-center justify-center rounded-sm text-[9px] font-bold"
          style={{ background: FORM_COLOR[r] ?? C.line, color: "#08120F" }}>
          {r}
        </span>
      ))}
    </div>
  );
}

const KO_STAGES = new Set([
  "round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "third_place",
]);

function knockoutProgression(p, comp) {
  if (p?.progression) return p.progression;
  const stage = p?.stage;
  const knockoutStage = stage && KO_STAGES.has(stage);
  const tournamentCtx = (comp === "WC" || comp === "CL") && stage !== "group";
  if (!knockoutStage && !(tournamentCtx && p?.is_knockout)) return null;
  const d = p.draw_prob ?? 0;
  const hw = p.home_win_prob ?? 0;
  const ha = hw + d * 0.5;
  return { home_advance: ha, away_advance: 1 - ha };
}

function PredictionCard({ p, home, away, comp = "WC", neutral = null }) {
  const color = outcomeColor(p.prediction, home, away);
  const prog = knockoutProgression(p, comp);
  const isKnockout = Boolean(p.is_knockout || prog);
  const [copied, setCopied] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState(null);

  function share() {
    const url = buildPredictUrl(home, away, { comp, neutral });
    const probs = isKnockout && prog
      ? `${flag(home)}${home} ${pct(prog.home_advance)} · ${flag(away)}${away} ${pct(prog.away_advance)} (advance)`
      : `${flag(home)}${home} ${pct(p.home_win_prob)} · Draw ${pct(p.draw_prob)} · ${flag(away)}${away} ${pct(p.away_win_prob)}`;
    const txt = `${probs}\nPrediction: ${p.prediction} (${pct(p.confidence)} confidence)\n${url}\nvia FootballMind`;
    navigator.clipboard?.writeText(txt).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function copyLink() {
    const url = buildPredictUrl(home, away, { comp, neutral });
    navigator.clipboard?.writeText(url).then(() => {
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    });
  }

  async function analyze() {
    if (analyzing || analysis) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const res = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ home, away, prediction: p, comp }),
      });
      if (res.status === 429) {
        setAnalyzeError(await readApiError(res));
        return;
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.message || "Failed");
      setAnalysis(data.analysis);
    } catch (e) {
      setAnalyzeError(e.message || "Analysis unavailable");
    } finally {
      setAnalyzing(false);
    }
  }

  const h2h = p.h2h;
  const hasH2h = h2h?.played > 0;

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
          <button onClick={share} title="Copy prediction summary + link"
            className="rounded px-1.5 py-0.5 text-[11px] transition-opacity hover:opacity-70"
            style={{ background: C.line, color: copied ? C.home : C.mute }}>
            {copied ? "✓" : "⎘"}
          </button>
          <button onClick={copyLink} title="Copy share link"
            className="rounded px-1.5 py-0.5 text-[11px] transition-opacity hover:opacity-70"
            style={{ background: C.line, color: linkCopied ? C.home : C.mute }}>
            {linkCopied ? "✓" : "🔗"}
          </button>
        </div>
      </div>

      {/* Form guides */}
      {(p.home_form?.length > 0 || p.away_form?.length > 0) && (
        <div className="mt-2.5 flex flex-col gap-1">
          <FormDots results={p.home_form} label={home.split(" ")[0]} />
          <FormDots results={p.away_form} label={away.split(" ")[0]} />
        </div>
      )}

      {p.stakes?.labels?.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1">
          {p.stakes.labels.map((lbl) => (
            <span key={lbl} className="rounded-md px-2 py-0.5 text-[10px] font-semibold"
              style={{ background: "rgba(251,191,36,0.12)", color: "#fbbf24", border: "1px solid rgba(251,191,36,0.35)" }}>
              {lbl}
            </span>
          ))}
        </div>
      )}
      {p.stakes?.summary && (
        <p className="mt-1.5 text-[11px] leading-snug" style={{ color: C.mute }}>{p.stakes.summary}</p>
      )}
      {p.stakes_adjustment?.applied && (
        <p className="mt-1 text-[10px] italic" style={{ color: C.mute }}>
          High-pressure adjustment: xG ×{(p.stakes_adjustment.total_xg_multiplier ?? 1).toFixed(3)}
          {p.stakes_adjustment.draw_tilt != null
            ? ` · draw tilt +${Math.round(p.stakes_adjustment.draw_tilt * 100)}%`
            : ""}
        </p>
      )}

      <div className="mt-3">
        {isKnockout && prog
          ? <AdvanceBar prog={prog} homeName={home} awayName={away} />
          : <ProbBar home={p.home_win_prob} draw={p.draw_prob} away={p.away_win_prob} homeName={home} awayName={away} />}
      </div>

      {/* Head-to-head */}
      {hasH2h && (
        <div className="mt-2.5 flex items-center gap-1.5 text-[11px]" style={{ color: C.mute }}>
          <span>H2H ({h2h.played}):</span>
          <span style={{ color: C.home }}>{h2h.home_wins}W</span>
          <span>·</span>
          <span style={{ color: C.draw }}>{h2h.draws}D</span>
          <span>·</span>
          <span style={{ color: C.away }}>{h2h.away_wins}L</span>
          <span style={{ color: C.mute }}>for {home.split(" ")[0]}</span>
        </div>
      )}

      <CardPredictedLineups home={home} away={away} comp={comp} apiBase={API_BASE} />

      {p.key_factors?.length > 0 && (
        <ul className="mt-2.5 space-y-1">
          {p.key_factors.map((f, i) => (
            <li key={i} className="flex gap-2 text-xs" style={{ color: C.mute }}>
              <span style={{ color: color }}>▸</span>{f}
            </li>
          ))}
        </ul>
      )}

      {/* AI analysis section */}
      {!analysis && !analyzeError && API_BASE && (
        <button onClick={analyze} disabled={analyzing}
          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border py-1.5 text-xs font-medium transition-opacity hover:opacity-70 disabled:opacity-40"
          style={{ borderColor: C.line, color: C.mute }}>
          {analyzing
            ? <><span className="animate-spin">⟳</span> Analyzing match…</>
            : <>✨ Deep analysis</>}
        </button>
      )}
      {analysis && (
        <div className="mt-3 rounded-lg border-l-2 pl-3 pr-2 py-2.5 text-xs leading-relaxed"
          style={{ borderColor: color, background: C.panel2, color: C.chalk }}>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
            ✨ AI Analysis
          </div>
          <MarkdownBody text={analysis} size="xs" />
        </div>
      )}
      {analyzeError && (
        <div className="mt-2 text-[11px]" style={{ color: C.away }}>
          {analyzeError}
        </div>
      )}
    </div>
  );
}


// ─── Main app ─────────────────────────────────────────────────────────────
export default function FootballMind() {
  const [sessionId, setSessionId] = useState(getOrCreateSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [venueMode, setVenueMode] = useState(null); // null=auto, true=neutral, false=home
  const [busy, setBusy] = useState(false);
  const [loadPhase, setLoadPhase] = useState(null);
  const [wcFixtures, setWcFixtures] = useState(API_BASE ? [] : DEMO_FIXTURES);
  const [plFixtures, setPlFixtures] = useState([]);
  const [groups, setGroups] = useState({});
  const [summary, setSummary] = useState(null);
  const [offline, setOffline] = useState(!API_BASE);
  const [backendStatus, setBackendStatus] = useState(API_BASE ? "connecting" : "demo");
  const [sidebarMode, setSidebarMode] = useState("matches");
  const [sidebarLoaded, setSidebarLoaded] = useState(false);
  const [chatComp, setChatComp] = useState("WC");
  const [adminKey, setAdminKey] = useState(() => getAdminKey());
  const scroller = useRef(null);
  const sendRef = useRef(null);
  const deepLinkHandled = useRef(false);
  const shareLinkAtLoad = useRef(parseDeepLinkSearch());
  const historyBlockedRef = useRef(Boolean(shareLinkAtLoad.current));

  function handleCompChange(code) {
    if (code && COMP_LABELS[code]) setChatComp(code);
  }

  async function loadSidebarData() {
    if (!API_BASE) return;
    try {
      const [healthRes, wcRes, plRes, grpRes] = await Promise.all([
        fetch(`${API_BASE}/api/health`),
        fetch(`${API_BASE}/api/fixtures?comp=WC&limit=32`),
        fetch(`${API_BASE}/api/fixtures?comp=PL&limit=10`),
        fetch(`${API_BASE}/api/groups?comp=WC`),
      ]);
      if (!healthRes.ok) throw new Error("health");
      const wcData = await wcRes.json();
      const plData = await plRes.json();
      const grpData = await grpRes.json();
      if (wcData.fixtures) setWcFixtures(wcData.fixtures);
      if (plData.fixtures) setPlFixtures(plData.fixtures);
      if (grpData.groups) setGroups(grpData.groups);
      setOffline(false);
      setBackendStatus("live");
    } catch {
      setBackendStatus((s) => (s === "live" ? "live" : "unreachable"));
    } finally {
      setSidebarLoaded(true);
    }
  }

  useEffect(() => {
    saveAdminKeyFromUrl();
    const k = getAdminKey();
    if (k) setAdminKey(k);
  }, []);

  useEffect(() => {
    if (!API_BASE) {
      setOffline(true);
      setSummary({ graded: 0, correct: 0, hit_rate: null });
      return;
    }
    fetch(`${API_BASE}/api/predictions`).then((r) => r.json())
      .then((d) => setSummary(d.summary)).catch(() => {});
    loadSidebarData();
    const t1 = setTimeout(loadSidebarData, 4000);
    const t2 = setTimeout(loadSidebarData, 12000);
    const poll = setInterval(() => {
      loadSidebarData();
      fetch(`${API_BASE}/api/predictions`).then((r) => r.json())
        .then((d) => setSummary(d.summary)).catch(() => {});
    }, 90000);
    return () => { clearTimeout(t1); clearTimeout(t2); clearInterval(poll); };
  }, []);

  useEffect(() => {
    if (!API_BASE || historyBlockedRef.current) return;
    const ctrl = new AbortController();
    fetch(`${API_BASE}/api/history?session_id=${encodeURIComponent(sessionId)}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (historyBlockedRef.current || shareLinkAtLoad.current) return;
        if (!data?.history?.length) return;
        const restored = [];
        for (const row of [...data.history].reverse()) {
          if (row.query) restored.push({ role: "user", text: row.query });
          if (row.response) {
            const cached = loadPredictionCache(row.query);
            restored.push({
              role: "bot",
              text: row.response,
              ...(cached || {}),
            });
          }
        }
        if (restored.length) {
          setMessages((prev) => (prev.length ? prev : restored));
        }
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
      });
    return () => ctrl.abort();
  }, [sessionId]);

  useEffect(() => { scroller.current?.scrollTo(0, scroller.current.scrollHeight); }, [messages, busy, loadPhase]);

  async function ensureBackendAwake() {
    if (!API_BASE || backendStatus === "live") return true;
    setLoadPhase("waking");
    const ok = await pingBackend(API_BASE);
    if (ok) {
      setBackendStatus("live");
      setOffline(false);
      return true;
    }
    setBackendStatus("unreachable");
    setLoadPhase("waking_slow");
    return false;
  }

  function handleFixtureClick(f) {
    setInput(`Predict ${f.home} vs ${f.away}`);
    scroller.current?.scrollIntoView({ behavior: "smooth" });
  }

  function handlePlayerAsk(text) {
    send(text);
    scroller.current?.scrollIntoView({ behavior: "smooth" });
  }

  function startNewChat() {
    if (busy) return;
    setSessionId(createNewSessionId());
    setMessages([]);
    setInput("");
    try {
      sessionStorage.removeItem(DEEPLINK_STORAGE_KEY);
      sessionStorage.removeItem(PREDICTION_CACHE_KEY);
    } catch { /* ignore */ }
    clearDeepLinkParams();
    shareLinkAtLoad.current = null;
    historyBlockedRef.current = false;
    deepLinkHandled.current = true;
  }

  async function send(text, options = {}) {
    text = (text ?? input).trim();
    if (!text || busy) return;
    setInput("");
    const teams = parseVs(text);
    const effectiveComp = options.comp ?? chatComp;
    const effectiveNeutral = options.neutral !== undefined ? options.neutral : venueMode;
    const history = messages.slice(-10).flatMap((m) =>
      m.role === "user"
        ? [{ role: "user", content: m.text }]
        : [{ role: "assistant", content: m.text }]
    );
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    setLoadPhase(guessLoadPhase(text, backendStatus));
    const slowTimer = setTimeout(() => {
      setLoadPhase((p) => {
        if (p === "waking" || p === "waking_slow") return "waking_slow";
        return "still_thinking";
      });
    }, 10000);
    try {
      if (!API_BASE) throw new Error("offline");
      let isLive = backendStatus === "live";
      if (!isLive) {
        isLive = await ensureBackendAwake();
        setLoadPhase(guessLoadPhase(text, isLive ? "live" : "unreachable"));
      }
      const body = { message: text, session_id: sessionId, history, comp: effectiveComp };
      if (effectiveNeutral !== null) body.neutral = effectiveNeutral;
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.status === 429) {
        const msg = await readApiError(res);
        setMessages((m) => [...m, { role: "bot", text: msg, rateLimited: true }]);
        return;
      }
      if (!res.ok) throw new Error("bad status");
      const data = await res.json();
      setBackendStatus("live");
      setOffline(false);
      setMessages((m) => [...m, {
        role: "bot", text: data.reply, prediction: data.prediction, teams,
        comp: effectiveComp, neutral: effectiveNeutral,
        bracket: data.bracket, bracketComp: data.bracket_comp,
      }]);
      if (data.prediction && teams) {
        savePredictionCache(text, {
          prediction: data.prediction,
          teams,
          comp: effectiveComp,
          neutral: effectiveNeutral,
        });
      }
      if (teams) syncPredictUrl(teams.home, teams.away, effectiveComp, effectiveNeutral);
      if (options.fromDeepLink) clearDeepLinkParams();
    } catch {
      if (!API_BASE) {
        if (teams) {
          const p = demoPredict(teams.home, teams.away);
          setMessages((m) => [...m, { role: "bot", text: `${p.prediction} (${pct(p.confidence)} confidence). ${p.reasoning}`, prediction: p, teams, demo: true }]);
        } else {
          setMessages((m) => [...m, { role: "bot", text: 'Try a matchup like "Predict Mexico vs USA", or "show the table".', demo: true }]);
        }
      } else {
        setBackendStatus("unreachable");
        setMessages((m) => [...m, { role: "bot", text: "Backend unavailable — Render may still be waking up. Wait ~30s and try again." }]);
        loadSidebarData();
      }
    } finally {
      clearTimeout(slowTimer);
      setBusy(false);
      setLoadPhase(null);
    }
  }

  sendRef.current = send;

  useEffect(() => {
    if (deepLinkHandled.current) return;
    const link = parseDeepLinkSearch();
    if (!link) return;
    deepLinkHandled.current = true;
    historyBlockedRef.current = true;

    const sig = deepLinkSignature();
    if (deepLinkAlreadyHandled(sig)) {
      clearDeepLinkParams();
      return;
    }

    markDeepLinkHandled(sig);
    setMessages([]);
    if (link.comp) setChatComp(link.comp);
    if (link.neutral !== null) setVenueMode(link.neutral);
    const t = setTimeout(() => sendRef.current?.(link.query, {
      comp: link.comp ?? undefined,
      neutral: link.neutral,
      fromDeepLink: true,
    }), 150);
    return () => clearTimeout(t);
  }, []);

  const showChips = messages.length === 0;

  return (
    <div className="flex min-h-screen w-full flex-col font-sans" style={{ background: C.bg, color: C.chalk }}>
      <header className="flex items-center justify-between border-b px-5 py-3" style={{ borderColor: C.line }}>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold tracking-tight">Football Mind</span>
          <span className="text-xs" style={{ color: C.mute }}>Match Intelligence · By Neil M.</span>
        </div>
        {offline ? (
          <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.away }}>
            demo data
          </span>
        ) : backendStatus === "connecting" ? (
          <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.mute }}>
            connecting…
          </span>
        ) : backendStatus === "unreachable" ? (
          <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.away }}>
            backend waking up
          </span>
        ) : (
          <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.home }}>
            live
          </span>
        )}
      </header>

      <div className="flex min-w-0 flex-1 flex-col gap-4 p-4 md:flex-row">
        {/* ── Chat panel ── */}
        <section className="flex min-h-[60vh] min-w-0 flex-1 flex-col rounded-xl border md:min-w-0 md:basis-[60%]"
          style={{ borderColor: C.line, background: C.panel2 }}>
          <div className="flex items-center justify-between border-b px-4 py-2" style={{ borderColor: C.line }}>
            <span className="text-[10px] font-medium" style={{ color: C.mute }}>Chat</span>
            <button
              type="button"
              onClick={startNewChat}
              disabled={busy}
              title="Start a fresh conversation"
              className="rounded-md border px-2.5 py-1 text-[10px] font-semibold transition-opacity hover:opacity-80 disabled:opacity-40"
              style={{ borderColor: C.line, color: C.chalk, background: C.panel }}>
              New chat
            </button>
          </div>
          <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto p-4" style={{ maxHeight: "70vh" }}>
            {messages.length === 0 && (
              <div className="mt-10 text-center">
                <div className="text-sm" style={{ color: C.chalk }}>
                  {sidebarMode === "players"
                    ? "Ask about players, squads, or why a team works."
                    : "Ask anything about a match."}
                </div>
                <div className="mt-1 text-xs" style={{ color: C.mute }}>
                  {sidebarMode === "players"
                    ? "Switch to Players on the right, tap a name, or type a question below."
                    : "Tap a fixture on the right, or type a question below."}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
                <div className="max-w-[85%]">
                  <div className="rounded-xl px-3.5 py-2 text-sm"
                    style={{ background: m.role === "user" ? C.home : C.panel, color: m.role === "user" ? "#08120F" : C.chalk }}>
                    {m.role === "user" ? m.text : <MarkdownBody text={m.text} />}
                  </div>
                  {m.prediction && m.teams && (
                    <PredictionCard
                      p={m.prediction}
                      home={m.teams.home}
                      away={m.teams.away}
                      comp={m.comp ?? chatComp}
                      neutral={m.neutral ?? null}
                    />
                  )}
                  {m.bracket && (
                    <div className="mt-2 w-full min-w-0 max-w-full overflow-hidden rounded-xl border p-1"
                      style={{ borderColor: C.line, background: C.panel }}>
                      <BracketTree rounds={normaliseBracket(m.bracket)} />
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && loadPhase && <TypingIndicator phase={loadPhase} />}
          </div>

          {/* Suggestion chips */}
          {showChips && (
            <div className="flex flex-wrap gap-2 px-3 pt-3 pb-0">
              {(sidebarMode === "players" ? PLAYER_CHIPS : CHIPS).map((c) => (
                <button key={c} onClick={() => send(c)}
                  className="rounded-full border px-3 py-1 text-[11px] font-medium transition-opacity hover:opacity-70"
                  style={{ borderColor: C.line, color: C.chalk, background: C.panel }}>
                  {c}
                </button>
              ))}
            </div>
          )}

          {/* Venue toggle + input row */}
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
                    background: venueMode === val ? (val === false ? C.away : val === true ? C.home : C.mute) : C.line,
                    color: venueMode === val ? "#08120F" : C.mute,
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
                className="flex-1 rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }} />
              <button onClick={() => send()} disabled={busy}
                className="rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
                style={{ background: C.home, color: "#08120F" }}>Ask</button>
            </div>
          </div>
        </section>

        {/* ── Sidebar ── */}
        <aside className="flex min-w-0 flex-col gap-4 md:max-w-[40%] md:basis-[40%] md:shrink-0">
          <SidebarModeToggle mode={sidebarMode} setMode={setSidebarMode} />
          {sidebarMode === "matches" ? (
            <>
              <CalibrationPanel summary={summary} apiBase={API_BASE} offline={offline} />
              <SyncHealthPanel apiBase={API_BASE} offline={offline} />
              <FixturesPanel initialWc={wcFixtures} initialPl={plFixtures} sidebarLoaded={sidebarLoaded} onClickFixture={handleFixtureClick} apiBase={API_BASE} onSummary={setSummary} onCompChange={handleCompChange} />
              {Object.keys(groups).length > 0 && <GroupsPanel groups={groups} />}
              <BracketPanel apiBase={API_BASE} offline={offline} defaultComp={chatComp === "CL" ? "CL" : "WC"} />
              <RankingsPanel apiBase={API_BASE} offline={offline} />
              <StandingsPanel apiBase={API_BASE} offline={offline} onCompChange={handleCompChange} />
            </>
          ) : (
            <PlayersSidebar apiBase={API_BASE} offline={offline} onAsk={handlePlayerAsk} onCompChange={handleCompChange} adminKey={adminKey} />
          )}
        </aside>
      </div>
    </div>
  );
}
