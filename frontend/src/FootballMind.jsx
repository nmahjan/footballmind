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
  { code: "DED", label: "Eredivisie",      short: "Eredivisie" },
];

// Qualification / relegation zones (mirrors footballmind_standings_zones.py)
const STANDING_ZONES = {
  PL: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 4 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 5, to: 5 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 6, to: 6 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 3, toEnd: 1 },
  ],
  PD: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 4 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 5, to: 5 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 6, to: 6 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 3, toEnd: 1 },
  ],
  BL1: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 4 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 5, to: 5 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 6, to: 6 },
    { id: "playoff", label: "Relegation play-off", short: "PO", color: "#fbbf24", fromEnd: 3, toEnd: 3 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 2, toEnd: 1 },
  ],
  SA: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 4 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 5, to: 5 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 6, to: 6 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 3, toEnd: 1 },
  ],
  FL1: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 3 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 4, to: 4 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 5, to: 5 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 3, toEnd: 1 },
  ],
  DED: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 2 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 3, to: 3 },
    { id: "playoff", label: "Relegation play-off", short: "PO", color: "#fbbf24", fromEnd: 3, toEnd: 3 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 2, toEnd: 1 },
  ],
  CL: [
    { id: "r16", label: "Round of 16", short: "R16", color: "#34d399", from: 1, to: 8 },
    { id: "kopo", label: "Knockout play-offs", short: "PO", color: "#fbbf24", from: 9, to: 24 },
    { id: "out", label: "Eliminated", short: "OUT", color: "#64748b", from: 25, to: 99 },
  ],
};

const WC_GROUP_ZONES = [
  { id: "adv", label: "Knockout stage", short: "KO", color: "#34d399", from: 1, to: 2 },
];

function zoneForRank(compCode, rank, teamCount) {
  const zones = STANDING_ZONES[compCode];
  if (!zones || !rank || !teamCount) return null;
  for (const z of zones) {
    if (z.fromEnd != null) {
      const rankHi = teamCount - z.fromEnd + 1;
      const rankLo = teamCount - (z.toEnd ?? 1) + 1;
      if (rank >= rankHi && rank <= rankLo) {
        return { id: z.id, label: z.label, short: z.short, color: z.color };
      }
    } else if (rank >= z.from && rank <= z.to) {
      return { id: z.id, label: z.label, short: z.short, color: z.color };
    }
  }
  return null;
}

function standingLegend(compCode) {
  const zones = STANDING_ZONES[compCode] ?? [];
  const seen = new Set();
  return zones.filter((z) => {
    if (seen.has(z.id)) return false;
    seen.add(z.id);
    return true;
  }).map(({ id, label, short, color }) => ({ id, label, short, color }));
}

function rowZone(compCode, row, teamCount) {
  return row.zone ?? zoneForRank(compCode, row.rank, teamCount);
}

