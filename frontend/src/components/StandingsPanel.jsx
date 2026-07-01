import { useState, useEffect } from "react";
import { C } from "../fm/theme.js";
import { LEAGUES, DEMO_STANDINGS, standingLegend, rowZone, standingsSections } from "../fm/standings.js";

function StandingsTableBody({ compCode, rows, teamCount }) {
  return rows.map((r) => {
    const zone = rowZone(compCode, r, teamCount);
    return (
      <tr key={`${r.conference ?? "x"}-${r.rank}-${r.team}`} className="border-t" style={{
        borderColor: C.line,
        background: zone ? `${zone.color}12` : undefined,
        boxShadow: zone ? `inset 3px 0 0 ${zone.color}` : undefined,
      }}>
        <td className="px-3 py-2 tabular-nums" style={{ color: zone?.color ?? C.mute }}>
          {r.rank}
        </td>
        <td className="px-2 py-2 max-w-[120px] truncate text-xs" style={{ color: C.chalk }}>
          {r.team}
          {zone && (
            <span className="ml-1.5 text-[10px] font-medium" style={{ color: zone.color }}>
              {zone.short}
            </span>
          )}
        </td>
        <td className="px-1.5 py-2 text-center tabular-nums text-xs" style={{ color: C.mute }}>{r.P ?? "—"}</td>
        <td className="px-1.5 py-2 text-center tabular-nums text-xs" style={{ color: C.chalk }}>{r.W ?? "—"}</td>
        <td className="px-1.5 py-2 text-center tabular-nums text-xs" style={{ color: C.mute }}>{r.D ?? "—"}</td>
        <td className="px-1.5 py-2 text-center tabular-nums text-xs" style={{ color: C.mute }}>{r.L ?? "—"}</td>
        <td className="px-2 py-2 text-right tabular-nums text-xs" style={{ color: C.mute }}>
          {r.GD > 0 ? `+${r.GD}` : r.GD ?? "—"}
        </td>
        <td className="px-3 py-2 text-right font-semibold tabular-nums text-xs" style={{ color: C.chalk }}>{r.Pts}</td>
      </tr>
    );
  });
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

export default function StandingsPanel({ apiBase, offline, onCompChange }) {
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
        <div className="max-h-[280px] overflow-y-auto" style={{ scrollbarWidth: "thin" }}>
        {standingsSections(activeComp, rows).map((section) => (
          <div key={section.key}>
            {section.label && (
              <div className="border-t px-4 py-2 text-[11px] font-semibold uppercase tracking-wide"
                style={{ borderColor: C.line, color: C.mute }}>
                {section.label}
              </div>
            )}
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-[1]" style={{ background: C.panel }}>
                <tr className="text-[10px] uppercase" style={{ color: C.mute }}>
                  <th className="px-3 py-1.5 text-left font-medium w-8">#</th>
                  <th className="px-2 py-1.5 text-left font-medium">Club</th>
                  <th className="px-1.5 py-1.5 text-center font-medium">P</th>
                  <th className="px-1.5 py-1.5 text-center font-medium">W</th>
                  <th className="px-1.5 py-1.5 text-center font-medium">D</th>
                  <th className="px-1.5 py-1.5 text-center font-medium">L</th>
                  <th className="px-1.5 py-1.5 text-right font-medium">GD</th>
                  <th className="px-3 py-1.5 text-right font-medium">Pts</th>
                </tr>
              </thead>
              <tbody>
                <StandingsTableBody compCode={activeComp} rows={section.rows} teamCount={rows.length} />
              </tbody>
            </table>
          </div>
        ))}
        </div>
        {activeComp === "MLS" && (
          <div className="border-t px-3 py-2 text-[10px]" style={{ borderColor: C.line, color: C.mute }}>
            MLS has no relegation. Top 9 per conference reach the Audi MLS Cup Playoffs (seeds 1–7 Round One, 8–9 Wild Card).
          </div>
        )}
        <StandingsLegend compCode={activeComp} />
        </>
      )}
    </div>
  );
}
