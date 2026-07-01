import { useState, useEffect, useRef } from "react";
import AppHeader from "./components/AppHeader.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import MatchesSidebar from "./components/MatchesSidebar.jsx";
import PlayersSidebar, { SidebarModeToggle } from "./components/PlayersSidebar.jsx";
import GroupsPanel from "./components/GroupsPanel.jsx";
import StandingsPanel from "./components/StandingsPanel.jsx";
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
import { guessLoadPhase } from "./components/TypingIndicator.jsx";

const API_BASE = getApiBase();

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
  }

  function handlePlayerAsk(text) {
    send(text);
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

  const showTablesBelowChat = sidebarMode === "matches";

  return (
    <div className="flex min-h-screen w-full flex-col font-sans" style={{ background: C.bg, color: C.chalk }}>
      <AppHeader offline={offline} backendStatus={backendStatus} />

      <div className="flex min-w-0 flex-1 flex-col gap-4 p-4 md:flex-row md:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-4 md:basis-[60%]">
          <ChatPanel
            messages={messages}
            busy={busy}
            loadPhase={loadPhase}
            input={input}
            setInput={setInput}
            send={send}
            startNewChat={startNewChat}
            sidebarMode={sidebarMode}
            venueMode={venueMode}
            setVenueMode={setVenueMode}
            chatComp={chatComp}
            apiBase={API_BASE}
          />

          {showTablesBelowChat && (
            <div className={`grid min-w-0 gap-4 ${Object.keys(groups).length > 0 ? "lg:grid-cols-2" : "grid-cols-1"}`}>
              {Object.keys(groups).length > 0 && <GroupsPanel groups={groups} />}
              <StandingsPanel apiBase={API_BASE} offline={offline} onCompChange={handleCompChange} />
            </div>
          )}
        </div>

        <aside className="flex min-w-0 flex-col gap-4 md:max-w-[40%] md:basis-[40%] md:shrink-0">
          <SidebarModeToggle mode={sidebarMode} setMode={setSidebarMode} />
          {sidebarMode === "matches" ? (
            <MatchesSidebar
              summary={summary}
              apiBase={API_BASE}
              offline={offline}
              wcFixtures={wcFixtures}
              plFixtures={plFixtures}
              sidebarLoaded={sidebarLoaded}
              onClickFixture={handleFixtureClick}
              onSummary={setSummary}
              onCompChange={handleCompChange}
              chatComp={chatComp}
            />
          ) : (
            <PlayersSidebar apiBase={API_BASE} offline={offline} onAsk={handlePlayerAsk} onCompChange={handleCompChange} adminKey={adminKey} />
          )}
        </aside>
      </div>
    </div>
  );
}
