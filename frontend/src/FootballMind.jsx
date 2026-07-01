import { useState, useEffect, useRef } from "react";
import BracketPanel, { BracketTree, normaliseBracket } from "./components/BracketPanel.jsx";
import SyncHealthPanel from "./components/SyncHealthPanel.jsx";
import PlayersSidebar, { SidebarModeToggle } from "./components/PlayersSidebar.jsx";
import FixturesPanel from "./components/FixturesPanel.jsx";
import GroupsPanel from "./components/GroupsPanel.jsx";
import StandingsPanel from "./components/StandingsPanel.jsx";
import CalibrationPanel from "./components/CalibrationPanel.jsx";
import RankingsPanel from "./components/RankingsPanel.jsx";
import PredictionCard from "./components/PredictionCard.jsx";
import MarkdownBody from "./components/MarkdownBody.jsx";
import TypingIndicator, { guessLoadPhase } from "./components/TypingIndicator.jsx";
import { C } from "./fm/theme.js";
import { pct } from "./fm/format.js";
import { DEMO_FIXTURES, demoPredict, COMP_LABELS } from "./fm/demo.js";
import { getApiBase, pingBackend, readApiError } from "./fm/api.js";
import {
  getAdminKey, saveAdminKeyFromUrl, getOrCreateSessionId, createNewSessionId,
} from "./fm/session.js";
import {
  parseVs, DEEPLINK_STORAGE_KEY, PREDICTION_CACHE_KEY,
  deepLinkSignature, clearDeepLinkParams, markDeepLinkHandled, deepLinkAlreadyHandled,
  savePredictionCache, loadPredictionCache, syncPredictUrl, parseDeepLinkSearch,
} from "./fm/deeplink.js";

const API_BASE = getApiBase();

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

export default function FootballMind() {
  const [sessionId, setSessionId] = useState(getOrCreateSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [venueMode, setVenueMode] = useState(null);
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
                      apiBase={API_BASE}
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
