import { useState, useEffect } from "react";
import { C } from "../fm/theme.js";
import { cachedJson } from "../fm/cache.js";

const JOB_LABELS = {
  matchday: "Matchday sync",
  wikipedia: "Wikipedia squads",
  sync: "Full sync",
};

function fmtWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  if (diff < 3600000) return `${Math.max(1, Math.round(diff / 60000))}m ago`;
  if (diff < 86400000) return `${Math.round(diff / 3600000)}h ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function statusColor(status) {
  if (status === "ok") return C.home;
  if (status === "partial") return C.warning;
  if (status === "failed") return "#f87171";
  return C.mute;
}

export default function SyncHealthPanel({ apiBase, offline }) {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    if (!apiBase || offline) {
      setHealth(null);
      return;
    }
    cachedJson(`${apiBase}/api/sync-health`, { ttlMs: 30_000 })
      .then((d) => setHealth(d))
      .catch(() => setHealth(null));
  }, [apiBase, offline]);

  if (!apiBase || offline) return null;

  const jobs = health?.jobs ?? [];

  return (
    <div className="rounded-lg border p-4" style={{ borderColor: C.line, background: C.panel }}>
      <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
        Sync health
      </div>
      {!health ? (
        <div className="mt-2 text-xs" style={{ color: C.mute }}>Loading…</div>
      ) : jobs.length === 0 ? (
        <div className="mt-2 text-xs" style={{ color: C.mute }}>
          No job runs recorded yet — runs appear after the next scheduled sync.
        </div>
      ) : (
        <ul className="mt-3 space-y-2">
          {jobs.map((j) => (
            <li key={j.job} className="flex items-start justify-between gap-2 text-xs">
              <span style={{ color: C.chalk }}>{JOB_LABELS[j.job] ?? j.job}</span>
              <span className="shrink-0 text-right">
                <span style={{ color: statusColor(j.status) }}>{j.status}</span>
                <span className="block text-[10px]" style={{ color: C.mute }}>{fmtWhen(j.finished_at)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {health?.jobs?.some((j) => j.summary?.alert) && (
        <div className="mt-3 rounded-md border px-2.5 py-2 text-[11px]"
          style={{ borderColor: C.warning, color: C.warning, background: "rgba(248,151,29,0.10)" }}>
          {health.jobs.filter((j) => j.summary?.alert).map((j) => (
            <div key={j.job}>{j.summary.alert}</div>
          ))}
        </div>
      )}
      {health?.last_result_at && (
        <div className="mt-3 border-t pt-2 text-[10px]" style={{ borderColor: C.line, color: C.mute }}>
          Latest result: {fmtWhen(health.last_result_at)}
          {health.players_with_roles != null && (
            <span> · {health.players_with_roles} players with roles</span>
          )}
        </div>
      )}
    </div>
  );
}
