export const VALID_COMPS = new Set(["WC", "PL", "PD", "BL1", "SA", "FL1", "CL", "DED", "MLS"]);
export const DEEPLINK_STORAGE_KEY = "fm_deeplink_search";
export const PREDICTION_CACHE_KEY = "fm_prediction_cache";

export function parseVs(msg) {
  const m = msg.match(/^\s*(?:predict|forecast)?\s*(.+?)\s+(?:vs\.?|versus|v|against)\s+(.+?)\s*[?.!]*$/i);
  if (!m) return null;
  const clean = (s) => s
    .replace(/^(who\s+will\s+win\s+|who\s+wins\s+|will\s+|can\s+|the\s+|a\s+)/i, "")
    .replace(/\s+(match|game|fixture|this weekend|today|tomorrow|on \w+)\b.*$/i, "")
    .trim();
  return { home: clean(m[1]), away: clean(m[2]) };
}

function deepLinkParamsHasPredict(params) {
  return Boolean(
    params.get("predict")?.trim() ||
    (params.get("home")?.trim() && params.get("away")?.trim())
  );
}

export function getDeepLinkParams() {
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

export function deepLinkSignature() {
  const params = getDeepLinkParams();
  return deepLinkParamsHasPredict(params) ? params.toString() : "";
}

export function buildPredictUrl(home, away, { comp, neutral } = {}) {
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

export function clearDeepLinkParams() {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  for (const key of ["predict", "home", "away", "comp", "neutral"]) {
    url.searchParams.delete(key);
  }
  url.hash = "";
  const qs = url.searchParams.toString();
  window.history.replaceState(null, "", url.pathname + (qs ? `?${qs}` : ""));
}

export function markDeepLinkHandled(sig = deepLinkSignature()) {
  try { sessionStorage.setItem(DEEPLINK_STORAGE_KEY, sig || ""); } catch { /* ignore */ }
}

export function deepLinkAlreadyHandled(sig = deepLinkSignature()) {
  try { return sessionStorage.getItem(DEEPLINK_STORAGE_KEY) === (sig || ""); } catch { return false; }
}

export function savePredictionCache(query, entry) {
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

export function loadPredictionCache(query) {
  try {
    const cache = JSON.parse(sessionStorage.getItem(PREDICTION_CACHE_KEY) || "{}");
    return cache[(query || "").trim().toLowerCase()] || null;
  } catch { return null; }
}

export function syncPredictUrl(home, away, comp, neutral) {
  if (!home || !away || typeof window === "undefined") return;
  const next = buildPredictUrl(home, away, { comp, neutral });
  if (window.location.href !== next) {
    window.history.replaceState(null, "", next);
  }
  markDeepLinkHandled(deepLinkSignature());
}

export function parseDeepLinkSearch() {
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

export function hasDeepLinkPredict() {
  return deepLinkParamsHasPredict(getDeepLinkParams());
}
