import { useState } from "react";
import { C, TeamLabel } from "../fm/theme.js";
import { zoneForRank, WC_GROUP_ZONES } from "../fm/standings.js";

export default function GroupsPanel({ groups }) {
  const letters = Object.keys(groups).sort();
  const [open, setOpen] = useState(letters[0] ?? null);

  if (letters.length === 0) return null;

  return (
    <div className="rounded-xl border" style={{ borderColor: C.line, background: C.panel }}>
      <div className="border-b px-4 py-2.5 text-xs font-semibold uppercase tracking-wider"
        style={{ borderColor: C.line, color: C.mute }}>
        WC Group Standings
      </div>
      {/* Group tabs */}
      <div className="flex flex-wrap gap-1 px-3 pt-2 pb-1">
        {letters.map((g) => (
          <button key={g} onClick={() => setOpen(g)}
            className="rounded px-2 py-0.5 text-[11px] font-semibold transition-colors"
            style={{ background: g === open ? C.home : C.line, color: g === open ? "#08120F" : C.mute }}>
            {g}
          </button>
        ))}
      </div>
      {open && groups[open] && (
        <>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase" style={{ color: C.mute }}>
              <th className="px-3 py-1 text-left font-medium">Team</th>
              <th className="px-2 py-1 text-center font-medium">P</th>
              <th className="px-2 py-1 text-center font-medium">W</th>
              <th className="px-2 py-1 text-center font-medium">D</th>
              <th className="px-2 py-1 text-center font-medium">L</th>
              <th className="px-2 py-1 text-right font-medium">GD</th>
              <th className="px-3 py-1 text-right font-medium">Pts</th>
            </tr>
          </thead>
          <tbody>
            {groups[open].map((r, i) => {
              const rank = i + 1;
              const zone = zoneForRank("WC", rank, groups[open].length)
                ?? (rank <= 2 ? WC_GROUP_ZONES[0] : null);
              return (
              <tr key={i} className="border-t" style={{
                borderColor: C.line,
                background: zone ? `${zone.color}12` : undefined,
                boxShadow: zone ? `inset 3px 0 0 ${zone.color}` : undefined,
              }}>
                <td className="px-3 py-1.5 text-xs" style={{ color: C.chalk }}>
                  <span className="mr-1.5 tabular-nums" style={{ color: zone?.color ?? C.mute }}>{rank}</span>
                  <TeamLabel name={r.team} />
                  {zone && (
                    <span className="ml-1 text-[10px] font-medium" style={{ color: zone.color }}>{zone.short}</span>
                  )}
                </td>
                <td className="px-2 py-1.5 text-center text-xs tabular-nums" style={{ color: C.mute }}>{r.P ?? "—"}</td>
                <td className="px-2 py-1.5 text-center text-xs tabular-nums" style={{ color: C.chalk }}>{r.W}</td>
                <td className="px-2 py-1.5 text-center text-xs tabular-nums" style={{ color: C.mute }}>{r.D}</td>
                <td className="px-2 py-1.5 text-center text-xs tabular-nums" style={{ color: C.mute }}>{r.L}</td>
                <td className="px-2 py-1.5 text-right text-xs tabular-nums" style={{ color: C.mute }}>
                  {r.GD > 0 ? `+${r.GD}` : r.GD}
                </td>
                <td className="px-3 py-1.5 text-right text-xs font-bold tabular-nums" style={{ color: r.Pts > 0 ? C.home : C.chalk }}>
                  {r.Pts}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
        <div className="flex flex-wrap gap-x-3 gap-y-1 border-t px-3 py-2" style={{ borderColor: C.line }}>
          {WC_GROUP_ZONES.map((z) => (
            <span key={z.id} className="inline-flex items-center gap-1 text-[10px]" style={{ color: C.mute }}>
              <span className="inline-block h-2 w-2 rounded-sm shrink-0" style={{ background: z.color }} />
              Top 2 — {z.label}
            </span>
          ))}
        </div>
        </>
      )}
    </div>
  );
}
