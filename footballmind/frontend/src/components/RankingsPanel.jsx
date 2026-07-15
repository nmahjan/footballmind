import { useState, useEffect } from "react";
import { C, TeamLabel } from "../fm/theme.js";

export default function RankingsPanel({ apiBase, offline, defaultOpen = false }) {
  const [rows, setRows] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(defaultOpen);

  function load() {
    if (loaded || offline || !apiBase) return;
    fetch(`${apiBase}/api/rankings?comp=WC&limit=48`)
      .then((r) => r.json())
      .then((d) => { setRows(d.rankings ?? []); setLoaded(true); })
      .catch(() => setLoaded(true));
  }

  useEffect(() => {
    if (defaultOpen) load();
  }, [defaultOpen, apiBase, offline]);

  if (!open) {
    return (
      <button onClick={() => { setOpen(true); load(); }}
        className="flex w-full items-center justify-between rounded-lg border px-4 py-3 text-left transition-opacity hover:opacity-70"
        style={{ borderColor: C.line, background: C.panel }}>
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          🏆 WC Power Rankings
        </span>
        <span className="text-xs" style={{ color: C.mute }}>show ▾</span>
      </button>
    );
  }

  return (
    <div className="rounded-lg border" style={{ borderColor: C.line, background: C.panel }}>
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
        <div>
          {rows.map((r) => (
            <div key={r.rank} className="flex items-center gap-3 px-4 py-1.5"
              style={{ borderTop: r.rank > 1 ? `1px solid ${C.line}` : "none" }}>
              <span className="w-5 shrink-0 text-[11px] tabular-nums text-right" style={{ color: C.mute }}>{r.rank}</span>
              <span className="flex-1 text-xs" style={{ color: C.chalk }}><TeamLabel name={r.team} /></span>
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
