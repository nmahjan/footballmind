import { useEffect, useMemo, useState } from "react";
import { cachedJson } from "../fm/cache.js";
import { COMP_LABELS, FIXTURE_TABS } from "../fm/demo.js";
import { fmtDate, outcomeColor, pct } from "../fm/format.js";
import { C, TeamLabel } from "../fm/theme.js";

function stageLabel(stage) {
  return {
    group: "Group",
    regular_season: "League",
    round_of_32: "Round of 32",
    round_of_16: "Round of 16",
    quarter_final: "Quarter-final",
    semi_final: "Semi-final",
    final: "Final",
    third_place: "Third place",
  }[stage] ?? stage ?? "Match";
}

function PredictionCard({ row }) {
  const predColor = outcomeColor(row.prediction, row.home, row.away);
  const graded = row.was_correct !== null && row.was_correct !== undefined;
  return (
    <div className="rounded-lg border p-3" style={{ borderColor: C.line, background: C.panel2 }}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold" style={{ color: C.chalk }}>
            <TeamLabel name={row.home} /> <span style={{ color: C.mute }}>vs</span> <TeamLabel name={row.away} />
          </div>
          <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px]" style={{ color: C.mute }}>
            <span>{COMP_LABELS[row.comp] ?? row.comp ?? "Prediction"}</span>
            {row.season && <span>· {row.season}</span>}
            {row.stage && <span>· {stageLabel(row.stage)}</span>}
          </div>
        </div>
        {graded ? (
          <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold"
            style={{
              background: row.was_correct ? "rgba(52,211,153,0.15)" : "rgba(244,161,82,0.15)",
              color: row.was_correct ? C.home : C.away,
            }}>
            {row.was_correct ? "Correct" : "Miss"}
          </span>
        ) : (
          <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold"
            style={{ background: C.line, color: C.mute }}>
            Open
          </span>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 text-[11px]">
        <span style={{ color: C.mute }}>Pick</span>
        <span className="font-semibold tabular-nums" style={{ color: predColor }}>
          {row.prediction} · {pct(row.confidence)}
        </span>
      </div>
      {row.score && (
        <div className="mt-1 flex items-center justify-between gap-3 text-[11px]">
          <span style={{ color: C.mute }}>Result</span>
          <span className="font-semibold" style={{ color: C.chalk }}>
            {row.score}{row.actual ? ` · ${row.actual}` : ""}
          </span>
        </div>
      )}
      <div className="mt-2 border-t pt-2 text-[10px]" style={{ borderColor: C.line, color: C.mute }}>
        Predicted {fmtDate(row.created_at)}
        {row.match_date && <span> · Match {fmtDate(row.match_date)}</span>}
      </div>
    </div>
  );
}

function optionsFromPayload(filters) {
  const byCode = new Map();
  for (const opt of filters?.competitions ?? []) {
    byCode.set(opt.code, opt);
  }
  return FIXTURE_TABS
    .filter((tab) => byCode.has(tab.code))
    .map((tab) => ({ ...tab, ...byCode.get(tab.code) }));
}

export default function PredictionsSidebar({ apiBase, offline, onCompChange }) {
  const [comp, setComp] = useState("");
  const [season, setSeason] = useState("");
  const [rows, setRows] = useState(null);
  const [filters, setFilters] = useState({ competitions: [] });

  const compOptions = useMemo(() => optionsFromPayload(filters), [filters]);
  const activeComp = compOptions.find((opt) => opt.code === comp);
  const seasons = activeComp?.seasons ?? [];

  function load(nextComp = comp, nextSeason = season) {
    if (!apiBase || offline) {
      setRows([]);
      return;
    }
    setRows(null);
    const params = new URLSearchParams({ history: "1", limit: "60" });
    if (nextComp) params.set("comp", nextComp);
    if (nextSeason) params.set("season", nextSeason);
    cachedJson(`${apiBase}/api/predictions?${params.toString()}`, { ttlMs: 60_000 })
      .then((d) => {
        setRows(d.predictions ?? []);
        setFilters(d.filters ?? { competitions: [] });
      })
      .catch(() => setRows([]));
  }

  useEffect(() => {
    load(comp, season);
  }, [apiBase, offline]);

  function pickComp(code) {
    const next = code === comp ? "" : code;
    setComp(next);
    setSeason("");
    onCompChange?.(next || "WC");
    load(next, "");
  }

  function pickSeason(value) {
    setSeason(value);
    load(comp, value);
  }

  return (
    <div className="rounded-lg border flex max-h-[calc(100vh-8rem)] flex-col" style={{ borderColor: C.line, background: C.panel }}>
      <div className="shrink-0 border-b px-4 py-3" style={{ borderColor: C.line }}>
        <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          Prediction History
        </div>
        <p className="mt-1 text-[10px] leading-snug" style={{ color: C.mute }}>
          Past model picks by competition and season. Finished matches show whether the pick graded correct.
        </p>
      </div>

      <div className="shrink-0 space-y-2 border-b px-3 py-2" style={{ borderColor: C.line }}>
        <div className="flex gap-1 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
          <button type="button" onClick={() => pickComp("")}
            className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
            style={{ background: !comp ? C.home : C.line, color: !comp ? "#003919" : C.mute }}>
            All
          </button>
          {compOptions.map((opt) => (
            <button key={opt.code} type="button" onClick={() => pickComp(opt.code)}
              className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
              style={{ background: comp === opt.code ? C.home : C.line, color: comp === opt.code ? "#003919" : C.mute }}>
              {opt.label}
            </button>
          ))}
        </div>
        <select value={season} onChange={(e) => pickSeason(e.target.value)}
          disabled={!comp || seasons.length === 0}
          className="w-full rounded-md px-2 py-1.5 text-xs outline-none disabled:opacity-50"
          style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}>
          <option value="">{comp ? "All years / seasons" : "Pick a competition for years"}</option>
          {seasons.map((yr) => <option key={yr} value={yr}>{yr}</option>)}
        </select>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {rows === null ? (
          <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>Loading predictions...</div>
        ) : rows.length === 0 ? (
          <div className="px-4 py-5 text-center text-xs leading-relaxed" style={{ color: C.mute }}>
            {offline || !apiBase ? "Connect to the backend to browse predictions." : "No predictions found for this filter."}
          </div>
        ) : (
          <div className="space-y-2">
            {rows.map((row) => <PredictionCard key={row.id} row={row} />)}
          </div>
        )}
      </div>
    </div>
  );
}
