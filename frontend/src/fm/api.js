export function getApiBase() {
  try {
    if (import.meta?.env?.VITE_API_BASE) return import.meta.env.VITE_API_BASE;
  } catch { /* ignore */ }
  return "";
}

export async function pingBackend(apiBase, timeoutMs = 28000) {
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

export async function readApiError(res) {
  try {
    const data = await res.json();
    return data.message || data.detail || data.error || `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}
