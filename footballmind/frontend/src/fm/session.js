export const SESSION_KEY = "footballmind_session_id";
export const ADMIN_KEY_STORAGE = "footballmind_admin_key";

export function getAdminKey() {
  try { return localStorage.getItem(ADMIN_KEY_STORAGE) || ""; } catch { return ""; }
}

export function saveAdminKeyFromUrl() {
  try {
    const k = new URLSearchParams(window.location.search).get("admin_key");
    if (k) localStorage.setItem(ADMIN_KEY_STORAGE, k);
  } catch { /* ignore */ }
}

export function getOrCreateSessionId() {
  try {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) id = createNewSessionId();
    return id;
  } catch {
    return crypto?.randomUUID?.() || String(Math.random());
  }
}

export function createNewSessionId() {
  const id = crypto?.randomUUID?.() || String(Math.random());
  try { localStorage.setItem(SESSION_KEY, id); } catch { /* ignore */ }
  return id;
}
