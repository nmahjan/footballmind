const memoryCache = new Map();
const inflight = new Map();

const DEFAULT_TTL_MS = 90_000;
const STORAGE_PREFIX = "fm:http:";

function cacheKey(url) {
  return `${STORAGE_PREFIX}${url}`;
}

function nowMs() {
  return Date.now();
}

function readStored(url) {
  try {
    const raw = sessionStorage.getItem(cacheKey(url));
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeStored(url, entry) {
  try {
    sessionStorage.setItem(cacheKey(url), JSON.stringify(entry));
  } catch {
    // Storage can be unavailable or full. The memory cache still helps.
  }
}

function fresh(entry, ttlMs) {
  return entry && nowMs() - entry.savedAt < ttlMs;
}

export function clearCachedJson(url) {
  memoryCache.delete(url);
  try {
    sessionStorage.removeItem(cacheKey(url));
  } catch {
    // ignore
  }
}

export async function cachedJson(url, { ttlMs = DEFAULT_TTL_MS, force = false, signal } = {}) {
  if (!force) {
    const mem = memoryCache.get(url);
    if (fresh(mem, ttlMs)) return mem.data;

    const stored = readStored(url);
    if (fresh(stored, ttlMs)) {
      memoryCache.set(url, stored);
      return stored.data;
    }

    if (inflight.has(url)) return inflight.get(url);
  }

  const request = fetch(url, { signal })
    .then(async (res) => {
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      const entry = { savedAt: nowMs(), data };
      memoryCache.set(url, entry);
      writeStored(url, entry);
      return data;
    })
    .finally(() => inflight.delete(url));

  inflight.set(url, request);
  return request;
}
