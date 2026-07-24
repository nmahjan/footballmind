import { useState, useEffect } from "react";
import { C } from "../fm/theme.js";
import { cachedJson } from "../fm/cache.js";
import { pct } from "../fm/format.js";

export default function CalibrationPanel({ summary, apiBase, offline }) {
  const [cal, setCal] = useState(null);

  useEffect(() => {
    if (!apiBase || offline) { setCal(null); return; }
    cachedJson(`${apiBase}/api/predictions/calibration`, { ttlMs: 60_000 })
      .then((d) => setCal(d))
      .catch(() => setCal(null));
  }, [apiBase, offline, summary?.graded]);

  const rate = summary?.hit_rate ?? cal?.hit_rate;
  const bins = (cal?.bins ?? []).filter((b) => b.count > 0);

  return (
    <div className="rounded-lg border p-4" style={{ borderColor: C.line, background: C.panel }}>
      <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
        Prediction accuracy & calibration
      </div>
      <div className="mt-3 flex items-end gap-2">
        <span className="text-4xl font-bold tabular-nums" style={{ color: rate == null ? C.mute : C.home }}>
          {rate == null ? "—" : pct(rate)}
        </span>
        <span className="mb-1 text-xs" style={{ color: C.mute }}>hit rate</span>
      </div>
      <div className="mt-1 text-xs" style={{ color: C.mute }}>
        {summary?.graded
          ? `${summary.correct}/${summary.graded} ${summary.graded === 1 ? "match" : "matches"}`
          : "No graded predictions yet"}
        {cal?.mean_abs_calibration_error != null && summary?.graded >= 3 && (
          <span> · calibration error {pct(cal.mean_abs_calibration_error)}</span>
        )}
      </div>

      {bins.length > 0 ? (
        <div className="mt-4 space-y-3 border-t pt-3" style={{ borderColor: C.line }}>
          <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
            By confidence band
          </div>
          <p className="text-[10px] leading-snug" style={{ color: C.mute }}>
            When we predict at ~70%, those picks should win ~70% of the time. Bars compare predicted vs actual.
          </p>
          {bins.map((b) => (
            <div key={b.label}>
              <div className="flex items-center justify-between text-[10px] mb-1">
                <span style={{ color: C.chalk }}>{b.label}</span>
                <span style={{ color: C.mute }}>{b.correct}/{b.count} correct</span>
              </div>
              <div className="flex items-center gap-2 text-[9px] mb-0.5">
                <span className="w-10 shrink-0" style={{ color: C.mute }}>Pred</span>
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: C.line }}>
                  <div className="h-full rounded-full" style={{ width: `${(b.expected_rate || 0) * 100}%`, background: C.mute }} />
                </div>
                <span className="w-8 text-right tabular-nums" style={{ color: C.mute }}>{pct(b.expected_rate)}</span>
              </div>
              <div className="flex items-center gap-2 text-[9px]">
                <span className="w-10 shrink-0" style={{ color: C.mute }}>Actual</span>
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: C.line }}>
                  <div className="h-full rounded-full" style={{
                    width: `${(b.actual_rate || 0) * 100}%`,
                    background: Math.abs(b.gap || 0) > 0.15 ? C.away : C.home,
                  }} />
                </div>
                <span className="w-8 text-right tabular-nums" style={{ color: C.chalk }}>{pct(b.actual_rate)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : cal && cal.graded > 0 ? (
        <div className="mt-3 text-[10px]" style={{ color: C.mute }}>
          Not enough spread across confidence bands yet — keep predicting!
        </div>
      ) : null}
    </div>
  );
}
