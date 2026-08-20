import { useEffect, useMemo, useState } from "react";
import { cachedJson } from "../fm/cache.js";
import { COMP_LABELS, FIXTURE_TABS } from "../fm/demo.js";
import { fmtDate, outcomeColor, pct } from "../fm/format.js";
import { C, TeamLabel } from "../fm/theme.js";

const WORLD_CUP_CODE = "WC";
const LEAGUE_CODES = ["PL", "PD", "BL1", "SA", "FL1", "CL", "MLS", "DED"];

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
  const prediction = row.prediction || "No pick";
  const predColor = outcomeColor(prediction, row.home, row.away);
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
          {prediction} · {pct(row.confidence)}
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
  // Always show every fixture tab (PL, La Liga, …) — not only comps that already
  // have saved predictions. Season lists come from the API when available.
  const byCode = new Map();
  for (const opt of filters?.competitions ?? []) {
    byCode.set(opt.code, opt);
  }
  return FIXTURE_TABS.map((tab) => {
    const fromApi = byCode.get(tab.code);
    return {
      ...tab,
      name: fromApi?.name ?? COMP_LABELS[tab.code] ?? tab.label,
      seasons: fromApi?.seasons ?? [],
    };
  });
}

/** Prefer one card per match when chat/history saved multiple picks. */
function dedupePredictions(rows) {
  const seen = new Set();
  const out = [];
  for (const row of rows ?? []) {
    const key = row.match_id != null
      ? `id:${row.match_id}`
      : `fx:${row.home}|${row.away}|${row.match_date ?? ""}|${row.comp ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  return out;
}

export default function PredictionsSidebar({ apiBase, offline, onCompChange }) {
  const [mode, setMode] = useState("wc");
  const [comp, setComp] = useState(WORLD_CUP_CODE);
  const [season, setSeason] = useState("");
  const [rows, setRows] = useState(null);
  const [filters, setFilters] = useState({ competitions: [] });

  const compOptions = useMemo(() => optionsFromPayload(filters), [filters]);
  const leagueOptions = useMemo(
    () => compOptions.filter((opt) => LEAGUE_CODES.includes(opt.code)),
    [compOptions],
  );
  const activeComp = compOptions.find((opt) => opt.code === comp);
  const seasons = activeComp?.seasons ?? [];

  function load(nextComp = comp, nextSeason = season) {
    if (!apiBase || offline) {
      setRows([]);
      return;
    }
    setRows(null);
    const params = new URLSearchParams({ history: "1", limit: "60", comp: nextComp || WORLD_CUP_CODE });
    if (nextSeason) params.set("season", nextSeason);
    cachedJson(`${apiBase}/api/predictions?${params.toString()}`, { ttlMs: 60_000 })
      .then((d) => {
        setRows(dedupePredictions(d.predictions ?? []));
        setFilters(d.filters ?? { competitions: [] });
      })
      .catch(() => setRows([]));
  }

  useEffect(() => {
    load(comp, season);
  }, [apiBase, offline]);

  function pickMode(nextMode) {
    const nextComp = nextMode === "wc"
      ? WORLD_CUP_CODE
      : (leagueOptions.find((opt) => opt.code === comp)?.code ?? leagueOptions[0]?.code ?? "PL");
    setMode(nextMode);
    setComp(nextComp);
    setSeason("");
    onCompChange?.(nextComp);
    load(nextComp, "");
  }

  function pickComp(code) {
    const next = code || comp;
    setComp(next);
    setSeason("");
    onCompChange?.(next);
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
          Past match-linked model picks by competition and season. Finished matches show whether the pick graded correct.
        </p>
      </div>

      <div className="shrink-0 space-y-2 border-b px-3 py-2" style={{ borderColor: C.line }}>
        <div className="grid grid-cols-2 gap-1">
          {[["wc", "🌍 World Cup"], ["leagues", "🏟 Leagues"]].map(([key, label]) => (
            <button key={key} type="button" onClick={() => pickMode(key)}
              className="rounded-md px-2.5 py-1.5 text-[11px] font-semibold transition-colors"
              style={{ background: mode === key ? C.home : C.line, color: mode === key ? "#003919" : C.mute }}>
              {label}
            </button>
          ))}
        </div>
        <div className="flex gap-1 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
          {(mode === "wc" ? compOptions.filter((opt) => opt.code === WORLD_CUP_CODE) : leagueOptions).map((opt) => (
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
          <option value="">All years / seasons</option>
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
