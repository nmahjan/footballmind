import { useState, useEffect, useRef, useCallback } from "react";
import { pct } from "../fm/format.js";
import { demoPredict, COMP_LABELS } from "../fm/demo.js";
import { pingBackend, readApiError } from "../fm/api.js";
import {
  getAdminKey, saveAdminKeyFromUrl, getOrCreateSessionId, createNewSessionId,
} from "../fm/session.js";
import {
  parseVs, DEEPLINK_STORAGE_KEY, PREDICTION_CACHE_KEY,
  deepLinkSignature, clearDeepLinkParams, markDeepLinkHandled, deepLinkAlreadyHandled,
  savePredictionCache, loadPredictionCache, syncPredictUrl, parseDeepLinkSearch,
} from "../fm/deeplink.js";
import { guessLoadPhase } from "../components/TypingIndicator.jsx";

export function useFootballMindChat(apiBase) {
  const [sessionId, setSessionId] = useState(getOrCreateSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [venueMode, setVenueMode] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadPhase, setLoadPhase] = useState(null);
  const [chatComp, setChatComp] = useState("WC");
  const [backendStatus, setBackendStatus] = useState(apiBase ? "connecting" : "demo");
  const [offline, setOffline] = useState(!apiBase);
  const sendRef = useRef(null);
  const deepLinkHandled = useRef(false);
  const shareLinkAtLoad = useRef(parseDeepLinkSearch());
  const historyBlockedRef = useRef(Boolean(shareLinkAtLoad.current));

  const handleCompChange = useCallback((code) => {
    if (code && COMP_LABELS[code]) setChatComp(code);
  }, []);

  const ensureBackendAwake = useCallback(async () => {
    if (!apiBase || backendStatus === "live") return true;
    setLoadPhase("waking");
    const ok = await pingBackend(apiBase);
    if (ok) {
      setBackendStatus("live");
      setOffline(false);
      return true;
    }
    setBackendStatus("unreachable");
    setLoadPhase("waking_slow");
    return false;
  }, [apiBase, backendStatus]);

  const startNewChat = useCallback(() => {
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
  }, [busy]);

  const send = useCallback(async (text, options = {}) => {
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
      if (!apiBase) throw new Error("offline");
      let isLive = backendStatus === "live";
      if (!isLive) {
        isLive = await ensureBackendAwake();
        setLoadPhase(guessLoadPhase(text, isLive ? "live" : "unreachable"));
      }
      const body = { message: text, session_id: sessionId, history, comp: effectiveComp };
      if (effectiveNeutral !== null) body.neutral = effectiveNeutral;
      const res = await fetch(`${apiBase}/api/chat`, {
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
      if (!apiBase) {
        if (teams) {
          const p = demoPredict(teams.home, teams.away);
          setMessages((m) => [...m, { role: "bot", text: `${p.prediction} (${pct(p.confidence)} confidence). ${p.reasoning}`, prediction: p, teams, demo: true }]);
        } else {
          setMessages((m) => [...m, { role: "bot", text: 'Try a matchup like "Predict Mexico vs USA", or "show the table".', demo: true }]);
        }
      } else {
        setBackendStatus("unreachable");
        setMessages((m) => [...m, { role: "bot", text: "Backend unavailable — Render may still be waking up. Wait ~30s and try again." }]);
      }
    } finally {
      clearTimeout(slowTimer);
      setBusy(false);
      setLoadPhase(null);
    }
  }, [apiBase, input, busy, chatComp, venueMode, messages, sessionId, backendStatus, ensureBackendAwake]);

  sendRef.current = send;

  const handleFixtureClick = useCallback((f) => {
    if (busy) return;
    const comp = f.comp && COMP_LABELS[f.comp] ? f.comp : chatComp;
    if (comp !== chatComp) setChatComp(comp);
    send(`Predict ${f.home} vs ${f.away}`, { comp });
  }, [busy, chatComp, send]);

  const handlePlayerAsk = useCallback((text) => {
    send(text);
  }, [send]);

  function restoreSharePredictionMessages(link) {
    const cached = loadPredictionCache(link?.query);
    if (!cached?.prediction) return null;
    const p = cached.prediction;
    const text = `${p.prediction} (${pct(p.confidence)} confidence). ${p.reasoning || ""}`.trim();
    return [
      { role: "user", text: link.query },
      {
        role: "bot",
        text,
        prediction: cached.prediction,
        teams: cached.teams,
        comp: cached.comp,
        neutral: cached.neutral,
      },
    ];
  }

  useEffect(() => {
    saveAdminKeyFromUrl();
  }, []);

  useEffect(() => {
    if (!apiBase || historyBlockedRef.current) return;
    const ctrl = new AbortController();
    fetch(`${apiBase}/api/history?session_id=${encodeURIComponent(sessionId)}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (historyBlockedRef.current || shareLinkAtLoad.current) return;
        if (!data?.history?.length) return;
        const restored = [];
        for (const row of [...data.history].reverse()) {
          if (row.query) restored.push({ role: "user", text: row.query });
          if (row.response) {
            const cached = loadPredictionCache(row.query);
            restored.push({ role: "bot", text: row.response, ...(cached || {}) });
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
  }, [apiBase, sessionId]);

  useEffect(() => {
    if (deepLinkHandled.current) return;
    const link = parseDeepLinkSearch();
    if (!link) return;
    deepLinkHandled.current = true;
    historyBlockedRef.current = true;
    const sig = deepLinkSignature();
    if (deepLinkAlreadyHandled(sig)) {
      const restored = restoreSharePredictionMessages(link);
      if (restored) setMessages(restored);
      clearDeepLinkParams();
      historyBlockedRef.current = false;
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

  // Keep Render warm when tab is open (free tier cold start)
  useEffect(() => {
    if (!apiBase) return;
    const ping = () => {
      if (document.visibilityState !== "visible") return;
      fetch(`${apiBase}/api/health`).then((r) => {
        if (r.ok) {
          setBackendStatus("live");
          setOffline(false);
        }
      }).catch(() => {});
    };
    ping();
    const id = setInterval(ping, 12 * 60 * 1000);
    return () => clearInterval(id);
  }, [apiBase]);

  return {
    sessionId,
    messages,
    input,
    setInput,
    venueMode,
    setVenueMode,
    busy,
    loadPhase,
    chatComp,
    setChatComp,
    backendStatus,
    setBackendStatus,
    offline,
    setOffline,
    send,
    startNewChat,
    handleCompChange,
    handleFixtureClick,
    handlePlayerAsk,
  };
}