// ─── Suggestion chips ─────────────────────────────────────────────────────
const CHIPS = [
  "Predict Mexico vs USA",
  "Predict Spain vs Germany",
  "Predict Arsenal vs Chelsea",
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

const COMP_OPTIONS = [
  ["WC", "🌍 World Cup"], ["PL", "🏴󠁧󠁢󠁥󠁮󠁧󠁿 PL"], ["PD", "🇪🇸 La Liga"],
  ["BL1", "🇩🇪 Bundesliga"], ["SA", "🇮🇹 Serie A"], ["FL1", "🇫🇷 Ligue 1"], ["CL", "⭐ CL"],
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

const VALID_COMPS = new Set(["WC", "PL", "PD", "BL1", "SA", "FL1", "CL", "DED"]);
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

/** Local calendar date YYYY-MM-DD — matches what fmtDate shows to the user. */
function localDayKey(iso) {
  if (!iso) return "TBD";
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function dayHeaderLabel(dayKey) {
  if (dayKey === "TBD") return "TBD";
  const [y, m, d] = dayKey.split("-").map(Number);
  const target = new Date(y, m - 1, d);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = Math.round((target - today) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  return target.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

// Demo data — only used when VITE_API_BASE is empty (local preview).
const DEMO_FIXTURES = [
  { home: "Mexico", away: "South Africa", match_date: "2026-06-11T19:00:00Z", stage: "group" },
  { home: "South Korea", away: "Czechia", match_date: "2026-06-12T02:00:00Z", stage: "group" },
  { home: "United States", away: "Paraguay", match_date: "2026-06-13T01:00:00Z", stage: "group" },
  { home: "Brazil", away: "Morocco", match_date: "2026-06-13T22:00:00Z", stage: "group" },
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

function PredictionCard({ p, home, away, comp = "WC", neutral = null }) {
  const color = outcomeColor(p.prediction, home, away);
  const [copied, setCopied] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState(null);

  function share() {
    const url = buildPredictUrl(home, away, { comp, neutral });
    const txt = `${flag(home)}${home} ${pct(p.home_win_prob)} · Draw ${pct(p.draw_prob)} · ${flag(away)}${away} ${pct(p.away_win_prob)}\nPrediction: ${p.prediction} (${pct(p.confidence)} confidence)\n${url}\nvia FootballMind`;
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
        <ProbBar home={p.home_win_prob} draw={p.draw_prob} away={p.away_win_prob} homeName={home} awayName={away} />
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

      <CardPredictedLineups home={home} away={away} comp={comp} />

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

function RankingsPanel({ apiBase, offline }) {
  const [rows, setRows] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);

  function load() {
    if (loaded || offline || !apiBase) return;
    fetch(`${apiBase}/api/rankings?comp=WC&limit=48`)
      .then((r) => r.json())
      .then((d) => { setRows(d.rankings ?? []); setLoaded(true); })
      .catch(() => setLoaded(true));
  }

  if (!open) {
    return (
      <button onClick={() => { setOpen(true); load(); }}
        className="flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition-opacity hover:opacity-70"
        style={{ borderColor: C.line, background: C.panel }}>
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          🏆 WC Power Rankings
        </span>
        <span className="text-xs" style={{ color: C.mute }}>show ▾</span>
      </button>
    );
  }

  return (
    <div className="rounded-xl border" style={{ borderColor: C.line, background: C.panel }}>
      <button onClick={() => setOpen(false)}
        className="flex w-full items-center justify-between border-b px-4 py-2.5 text-left transition-opacity hover:opacity-70"
        style={{ borderColor: C.line }}>
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          🏆 WC Power Rankings
        </span>
        <span className="text-xs" style={{ color: C.mute }}>hide ▴</span>
      </button>
      {rows.length === 0 ? (
        <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>
          {offline ? "Available when backend is connected." : "Run seed-elo + sync to populate."}
        </div>
      ) : (
        <div className="divide-y" style={{ divideColor: C.line }}>
          {rows.map((r) => (
            <div key={r.rank} className="flex items-center gap-3 px-4 py-1.5"
              style={{ borderTop: r.rank > 1 ? `1px solid ${C.line}` : "none" }}>
              <span className="w-5 shrink-0 text-[11px] tabular-nums text-right" style={{ color: C.mute }}>{r.rank}</span>
              <span className="flex-1 text-xs" style={{ color: C.chalk }}>{flag(r.team)}{r.team}</span>
              {/* Strength bar */}
              <div className="h-1.5 w-20 overflow-hidden rounded-full" style={{ background: C.line }}>
                <div className="h-full rounded-full" style={{ width: `${Math.round(r.strength * 100)}%`, background: C.home }} />
              </div>
              <span className="w-12 shrink-0 text-right text-[11px] tabular-nums" style={{ color: C.mute }}>{r.rating}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const FIXTURE_TABS = [
  { code: "WC",  label: "🌍 WC"         },
  { code: "PL",  label: "🏴󠁧󠁢󠁥󠁮󠁧󠁿 PL"          },
  { code: "PD",  label: "🇪🇸 La Liga"   },
  { code: "BL1", label: "🇩🇪 Bundesliga" },
  { code: "SA",  label: "🇮🇹 Serie A"   },
  { code: "FL1", label: "🇫🇷 Ligue 1"   },
  { code: "CL",  label: "⭐ CL"         },
  { code: "DED", label: "🇳🇱 Eredivisie" },
];

const COMP_LABELS = {
  WC: "World Cup", PL: "Premier League", PD: "La Liga", BL1: "Bundesliga",
  SA: "Serie A", FL1: "Ligue 1", CL: "Champions League", DED: "Eredivisie",
};

function FixtureRow({ f, onClick }) {
  return (
    <button onClick={() => onClick(f)}
      className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-opacity hover:opacity-70"
      style={{ background: "transparent" }}>
      <span className="shrink-0 rounded px-2 py-0.5 text-center text-[10px] font-semibold"
        style={{ background: C.line, color: C.mute, minWidth: "2.25rem" }}>
        {STAGE_BADGE[f.stage] ?? "GS"}
      </span>
      <span className="flex min-w-0 flex-1 items-center gap-1 text-xs font-medium" style={{ color: C.chalk }}>
        <span className="truncate">{flag(f.home)}{f.home}</span>
        <span className="shrink-0 text-[10px]" style={{ color: C.mute }}>vs</span>
        <span className="truncate">{flag(f.away)}{f.away}</span>
      </span>
      {f.live && <span className="shrink-0 animate-pulse text-[9px] font-bold" style={{ color: C.away }}>LIVE</span>}
      {f.home_goals != null
        ? <span className="shrink-0 text-xs font-bold tabular-nums" style={{ color: C.home }}>{f.home_goals}–{f.away_goals}</span>
        : <span className="shrink-0 text-[10px] whitespace-nowrap" style={{ color: C.mute }}>{fmtDate(f.match_date)}</span>}
    </button>
  );
}

function PredictionResultsView({ apiBase, onSummary }) {
  const [rows, setRows] = useState(null);

  function load() {
    if (!apiBase) { setRows([]); return; }
    setRows(null);
    fetch(`${apiBase}/api/predictions?finished=1&limit=40`)
      .then((r) => r.json())
      .then((d) => {
        setRows(d.results ?? []);
        if (d.summary && onSummary) onSummary(d.summary);
      })
      .catch(() => setRows([]));
  }

  useEffect(() => { load(); }, [apiBase]);

  useEffect(() => {
    if (!apiBase) return;
    const id = setInterval(load, 90000);
    return () => clearInterval(id);
  }, [apiBase]);

  if (rows === null) {
    return <div className="px-4 py-4 text-center text-xs" style={{ color: C.mute }}>Loading results…</div>;
  }
  if (rows.length === 0) {
    return (
      <div className="px-4 py-5 text-center text-xs leading-relaxed" style={{ color: C.mute }}>
        No finished matches yet. Once a game you predicted is played and synced, it’ll show here with the score and whether we got it right.
      </div>
    );
  }

  return (
    <div className="divide-y" style={{ borderColor: C.line }}>
      {rows.map((r) => {
        const predColor = outcomeColor(r.predicted, r.home, r.away);
        const ok = r.was_correct;
        return (
          <div key={r.id} className="px-4 py-3 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: C.mute }}>
                {r.match_date ? fmtDate(r.match_date) : "Final"}
              </span>
              <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold"
                style={{
                  background: ok ? "rgba(52,211,153,0.15)" : "rgba(244,161,82,0.15)",
                  color: ok ? C.home : C.away,
                }}>
                {ok ? "✓ Correct" : "✗ Miss"}
              </span>
            </div>
            <div className="text-sm font-semibold" style={{ color: C.chalk }}>
              {flag(r.home)}{r.home} {r.score} {flag(r.away)}{r.away}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px]">
              <span style={{ color: C.mute }}>
                Predicted:{" "}
                <span className="font-semibold" style={{ color: predColor }}>
                  {r.predicted === r.home ? `${flag(r.home)}${r.predicted}` : r.predicted === r.away ? `${flag(r.away)}${r.predicted}` : r.predicted}
                  {" "}({pct(r.predicted_confidence)})
                </span>
              </span>
              <span style={{ color: C.mute }}>
                Actual:{" "}
                <span className="font-semibold" style={{ color: C.chalk }}>
                  {r.actual === r.home ? `${flag(r.home)}${r.actual}` : r.actual === r.away ? `${flag(r.away)}${r.actual}` : r.actual}
                </span>
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FixturesPanel({ initialWc, initialPl, sidebarLoaded, onClickFixture, apiBase, onSummary, onCompChange }) {
  const [view, setView] = useState("upcoming");
  const [tab, setTab] = useState("WC");
  // Lazy-loaded tabs only (WC/PL come from parent after async fetch)
  const [cache, setCache] = useState({});
  const [loaded, setLoaded] = useState(new Set());
  const [loading, setLoading] = useState(false);

  function rowsFor(code) {
    if (code === "WC") return initialWc ?? [];
    if (code === "PL") return initialPl ?? [];
    return cache[code] ?? [];
  }

  function switchTab(code) {
    setTab(code);
    onCompChange?.(code);
    if (code === "WC" || code === "PL" || loaded.has(code) || !apiBase) return;
    setLoading(true);
    fetch(`${apiBase}/api/fixtures?comp=${code}&limit=16`)
      .then((r) => r.json())
      .then((d) => setCache((c) => ({ ...c, [code]: d.fixtures ?? [] })))
      .catch(() => setCache((c) => ({ ...c, [code]: [] })))
      .finally(() => { setLoaded((s) => new Set(s).add(code)); setLoading(false); });
  }

  const rows = rowsFor(tab);
  const waitingParent = (tab === "WC" || tab === "PL") && apiBase && !sidebarLoaded;

  return (
    <div className="rounded-xl border" style={{ borderColor: C.line, background: C.panel }}>
      <div className="border-b px-4 pt-3 pb-0" style={{ borderColor: C.line }}>
        <div className="mb-2 flex gap-1">
          {[["upcoming", "📅 Upcoming"], ["results", "✅ Results"]].map(([k, lbl]) => (
            <button key={k} onClick={() => setView(k)}
              className="rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
              style={{ background: view === k ? C.home : C.line, color: view === k ? "#08120F" : C.mute }}>
              {lbl}
            </button>
          ))}
        </div>
        {view === "upcoming" && (
          <>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
              Upcoming Fixtures
            </div>
            <div className="flex gap-1 overflow-x-auto pb-2" style={{ scrollbarWidth: "none" }}>
              {FIXTURE_TABS.map(({ code, label }) => (
                <button key={code} onClick={() => switchTab(code)}
                  className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
                  style={{ background: code === tab ? C.home : C.line, color: code === tab ? "#08120F" : C.mute }}>
                  {label}
                </button>
              ))}
            </div>
          </>
        )}
        {view === "results" && (
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
            Our Predictions vs Results
          </div>
        )}
      </div>
      <div>
        {view === "results" ? (
          <PredictionResultsView apiBase={apiBase} onSummary={onSummary} />
        ) : loading || waitingParent ? (
          <div className="px-4 py-4 text-center text-xs" style={{ color: C.mute }}>Loading…</div>
        ) : rows.length === 0 ? (
          <div className="px-4 py-4 text-center text-xs" style={{ color: C.mute }}>No upcoming fixtures found.</div>
        ) : (() => {
          // Group by local calendar date (same timezone as fmtDate), up to 4 days
          const byDate = [];
          const seen = new Set();
          [...rows].sort((a, b) => (a.match_date || "").localeCompare(b.match_date || ""))
            .forEach((f) => {
              const day = localDayKey(f.match_date);
              if (!seen.has(day)) { seen.add(day); byDate.push({ day, games: [] }); }
              byDate[byDate.length - 1].games.push(f);
            });
          const days = byDate.slice(0, 5);
          return days.map(({ day, games }) => {
            const label = dayHeaderLabel(day);
            return (
              <div key={day}>
                <div className="border-t px-4 py-1 text-[10px] font-semibold uppercase tracking-wider"
                  style={{ borderColor: C.line, background: C.panel2, color: C.mute }}>
                  {label} · {games.length} {games.length === 1 ? "match" : "matches"}
                </div>
                {games.map((f, i) => (
                  <div key={i} style={{ borderTop: `1px solid ${C.line}` }}>
                    <FixtureRow f={f} onClick={onClickFixture} />
                  </div>
                ))}
              </div>
            );
          });
        })()}
      </div>
    </div>
  );
}

const ROUND_LABEL = {
  round_of_32: "Round of 32", round_of_16: "Round of 16",
  quarter_final: "Quarter-Finals", semi_final: "Semi-Finals",
  final: "Final",
};
const BRACKET_ORDER = ["final", "semi_final", "quarter_final", "round_of_16", "round_of_32"];

/** Normalise API bracket to ordered [{round, matches}] (array or legacy object). */
function normaliseBracket(data) {
  if (Array.isArray(data)) {
    return data.filter((r) => r.round !== "third_place" && r.matches?.length);
  }
  const b = data || {};
  return BRACKET_ORDER.filter((k) => b[k]?.length).map((k) => ({ round: k, matches: b[k] }));
}

function BracketPanel({ apiBase, offline }) {
  const [bracket, setBracket] = useState(null);
  const [open, setOpen] = useState(false);
  const [comp, setComp] = useState("WC");

  function load(c) {
    if (!apiBase || offline) return;
    fetch(`${apiBase}/api/bracket?comp=${c}`)
      .then((r) => r.json())
      .then((d) => setBracket(normaliseBracket(d.bracket)))
      .catch(() => setBracket([]));
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && bracket === null) load(comp);
  }

  const rounds = bracket ?? [];

  return (
    <div className="rounded-xl border" style={{ borderColor: C.line, background: C.panel }}>
      <button onClick={toggle}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left transition-opacity hover:opacity-70"
        style={{ borderBottom: open ? `1px solid ${C.line}` : "none" }}>
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          🏆 Tournament Bracket
        </span>
        <span className="text-xs" style={{ color: C.mute }}>{open ? "hide ▴" : "show ▾"}</span>
      </button>

      {open && (
        <div>
          {/* Comp selector */}
          <div className="flex gap-1 overflow-x-auto px-3 pt-2 pb-1" style={{ scrollbarWidth: "none" }}>
            {[["WC", "🌍 World Cup"], ["CL", "⭐ Champions League"]].map(([c, lbl]) => (
              <button key={c} onClick={() => { setComp(c); setBracket(null); load(c); }}
                className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
                style={{ background: c === comp ? C.home : C.line, color: c === comp ? "#08120F" : C.mute }}>
                {lbl}
              </button>
            ))}
          </div>

          {bracket === null ? (
            <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>Loading…</div>
          ) : rounds.length === 0 ? (
            <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>
              No knockout matches yet — check back once the group stage finishes.
            </div>
          ) : rounds.map(({ round, matches }) => (
            <div key={round}>
              <div className="border-t px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider"
                style={{ borderColor: C.line, color: C.mute, background: C.panel2 }}>
                {ROUND_LABEL[round] ?? round}
              </div>
              {matches.map((f, i) => (
                <div key={i} style={{ borderTop: `1px solid ${C.line}` }}>
                  <div className="flex items-center gap-3 px-4 py-2.5">
                    <span className="flex min-w-0 flex-1 items-center gap-1 text-xs" style={{ color: C.chalk }}>
                      <span className="truncate font-medium">{flag(f.home)}{f.home}</span>
                      <span className="shrink-0" style={{ color: C.mute }}>vs</span>
                      <span className="truncate font-medium">{flag(f.away)}{f.away}</span>
                    </span>
                    {f.home_goals != null
                      ? <span className="shrink-0 text-xs font-bold tabular-nums"
                          style={{ color: C.home }}>{f.home_goals}–{f.away_goals}</span>
                      : f.match_date
                        ? <span className="shrink-0 text-[10px] whitespace-nowrap" style={{ color: C.mute }}>
                            {fmtDate(f.match_date)}
                          </span>
                        : <span className="shrink-0 text-[10px]" style={{ color: C.mute }}>TBD</span>}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const POS_META = {
  GK:  { label: "GK",  bg: "#B8860B", fg: "#08120F" },
  DEF: { label: "DEF", bg: "#1A6B47", fg: "#E8F5EE" },
  CB:  { label: "CB",  bg: "#1A6B47", fg: "#E8F5EE" },
  LB:  { label: "LB",  bg: "#1E7A52", fg: "#E8F5EE" },
  RB:  { label: "RB",  bg: "#1E7A52", fg: "#E8F5EE" },
  MID: { label: "MID", bg: "#1A3D6B", fg: "#DCE8FF" },
  CM:  { label: "CM",  bg: "#1A3D6B", fg: "#DCE8FF" },
  CDM: { label: "CDM", bg: "#153256", fg: "#DCE8FF" },
  CAM: { label: "CAM", bg: "#24508F", fg: "#DCE8FF" },
  FWD: { label: "FWD", bg: "#7B1F1F", fg: "#FFE0E0" },
  ST:  { label: "ST",  bg: "#7B1F1F", fg: "#FFE0E0" },
  WING:{ label: "WNG", bg: "#9B3030", fg: "#FFE0E0" },
  "?": { label: "?",   bg: "#333",    fg: "#aaa"    },
};
const POS_TABS = [
  { key: "ALL", label: "All" },
  { key: "FWD", label: "⚡ Forwards" },
  { key: "MID", label: "🎯 Midfielders" },
  { key: "DEF", label: "🛡 Defenders" },
  { key: "GK",  label: "🧤 Keepers" },
];

function SidebarModeToggle({ mode, setMode }) {
  return (
    <div className="flex rounded-lg border p-0.5" style={{ borderColor: C.line, background: C.panel2 }}>
      {[
        { key: "matches", label: "⚽ Matches" },
        { key: "players", label: "👤 Players" },
      ].map(({ key, label }) => (
        <button key={key} onClick={() => setMode(key)}
          className="flex-1 rounded-md px-3 py-2 text-xs font-semibold transition-colors"
          style={{
            background: mode === key ? C.home : "transparent",
            color: mode === key ? "#08120F" : C.mute,
          }}>
          {label}
        </button>
      ))}
    </div>
  );
}

function PlayerCard({ p, onSelect, compact }) {
  const pm = POS_META[p.position] ?? POS_META["?"];
  return (
    <button type="button" onClick={() => onSelect?.(p)}
      className={`rounded-lg border text-left transition-opacity hover:opacity-80 w-full ${compact ? "p-2" : "p-2.5 flex flex-col gap-1"}`}
      style={{ borderColor: C.line, background: C.panel2 }}>
      <div className="flex items-start justify-between gap-1">
        <span className={`font-semibold leading-tight ${compact ? "text-[11px]" : "text-xs"}`} style={{ color: C.chalk }}>
          {p.name}
        </span>
        <span className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase"
          style={{ background: pm.bg, color: pm.fg }}>
          {pm.label}
        </span>
      </div>
      <div className="flex items-center justify-between gap-1 mt-0.5">
        <span className="text-[10px] truncate" style={{ color: C.mute }}>
          {flag(p.team)}{p.team}
          {p.club_team && p.club_team !== p.team
            ? ` · ${p.club_team}`
            : p.nationality && p.nationality !== p.team ? ` · ${p.nationality}` : ""}
        </span>
        {p.age && <span className="shrink-0 text-[10px]" style={{ color: C.mute }}>{p.age}y</span>}
      </div>
      {(p.goals != null || p.assists != null) && p.position !== "GK" && p.position !== "DEF" && (
        <div className="text-[10px] font-semibold tabular-nums mt-0.5" style={{ color: C.home }}>
          {p.goals ?? 0}G{p.assists != null ? ` · ${p.assists}A` : ""}
          {p.appearances != null ? ` · ${p.appearances} apps` : ""}
        </div>
      )}
      {p.position === "GK" && (p.ga_per_game != null || p.saves != null) && (
        <div className="text-[10px] font-semibold tabular-nums mt-0.5" style={{ color: C.home }}>
          {p.saves != null ? `${p.saves} saves` : ""}
          {p.saves != null && p.ga_per_game != null ? " · " : ""}
          {p.ga_per_game != null ? `${p.ga_per_game} GA/game` : ""}
          {p.clean_sheets != null && p.team_gp ? ` · ${p.clean_sheets} CS` : ""}
        </div>
      )}
      {p.position === "DEF" && p.ga_per_game != null && (
        <div className="text-[10px] font-semibold tabular-nums mt-0.5" style={{ color: C.home }}>
          {p.clean_sheets != null ? `${p.clean_sheets} clean sheets` : ""}
          {p.clean_sheets != null ? " · " : ""}
          {p.ga_per_game} GA/game
          {p.appearances != null ? ` · ${p.appearances} apps` : ""}
        </div>
      )}
      {p.standout_rating != null && !compact && (
        <div className="mt-1 flex items-center gap-1.5">
          <div className="h-1 flex-1 overflow-hidden rounded-full" style={{ background: C.line }}>
            <div className="h-full rounded-full"
              style={{
                width: `${Math.min(100, Math.round(p.standout_rating))}%`,
                background: pm.bg === "#7B1F1F" ? C.away : pm.bg === "#1A6B47" ? C.home : C.draw,
              }} />
          </div>
          <span className="shrink-0 text-[9px] font-bold tabular-nums" style={{ color: C.mute }}>
            {Math.round(p.standout_rating)}
          </span>
        </div>
      )}
      {p.team_rating != null && !compact && p.standout_rating == null && !(p.goals != null) && (
        <div className="h-0.5 w-full overflow-hidden rounded-full mt-1" style={{ background: C.line }}>
          <div className="h-full rounded-full"
            style={{
              width: `${Math.min(100, Math.round((p.team_rating - 1200) / 8))}%`,
              background: pm.bg === "#7B1F1F" ? C.away : pm.bg === "#1A6B47" ? C.home : C.draw,
            }} />
        </div>
      )}
    </button>
  );
}

function PredictedPitch({ rows, formation, compact = false, label = "Predicted XI" }) {
  const displayRows = [...(rows ?? [])].reverse();
  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: "#2a5c3e", background: "linear-gradient(180deg, #1a4d35 0%, #143d2a 100%)" }}>
      <div className="px-3 py-2 flex items-center justify-between border-b" style={{ borderColor: "#2a5c3e55" }}>
        <span className="text-[11px] font-bold tracking-wider" style={{ color: "#b8e6c8" }}>{formation}</span>
        <span className="text-[9px] uppercase tracking-wider" style={{ color: "#7ab896" }}>{label}</span>
      </div>
      <div className={`px-2 py-3 space-y-2 flex flex-col justify-around ${compact ? "min-h-[120px]" : "min-h-[220px]"}`}>
        {displayRows.map((row, ri) => (
          <div key={ri} className="flex justify-center gap-1.5 flex-wrap">
            {row.players.map((p, pi) => {
              const posKey = p.position ?? row.line;
              const pm = POS_META[posKey] ?? POS_META["?"];
              return (
              <div key={pi} className={`flex flex-col items-center ${compact ? "w-[52px]" : "w-[72px]"}`}>
                <div className={`rounded-full flex items-center justify-center font-bold border-2 ${compact ? "w-7 h-7 text-[7px]" : "w-9 h-9 text-[8px]"}`}
                  style={{ background: "#0d2818", borderColor: "#4ade80", color: "#ecfdf5" }}>
                  {pm.label}
                </div>
                <span className={`mt-1 font-semibold text-center leading-tight line-clamp-2 w-full ${compact ? "text-[8px]" : "text-[9px]"}`}
                  style={{ color: "#f0fdf4" }}>
                  {p.shirt_number ? `${p.shirt_number} ` : ""}{p.name.split(" ").pop()}
                </span>
                {!compact && (
                  <span className="text-[8px] tabular-nums" style={{ color: "#86efac88" }}>
                    {p.rating != null ? p.rating.toFixed(1) : p.score != null ? Math.round(p.score) : ""}
                  </span>
                )}
              </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function MiniLineupColumn({ teamName, data, loading }) {
  if (loading) {
    return (
      <div className="flex-1 min-w-0 text-[10px]" style={{ color: C.mute }}>
        {flag(teamName)}{teamName.split(" ")[0]}…
      </div>
    );
  }
  if (!data?.rows?.length) return null;
  const starters = data.rows.flatMap((r) => r.players.map((p) => p.name.split(" ").pop()));
  return (
    <div className="flex-1 min-w-0">
      <div className="text-[10px] font-semibold truncate" style={{ color: C.chalk }}>
        {flag(teamName)}{teamName.split(" ")[0]} · {data.formation}
      </div>
      <div className="mt-1 text-[9px] leading-snug" style={{ color: C.mute }}>
        {starters.join(", ")}
      </div>
      {data.unavailable?.length > 0 && (
        <div className="mt-1 text-[9px] leading-snug" style={{ color: C.away }}>
          Out: {data.unavailable.map((u) => u.name.split(" ").pop()).join(", ")}
        </div>
      )}
    </div>
  );
}

function CardPredictedLineups({ home, away, comp }) {
  const [homeLineup, setHomeLineup] = useState(null);
  const [awayLineup, setAwayLineup] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!API_BASE || !home || !away) return;
    let cancelled = false;
    setLoading(true);
    setHomeLineup(null);
    setAwayLineup(null);
    const c = comp || "WC";
    Promise.all([
      fetch(`${API_BASE}/api/players/predicted-lineup?team=${encodeURIComponent(home)}&comp=${c}`)
        .then((r) => (r.ok ? r.json() : null)),
      fetch(`${API_BASE}/api/players/predicted-lineup?team=${encodeURIComponent(away)}&comp=${c}`)
        .then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([h, a]) => {
        if (cancelled) return;
        setHomeLineup(h?.error ? null : h);
        setAwayLineup(a?.error ? null : a);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [home, away, comp]);

  const hasLineup = homeLineup?.rows?.length || awayLineup?.rows?.length;
  if (!loading && !hasLineup) return null;

  return (
    <div className="mt-3 pt-2.5 border-t" style={{ borderColor: C.line }}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          ⚽ Predicted XI
        </span>
        {hasLineup && (
          <button type="button" onClick={() => setExpanded((v) => !v)}
            className="text-[10px] font-medium transition-opacity hover:opacity-70"
            style={{ color: C.home }}>
            {expanded ? "Compact" : "Pitch view"}
          </button>
        )}
      </div>
      {expanded && hasLineup ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {homeLineup?.rows?.length > 0 && (
            <PredictedPitch rows={homeLineup.rows} formation={homeLineup.formation} compact />
          )}
          {awayLineup?.rows?.length > 0 && (
            <PredictedPitch rows={awayLineup.rows} formation={awayLineup.formation} compact />
          )}
        </div>
      ) : (
        <div className="flex gap-3">
          <MiniLineupColumn teamName={home} data={homeLineup} loading={loading} />
          <MiniLineupColumn teamName={away} data={awayLineup} loading={loading} />
        </div>
      )}
    </div>
  );
}

function AvailabilityAdminPanel({ team, comp, apiBase, adminKey, onUpdated }) {
  const [player, setPlayer] = useState("");
  const [status, setStatus] = useState("injured");
  const [reason, setReason] = useState("");
  const [flags, setFlags] = useState([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!adminKey || !apiBase || !team) return;
    fetch(`${apiBase}/api/players/availability?team=${encodeURIComponent(team)}&comp=${comp}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setFlags(d?.flags ?? []))
      .catch(() => setFlags([]));
  }, [team, comp, apiBase, adminKey, msg]);

  async function submit(e) {
    e.preventDefault();
    if (!player.trim() || busy) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch(`${apiBase}/api/admin/availability`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${adminKey}` },
        body: JSON.stringify({ player: player.trim(), team, comp, status, reason: reason.trim() || null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.message || "Failed");
      setPlayer("");
      setReason("");
      setMsg(`Flagged ${data.player} as ${data.status}`);
      onUpdated?.();
    } catch (err) {
      setMsg(err.message || "Could not save flag");
    } finally {
      setBusy(false);
    }
  }

  async function removeFlag(name) {
    if (busy) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch(`${apiBase}/api/admin/availability`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${adminKey}` },
        body: JSON.stringify({ player: name, team, comp }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed");
      setMsg(`Cleared flag for ${data.player}`);
      onUpdated?.();
    } catch (err) {
      setMsg(err.message || "Could not clear flag");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border p-2.5 space-y-2" style={{ borderColor: C.line, background: C.panel2 }}>
      <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: C.mute }}>
        Admin · flag player out
      </div>
      <form onSubmit={submit} className="space-y-2">
        <input
          value={player}
          onChange={(e) => setPlayer(e.target.value)}
          placeholder="Player name"
          className="w-full rounded-md px-2 py-1.5 text-xs outline-none"
          style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}
        />
        <div className="flex gap-2">
          <select value={status} onChange={(e) => setStatus(e.target.value)}
            className="flex-1 rounded-md px-2 py-1.5 text-xs outline-none"
            style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}>
            <option value="injured">Injured</option>
            <option value="doubtful">Doubtful</option>
            <option value="suspended">Suspended (manual)</option>
          </select>
          <button type="submit" disabled={busy}
            className="shrink-0 rounded-md px-3 py-1.5 text-[10px] font-semibold disabled:opacity-50"
            style={{ background: C.home, color: "#08120F" }}>
            Save
          </button>
        </div>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason (optional) e.g. Hamstring"
          className="w-full rounded-md px-2 py-1.5 text-xs outline-none"
          style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}
        />
      </form>
      {msg && <div className="text-[10px]" style={{ color: C.mute }}>{msg}</div>}
      {flags.length > 0 && (
        <div className="space-y-1 pt-1 border-t" style={{ borderColor: C.line }}>
          <div className="text-[9px] uppercase tracking-wider" style={{ color: C.mute }}>Manual flags</div>
          {flags.map((f) => (
            <div key={f.player} className="flex items-center justify-between gap-2 text-[10px]">
              <span style={{ color: C.chalk }}>{f.player} · {f.status}{f.reason ? ` (${f.reason})` : ""}</span>
              <button type="button" onClick={() => removeFlag(f.player)} disabled={busy}
                className="shrink-0 text-[9px] font-semibold hover:opacity-70"
                style={{ color: C.away }}>
                Clear
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PlayersSidebar({ apiBase, offline, onAsk, onCompChange, adminKey }) {
  const [comp, setComp] = useState("WC");
  const [posTab, setPosTab] = useState("ALL");
  const [tab, setTab] = useState("standouts");
  const [standouts, setStandouts] = useState(null);
  const [teams, setTeams] = useState([]);
  const [team, setTeam] = useState("");
  const [squad, setSquad] = useState(null);
  const [search, setSearch] = useState("");
  const [searchHits, setSearchHits] = useState(null);
  const [scorers, setScorers] = useState(null);
  const [lineup, setLineup] = useState(null);
  const [lineupView, setLineupView] = useState("predicted");

  function loadPredictedLineup(t, c) {
    if (!apiBase || offline || !t) { setLineup(null); return; }
    setLineup(null);
    fetch(`${apiBase}/api/players/predicted-lineup?team=${encodeURIComponent(t)}&comp=${c}`)
      .then((r) => r.json())
      .then((d) => (d.error ? setLineup({ error: d.error }) : setLineup(d)))
      .catch(() => setLineup({ error: "Failed to load predicted lineup" }));
  }

  function reloadLineup() {
    if (team) loadPredictedLineup(team, comp);
  }

  function loadScorers(c) {
    if (!apiBase || offline) { setScorers([]); return; }
    setScorers(null);
    fetch(`${apiBase}/api/players/scorers?comp=${c}&limit=25`)
      .then((r) => r.json())
      .then((d) => setScorers(d.scorers ?? []))
      .catch(() => setScorers([]));
  }

  function loadStandouts(c) {
    if (!apiBase || offline) { setStandouts([]); return; }
    setStandouts(null);
    fetch(`${apiBase}/api/standouts?comp=${c}&limit=40`)
      .then((r) => r.json())
      .then((d) => setStandouts(d.standouts ?? []))
      .catch(() => setStandouts([]));
  }

  function loadTeams(c) {
    if (!apiBase || offline) { setTeams([]); return; }
    fetch(`${apiBase}/api/players/teams?comp=${c}`)
      .then((r) => r.json())
      .then((d) => {
        const list = d.teams ?? [];
        setTeams(list);
        const preferred = list.includes("Spain") ? "Spain" : list[0];
        if (list.length && (!team || !list.includes(team))) setTeam(preferred);
      })
      .catch(() => setTeams([]));
  }

  function loadSquad(t, c) {
    if (!apiBase || offline || !t) { setSquad(null); return; }
    setSquad(null);
    fetch(`${apiBase}/api/players/squad?team=${encodeURIComponent(t)}&comp=${c}`)
      .then((r) => r.json())
      .then((d) => (d.error ? setSquad({ error: d.error }) : setSquad(d)))
      .catch(() => setSquad({ error: "Failed to load squad" }));
  }

  useEffect(() => {
    loadStandouts(comp);
    loadTeams(comp);
    if (tab === "scorers") loadScorers(comp);
  }, [comp, apiBase, offline]);

  useEffect(() => {
    if (tab === "squad" && team) loadSquad(team, comp);
    if (tab === "scorers") loadScorers(comp);
    if (tab === "lineup" && team) loadPredictedLineup(team, comp);
  }, [tab, team, comp, apiBase, offline]);

  function pickComp(c) {
    setComp(c);
    setPosTab("ALL");
    onCompChange?.(c);
  }

  function askPlayer(p) {
    onAsk(`Tell me about ${p.name} (${p.team}) — their role, strengths, and why they matter`);
  }

  function askTeamLineup(t) {
    onAsk(`What's ${t}'s most likely starting XI for ${comp}? Who's out injured or suspended?`);
  }

  function askTeamSquad(t) {
    onAsk(`Explain ${t}'s squad — key players by position and why this team works tactically`);
  }

  function runSearch(e) {
    e?.preventDefault();
    const q = search.trim();
    if (!q || !apiBase || offline) return;
    setSearchHits(null);
    fetch(`${apiBase}/api/players/search?q=${encodeURIComponent(q)}&comp=${comp}`)
      .then((r) => r.json())
      .then((d) => setSearchHits(d.players ?? []))
      .catch(() => setSearchHits([]));
  }

  const visibleStandouts = standouts
    ? (posTab === "ALL" ? standouts : standouts.filter((p) => p.position === posTab))
    : [];

  const squadList = squad?.squad ?? [];
  const squadByPos = squad?.by_position ?? {};

  return (
    <div className="rounded-xl border flex flex-col max-h-[calc(100vh-8rem)]" style={{ borderColor: C.line, background: C.panel }}>
      <div className="border-b px-4 py-2.5 shrink-0" style={{ borderColor: C.line }}>
        <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          Players & Squads
        </div>
        <p className="mt-1 text-[10px]" style={{ color: C.mute }}>
          Tap a player to ask the chat. Standouts: scorers/assists for attackers, clean sheets and low GA for defenders, saves and GA for keepers (max 2 per nation).
        </p>
      </div>

      <div className="border-b px-3 pt-2 pb-2 space-y-1.5 shrink-0" style={{ borderColor: C.line }}>
        <div className="flex gap-1 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
          {COMP_OPTIONS.map(([c, lbl]) => (
            <button key={c} onClick={() => pickComp(c)}
              className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
              style={{ background: c === comp ? C.home : C.line, color: c === comp ? "#08120F" : C.mute }}>
              {lbl}
            </button>
          ))}
        </div>
        <div className="flex gap-1 flex-wrap">
          {[["standouts", "⚡ Standouts"], ["scorers", "🥅 Scorers"], ["lineup", "⚽ Predicted XI"], ["squad", "📋 Squad"]].map(([k, lbl]) => (
            <button key={k} onClick={() => setTab(k)}
              className="flex-1 min-w-[45%] rounded-md px-2 py-1 text-[11px] font-semibold transition-colors"
              style={{ background: tab === k ? C.home : C.line, color: tab === k ? "#08120F" : C.mute }}>
              {lbl}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {tab === "standouts" && (
          <>
            <div className="flex gap-1 overflow-x-auto px-3 py-2 border-b" style={{ borderColor: C.line, scrollbarWidth: "none" }}>
              {POS_TABS.map(({ key, label }) => (
                <button key={key} onClick={() => setPosTab(key)}
                  className="shrink-0 rounded-md px-2 py-0.5 text-[10px] font-semibold transition-colors"
                  style={{ background: key === posTab ? C.home : C.line, color: key === posTab ? "#08120F" : C.mute }}>
                  {label}
                </button>
              ))}
            </div>
            {standouts === null ? (
              <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>Loading…</div>
            ) : visibleStandouts.length === 0 ? (
              <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>
                {offline || !apiBase ? "Connect to the backend to browse players." : "No squad data — run sync to populate."}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2 p-3">
                {visibleStandouts.map((p, i) => (
                  <PlayerCard key={`${p.name}-${i}`} p={p} onSelect={askPlayer} />
                ))}
              </div>
            )}
          </>
        )}

        {tab === "scorers" && (
          <>
            {scorers === null ? (
              <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>Loading scorers…</div>
            ) : scorers.length === 0 ? (
              <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>
                {offline || !apiBase
                  ? "Connect to the backend."
                  : "No scorer stats yet — run sync to pull league data."}
              </div>
            ) : (
              <div className="divide-y" style={{ borderColor: C.line }}>
                {scorers.map((p) => (
                  <button key={p.rank} type="button" onClick={() => askPlayer(p)}
                    className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:opacity-80"
                    style={{ borderColor: C.line }}>
                    <span className="w-5 shrink-0 text-xs font-bold tabular-nums" style={{ color: C.mute }}>
                      {p.rank}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-semibold truncate" style={{ color: C.chalk }}>{p.name}</div>
                      <div className="text-[10px] truncate" style={{ color: C.mute }}>
                        {flag(p.team)}{p.team}
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-sm font-bold tabular-nums" style={{ color: C.home }}>{p.goals}</div>
                      <div className="text-[10px] tabular-nums" style={{ color: C.mute }}>{p.assists}A</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {tab === "lineup" && (
          <div className="p-3 space-y-3">
            <div className="flex gap-2">
              <select value={team} onChange={(e) => setTeam(e.target.value)}
                className="flex-1 rounded-lg px-2 py-1.5 text-xs outline-none"
                style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}>
                {teams.length === 0
                  ? <option value="">No teams</option>
                  : teams.map((t) => <option key={t} value={t}>{flag(t)}{t}</option>)}
              </select>
              {team && (
                <button type="button" onClick={() => askTeamLineup(team)}
                  className="shrink-0 rounded-lg px-2 py-1.5 text-[10px] font-semibold"
                  style={{ background: C.home, color: "#08120F" }}>
                  Ask AI
                </button>
              )}
            </div>
            {lineup === null ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>Building predicted XI…</div>
            ) : lineup.error ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>{lineup.error}</div>
            ) : (
              <>
                {lineup.confirmed?.rows?.length > 0 && (
                  <div className="flex rounded-lg border p-0.5" style={{ borderColor: C.line, background: C.panel2 }}>
                    {[["predicted", "Predicted"], ["confirmed", "Last match"]].map(([k, lbl]) => (
                      <button key={k} type="button" onClick={() => setLineupView(k)}
                        className="flex-1 rounded-md px-2 py-1.5 text-[10px] font-semibold transition-colors"
                        style={{
                          background: lineupView === k ? C.home : "transparent",
                          color: lineupView === k ? "#08120F" : C.mute,
                        }}>
                        {lbl}
                      </button>
                    ))}
                  </div>
                )}
                {(() => {
                  const showConfirmed = lineupView === "confirmed" && lineup.confirmed?.rows?.length > 0;
                  const view = showConfirmed ? lineup.confirmed : lineup;
                  const matchMeta = showConfirmed ? lineup.confirmed?.match : null;
                  return (
                    <>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px]" style={{ color: C.mute }}>
                        <span>{flag(lineup.team)}{lineup.team}</span>
                        <span>·</span>
                        <span>{
                          showConfirmed
                            ? `Confirmed vs ${matchMeta?.opponent ?? "opponent"}`
                            : lineup.source === "recent_lineup"
                              ? "Based on last match XI"
                              : lineup.source === "recent_formation"
                                ? "Based on recent formation"
                                : "Depth + form model"
                        }</span>
                        {matchMeta?.match_date && showConfirmed && (
                          <>
                            <span>·</span>
                            <span>{matchMeta.match_date.slice(0, 10)}</span>
                          </>
                        )}
                        {!showConfirmed && lineup.next_opponent && (
                          <>
                            <span>·</span>
                            <span>Next: vs {flag(lineup.next_opponent)}{lineup.next_opponent}</span>
                          </>
                        )}
                      </div>
                      {!showConfirmed && !lineup.confirmed?.rows?.length && (
                        <p className="text-[9px] leading-snug" style={{ color: C.mute }}>
                          Model prediction — not official lineups. Confirmed XIs appear when match detail sync includes lineups (paid API tier).
                        </p>
                      )}
                      {lineup.recent_formations?.length > 0 && !showConfirmed && (
                        <div className="text-[10px]" style={{ color: C.mute }}>
                          Recent: {lineup.recent_formations.join(", ")}
                        </div>
                      )}
                      <PredictedPitch
                        rows={view.rows}
                        formation={view.formation}
                        label={showConfirmed ? "Confirmed XI" : "Predicted XI"}
                      />
                    </>
                  );
                })()}
                {lineup.unavailable?.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider" style={{ color: C.away }}>
                      Out ({lineup.unavailable.length})
                    </div>
                    <div className="space-y-1">
                      {lineup.unavailable.map((u) => (
                        <div key={u.player_id} className="flex items-center justify-between rounded-md border px-2 py-1.5 text-[11px]"
                          style={{ borderColor: C.line, background: C.panel2 }}>
                          <span style={{ color: C.chalk }}>{u.name}</span>
                          <span className="shrink-0 ml-2 text-[10px] font-semibold capitalize"
                            style={{ color: u.status === "suspended" ? C.away : u.status === "injured" ? "#e67e22" : C.mute }}>
                            {u.status}{u.reason ? ` · ${u.reason}` : ""}
                            {u.source && u.source !== "manual" ? ` · ${u.source}` : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {lineup.bench?.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider" style={{ color: C.mute }}>
                      Bench
                    </div>
                    <div className="grid grid-cols-2 gap-1">
                      {lineup.bench.map((p) => (
                        <div key={p.name} className="rounded-md border px-2 py-1 text-[10px]"
                          style={{ borderColor: C.line, background: C.panel2, color: C.chalk }}>
                          <span className="font-medium">{p.name}</span>
                          <span className="ml-1" style={{ color: C.mute }}>{p.position}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {adminKey && team && (
                  <AvailabilityAdminPanel
                    team={team}
                    comp={comp}
                    apiBase={apiBase}
                    adminKey={adminKey}
                    onUpdated={reloadLineup}
                  />
                )}
              </>
            )}
          </div>
        )}

        {tab === "squad" && (
          <div className="p-3 space-y-3">
            <div className="flex gap-2">
              <select value={team} onChange={(e) => setTeam(e.target.value)}
                className="flex-1 rounded-lg px-2 py-1.5 text-xs outline-none"
                style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}>
                {teams.length === 0
                  ? <option value="">No teams</option>
                  : teams.map((t) => <option key={t} value={t}>{flag(t)}{t}</option>)}
              </select>
              {team && (
                <button type="button" onClick={() => askTeamSquad(team)}
                  className="shrink-0 rounded-lg px-2 py-1.5 text-[10px] font-semibold"
                  style={{ background: C.home, color: "#08120F" }}>
                  Ask AI
                </button>
              )}
            </div>
            {squad === null ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>Loading squad…</div>
            ) : squad.error ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>{squad.error}</div>
            ) : squadList.length === 0 ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>No squad on file for {team}.</div>
            ) : (
              <>
                <div className="flex items-center justify-between text-[10px]" style={{ color: C.mute }}>
                  <span>{flag(squad.team)}{squad.team}</span>
                  <span>{squad.squad_size} players{squad.team_rating ? ` · Elo ${squad.team_rating}` : ""}</span>
                </div>
                {["GK", "DEF", "MID", "FWD"].map((pos) => {
                  const group = squadByPos[pos];
                  if (!group?.length) return null;
                  const pm = POS_META[pos];
                  return (
                    <div key={pos}>
                      <div className="mb-1 text-[10px] font-bold uppercase tracking-wider"
                        style={{ color: pm.fg, background: pm.bg, display: "inline-block", padding: "2px 6px", borderRadius: 4 }}>
                        {pm.label} ({group.length})
                      </div>
                      <div className="space-y-1 mt-1">
                        {group.map((p) => (
                          <button key={p.name} type="button" onClick={() => askPlayer({ ...p, team: squad.team })}
                            className="flex w-full items-center justify-between rounded-md border px-2 py-1.5 text-left hover:opacity-80"
                            style={{ borderColor: C.line, background: C.panel2 }}>
                            <div className="min-w-0">
                              <div className="text-xs font-medium truncate" style={{ color: C.chalk }}>{p.name}</div>
                              {formatPlayerMeta(p) && (
                                <div className="text-[9px] truncate mt-0.5" style={{ color: C.mute }}>
                                  {formatPlayerMeta(p)}
                                </div>
                              )}
                            </div>
                            <span className="text-[10px] shrink-0 ml-2 text-right" style={{ color: C.mute }}>
                              {p.age ? `${p.age}y` : ""}{p.nationality ? ` · ${p.nationality}` : ""}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        )}
      </div>

      <form onSubmit={runSearch} className="border-t p-3 shrink-0 space-y-2" style={{ borderColor: C.line }}>
        <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.mute }}>Search players</div>
        <div className="flex gap-1">
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="e.g. Yamal, Martinez"
            className="flex-1 rounded-lg px-2 py-1.5 text-xs outline-none"
            style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }} />
          <button type="submit" className="rounded-lg px-2.5 py-1.5 text-xs font-semibold"
            style={{ background: C.line, color: C.chalk }}>Go</button>
        </div>
        {searchHits && (
          searchHits.length === 0
            ? <div className="text-[10px]" style={{ color: C.mute }}>No matches.</div>
            : <div className="grid grid-cols-1 gap-1 max-h-32 overflow-y-auto">
                {searchHits.map((p, i) => (
                  <PlayerCard key={i} p={p} onSelect={askPlayer} compact />
                ))}
              </div>
        )}
      </form>
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
        <>
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
            {groups[open].map((r, i) => {
              const rank = i + 1;
              const zone = zoneForRank("WC", rank, groups[open].length)
                ?? (rank <= 2 ? WC_GROUP_ZONES[0] : null);
              return (
              <tr key={i} className="border-t" style={{
                borderColor: C.line,
                background: zone ? `${zone.color}12` : undefined,
                boxShadow: zone ? `inset 3px 0 0 ${zone.color}` : undefined,
              }}>
                <td className="px-3 py-1.5 text-xs" style={{ color: C.chalk }}>
                  <span className="mr-1.5 tabular-nums" style={{ color: zone?.color ?? C.mute }}>{rank}</span>
                  {flag(r.team)}{r.team}
                  {zone && (
                    <span className="ml-1 text-[10px] font-medium" style={{ color: zone.color }}>{zone.short}</span>
                  )}
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
              );
            })}
          </tbody>
        </table>
        <div className="flex flex-wrap gap-x-3 gap-y-1 border-t px-3 py-2" style={{ borderColor: C.line }}>
          {WC_GROUP_ZONES.map((z) => (
            <span key={z.id} className="inline-flex items-center gap-1 text-[10px]" style={{ color: C.mute }}>
              <span className="inline-block h-2 w-2 rounded-sm shrink-0" style={{ background: z.color }} />
              Top 2 — {z.label}
            </span>
          ))}
        </div>
        </>
      )}
    </div>
  );
}

function StandingsLegend({ compCode }) {
  const items = standingLegend(compCode);
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 border-t px-3 py-2" style={{ borderColor: C.line }}>
      {items.map((z) => (
        <span key={z.id} className="inline-flex items-center gap-1 text-[10px]" style={{ color: C.mute }}>
          <span className="inline-block h-2 w-2 rounded-sm shrink-0" style={{ background: z.color }} />
          {z.label}
        </span>
      ))}
    </div>
  );
}

function StandingsPanel({ apiBase, offline, onCompChange }) {
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
            <button key={l.code} onClick={() => { setActiveComp(l.code); onCompChange?.(l.code); }}
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
        <>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] uppercase" style={{ color: C.mute }}>
              <th className="px-3 py-1.5 text-left font-medium w-8">#</th>
              <th className="px-2 py-1.5 text-left font-medium">Club</th>
              <th className="px-2 py-1.5 text-right font-medium">GD</th>
              <th className="px-3 py-1.5 text-right font-medium">Pts</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const zone = rowZone(activeComp, r, rows.length);
              return (
              <tr key={r.rank} className="border-t" style={{
                borderColor: C.line,
                background: zone ? `${zone.color}12` : undefined,
                boxShadow: zone ? `inset 3px 0 0 ${zone.color}` : undefined,
              }}>
                <td className="px-3 py-2 tabular-nums" style={{ color: zone?.color ?? C.mute }}>
                  {r.rank}
                </td>
                <td className="px-2 py-2 max-w-[140px] truncate" style={{ color: C.chalk }}>
                  {r.team}
                  {zone && (
                    <span className="ml-1.5 text-[10px] font-medium" style={{ color: zone.color }}>
                      {zone.short}
                    </span>
                  )}
                </td>
                <td className="px-2 py-2 text-right tabular-nums" style={{ color: C.mute }}>
                  {r.GD > 0 ? `+${r.GD}` : r.GD}
                </td>
                <td className="px-3 py-2 text-right font-semibold tabular-nums" style={{ color: C.chalk }}>{r.Pts}</td>
              </tr>
              );
            })}
          </tbody>
        </table>
        <StandingsLegend compCode={activeComp} />
        </>
      )}
    </div>
  );
}

function CalibrationPanel({ summary, apiBase, offline }) {
  const [cal, setCal] = useState(null);

  useEffect(() => {
    if (!apiBase || offline) { setCal(null); return; }
    fetch(`${apiBase}/api/predictions/calibration`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setCal(d))
      .catch(() => setCal(null));
  }, [apiBase, offline, summary?.graded]);

  const rate = summary?.hit_rate ?? cal?.hit_rate;
  const bins = (cal?.bins ?? []).filter((b) => b.count > 0);

  return (
    <div className="rounded-xl border p-4" style={{ borderColor: C.line, background: C.panel }}>
      <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
        Prediction accuracy & calibration
      </div>
      <div className="mt-3 flex items-end gap-2">
        <span className="text-4xl font-bold tabular-nums" style={{ color: rate == null ? C.mute : C.home }}>
          {rate == null ? "—" : pct(rate)}
        </span>
        <span className="mb-1 text-xs" style={{ color: C.mute }}>hit rate</span>
      </div>
      <div className="mt-1 text-xs" style={{ color: C.mute }}>
        {summary?.graded
          ? `${summary.correct}/${summary.graded} ${summary.graded === 1 ? "match" : "matches"}`
          : "No graded predictions yet"}
        {cal?.mean_abs_calibration_error != null && summary?.graded >= 3 && (
          <span> · calibration error {pct(cal.mean_abs_calibration_error)}</span>
        )}
      </div>

      {bins.length > 0 ? (
        <div className="mt-4 space-y-3 border-t pt-3" style={{ borderColor: C.line }}>
          <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
            By confidence band
          </div>
          <p className="text-[10px] leading-snug" style={{ color: C.mute }}>
            When we predict at ~70%, those picks should win ~70% of the time. Bars compare predicted vs actual.
          </p>
          {bins.map((b) => (
            <div key={b.label}>
              <div className="flex items-center justify-between text-[10px] mb-1">
                <span style={{ color: C.chalk }}>{b.label}</span>
                <span style={{ color: C.mute }}>{b.correct}/{b.count} correct</span>
              </div>
              <div className="flex items-center gap-2 text-[9px] mb-0.5">
                <span className="w-10 shrink-0" style={{ color: C.mute }}>Pred</span>
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: C.line }}>
                  <div className="h-full rounded-full" style={{ width: `${(b.expected_rate || 0) * 100}%`, background: C.mute }} />
                </div>
                <span className="w-8 text-right tabular-nums" style={{ color: C.mute }}>{pct(b.expected_rate)}</span>
              </div>
              <div className="flex items-center gap-2 text-[9px]">
                <span className="w-10 shrink-0" style={{ color: C.mute }}>Actual</span>
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: C.line }}>
                  <div className="h-full rounded-full" style={{
                    width: `${(b.actual_rate || 0) * 100}%`,
                    background: Math.abs(b.gap || 0) > 0.15 ? C.away : C.home,
                  }} />
                </div>
                <span className="w-8 text-right tabular-nums" style={{ color: C.chalk }}>{pct(b.actual_rate)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : cal && cal.graded > 0 ? (
        <div className="mt-3 text-[10px]" style={{ color: C.mute }}>
          Not enough spread across confidence bands yet — keep predicting!
        </div>
      ) : null}
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

      <div className="flex flex-1 flex-col gap-4 p-4 md:flex-row">
        {/* ── Chat panel ── */}
        <section className="flex min-h-[60vh] flex-1 flex-col rounded-xl border md:basis-[60%]"
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
        <aside className="flex flex-col gap-4 md:basis-[40%]">
          <SidebarModeToggle mode={sidebarMode} setMode={setSidebarMode} />
          {sidebarMode === "matches" ? (
            <>
              <CalibrationPanel summary={summary} apiBase={API_BASE} offline={offline} />
              <FixturesPanel initialWc={wcFixtures} initialPl={plFixtures} sidebarLoaded={sidebarLoaded} onClickFixture={handleFixtureClick} apiBase={API_BASE} onSummary={setSummary} onCompChange={handleCompChange} />
              {Object.keys(groups).length > 0 && <GroupsPanel groups={groups} />}
              <BracketPanel apiBase={API_BASE} offline={offline} />
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
