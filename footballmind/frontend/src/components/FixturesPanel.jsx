import { useState, useEffect } from "react";
import { C, Flag, TeamLabel } from "../fm/theme.js";
import { pct, outcomeColor, fmtDate, localDayKey, dayHeaderLabel, fixtureTeamStyle, fixturePreviewLabel } from "../fm/format.js";
import { STAGE_BADGE, FIXTURE_TABS, COMP_LABELS, demoPredict } from "../fm/demo.js";

function resolvePreview(f, offline) {
  if (f.preview) return f.preview;
  if (offline && f.home && f.away && !String(f.home).startsWith("TBD")) {
    const p = demoPredict(f.home, f.away);
    return {
      prediction: p.prediction,
      confidence: p.confidence,
      home_win_prob: p.home_win_prob,
      draw_prob: p.draw_prob,
      away_win_prob: p.away_win_prob,
      is_knockout: false,
    };
  }
  return null;
}

function displayTeam(name) {
  if (!name || String(name).startsWith("TBD")) return "TBD";
  return name;
}

function InlineTeam({ name }) {
  return <TeamLabel name={name} className="inline-flex" />;
}

function ResultScoreLine({ r }) {
  if (r.went_to_pens) {
    const rh = r.reg_home_goals ?? r.home_goals;
    const ra = r.reg_away_goals ?? r.away_goals;
    const reg = rh != null && ra != null ? `${rh}–${ra}` : r.score;
    const pens =
      r.home_pens != null && r.away_pens != null
        ? ` (${r.home_pens}–${r.away_pens} pens)`
        : " (pens)";
    return (
      <>
        <InlineTeam name={r.home} />{" "}
        <span className="tabular-nums">{reg}</span>{" "}
        <InlineTeam name={r.away} />
        <span className="font-normal text-xs" style={{ color: C.mute }}>{pens}</span>
      </>
    );
  }
  return (
    <>
      <InlineTeam name={r.home} /> {r.score} <InlineTeam name={r.away} />
    </>
  );
}

function FixtureRow({ f, comp, onClick, offline }) {
  const home = displayTeam(f.home);
  const away = displayTeam(f.away);
  const preview = resolvePreview(f, offline);
  const pick = fixturePreviewLabel(preview);
  const homeStyle = fixtureTeamStyle(home, home, away, preview);
  const awayStyle = fixtureTeamStyle(away, home, away, preview);
  const scored = f.home_goals != null;

  return (
    <button onClick={() => onClick({ ...f, home, away, comp })}
      className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-opacity hover:opacity-70"
      style={{ background: "transparent" }}>
      <span className="shrink-0 rounded px-2 py-0.5 text-center text-[10px] font-semibold"
        style={{ background: C.line, color: C.mute, minWidth: "2.25rem" }}>
        {STAGE_BADGE[f.stage] ?? "GS"}
      </span>
      <span className="flex min-w-0 flex-1 items-center gap-1 text-xs font-medium">
        <span className="truncate" style={homeStyle}><TeamLabel name={home} /></span>
        <span className="shrink-0 text-[10px]" style={{ color: C.mute }}>vs</span>
        <span className="truncate" style={awayStyle}><TeamLabel name={away} /></span>
      </span>
      {f.live && <span className="shrink-0 animate-pulse text-[9px] font-bold" style={{ color: C.away }}>LIVE</span>}
      {scored ? (
        <span className="shrink-0 text-xs font-bold tabular-nums" style={{ color: C.home }}>{f.home_goals}–{f.away_goals}</span>
      ) : (
        <span className="flex shrink-0 flex-col items-end gap-0.5">
          {pick && (
            <span className="rounded px-1.5 py-0.5 text-[9px] font-bold tabular-nums"
              style={{
                background: pick === "Draw" ? "rgba(154,167,178,0.15)" : "rgba(52,211,153,0.12)",
                color: pick === "Draw" ? C.draw : C.home,
              }}>
              {pick === "Draw" ? "Draw" : <><Flag name={pick} /> {pick}</>} · {pct(preview.confidence)}
            </span>
          )}
          <span className="text-[10px] whitespace-nowrap" style={{ color: C.mute }}>{fmtDate(f.match_date)}</span>
        </span>
      )}
    </button>
  );
}

function PredictionResultsView({ apiBase, comp = "WC", onSummary }) {
  const [rows, setRows] = useState(null);

  function load() {
    if (!apiBase) { setRows([]); return; }
    setRows(null);
    Promise.all([
      fetch(`${apiBase}/api/results?comp=${comp}&limit=40`).then((r) => r.json()),
      fetch(`${apiBase}/api/predictions?finished=1&limit=40`).then((r) => r.json()),
    ])
      .then(([resultsPayload, predsPayload]) => {
        setRows(resultsPayload.results ?? []);
        if (predsPayload.summary && onSummary) onSummary(predsPayload.summary);
      })
      .catch(() => setRows([]));
  }

  useEffect(() => { load(); }, [apiBase, comp]);

  useEffect(() => {
    if (!apiBase) return;
    const id = setInterval(load, 90000);
    return () => clearInterval(id);
  }, [apiBase]);

  if (rows === null) {
    return <div className="px-4 py-4 text-center text-xs" style={{ color: C.mute }}>Loading results…</div>;
  }
  if (rows.length === 0) {
    return (
      <div className="px-4 py-5 text-center text-xs leading-relaxed" style={{ color: C.mute }}>
        No finished {COMP_LABELS[comp] ?? comp} matches in the last two weeks yet.
      </div>
    );
  }

  return (
    <div className="divide-y" style={{ borderColor: C.line }}>
      {rows.map((r) => {
        const predColor = r.predicted ? outcomeColor(r.predicted, r.home, r.away) : C.mute;
        const ok = r.was_correct;
        const hasPred = r.predicted != null;
        return (
          <div key={r.match_id ?? r.id} className="px-4 py-3 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: C.mute }}>
                {r.match_date ? fmtDate(r.match_date) : "Final"}
              </span>
              {hasPred && (
                <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold"
                  style={{
                    background: ok ? "rgba(52,211,153,0.15)" : "rgba(244,161,82,0.15)",
                    color: ok ? C.home : C.away,
                  }}>
                  {ok ? "✓ Correct" : "✗ Miss"}
                </span>
              )}
            </div>
            <div className="text-sm font-semibold" style={{ color: C.chalk }}>
              <ResultScoreLine r={r} />
            </div>
            {hasPred ? (
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px]">
                <span style={{ color: C.mute }}>
                  Predicted:{" "}
                  <span className="font-semibold" style={{ color: predColor }}>
                    {r.predicted === r.home || r.predicted === r.away
                      ? <InlineTeam name={r.predicted} />
                      : r.predicted}
                    {" "}({pct(r.predicted_confidence)})
                  </span>
                </span>
                <span style={{ color: C.mute }}>
                  Actual:{" "}
                  <span className="font-semibold" style={{ color: C.chalk }}>
                    {r.actual === r.home || r.actual === r.away
                      ? <InlineTeam name={r.actual} />
                      : r.actual}
                  </span>
                </span>
              </div>
            ) : (
              <div className="text-[11px]" style={{ color: C.mute }}>Model pick pending sync</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function FixturesPanel({ initialWc, initialPl, sidebarLoaded, onClickFixture, apiBase, onSummary, onCompChange, offline }) {
  const [view, setView] = useState("upcoming");
  const [tab, setTab] = useState("WC");
  // Lazy-loaded tabs only (WC/PL come from parent after async fetch)
  const [cache, setCache] = useState({});
  const [loaded, setLoaded] = useState(new Set());
  const [loading, setLoading] = useState(false);

  function rowsFor(code) {
    if (code === "WC") return initialWc ?? [];
    if (code === "PL") return initialPl ?? [];
    return cache[code] ?? [];
  }

  function switchTab(code) {
    setTab(code);
    onCompChange?.(code);
    if (code === "WC" || code === "PL" || loaded.has(code) || !apiBase) return;
    setLoading(true);
    fetch(`${apiBase}/api/fixtures?comp=${code}&limit=16&preview=1`)
      .then((r) => r.json())
      .then((d) => setCache((c) => ({ ...c, [code]: d.fixtures ?? [] })))
      .catch(() => setCache((c) => ({ ...c, [code]: [] })))
      .finally(() => { setLoaded((s) => new Set(s).add(code)); setLoading(false); });
  }

  const rows = rowsFor(tab);
  const waitingParent = (tab === "WC" || tab === "PL") && apiBase && !sidebarLoaded;

  return (
    <div className="rounded-lg border" style={{ borderColor: C.line, background: C.panel }}>
      <div className="border-b px-4 pt-3 pb-0" style={{ borderColor: C.line }}>
        <div className="mb-2 flex gap-1">
          {[["upcoming", "📅 Upcoming"], ["results", "✅ Results"]].map(([k, lbl]) => (
            <button key={k} onClick={() => setView(k)}
              className="rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
              style={{ background: view === k ? C.home : C.line, color: view === k ? "#003919" : C.mute }}>
              {lbl}
            </button>
          ))}
        </div>
        {view === "upcoming" && (
          <>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
              Upcoming Fixtures
            </div>
            <div className="mb-2 text-[10px]" style={{ color: C.mute }}>
              <span style={{ color: C.home }}>Green</span> = model pick ·{" "}
              <span style={{ color: C.away }}>Orange</span> = underdog ·{" "}
              <span style={{ color: C.draw }}>Gray</span> = draw
            </div>
            <div className="flex gap-1 overflow-x-auto pb-2" style={{ scrollbarWidth: "none" }}>
              {FIXTURE_TABS.map(({ code, label }) => (
                <button key={code} onClick={() => switchTab(code)}
                  className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
                  style={{ background: code === tab ? C.home : C.line, color: code === tab ? "#003919" : C.mute }}>
                  {label}
                </button>
              ))}
            </div>
          </>
        )}
        {view === "results" && (
          <>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
              Recent Results · {COMP_LABELS[tab] ?? tab}
            </div>
            <div className="flex gap-1 overflow-x-auto pb-2" style={{ scrollbarWidth: "none" }}>
              {FIXTURE_TABS.map(({ code, label }) => (
                <button key={code} onClick={() => switchTab(code)}
                  className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
                  style={{ background: code === tab ? C.home : C.line, color: code === tab ? "#003919" : C.mute }}>
                  {label}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      <div>
        {view === "results" ? (
          <PredictionResultsView apiBase={apiBase} comp={tab} onSummary={onSummary} />
        ) : loading || waitingParent ? (
          <div className="px-4 py-4 text-center text-xs" style={{ color: C.mute }}>Loading…</div>
        ) : rows.length === 0 ? (
          <div className="px-4 py-4 text-center text-xs" style={{ color: C.mute }}>No upcoming fixtures found.</div>
        ) : (() => {
          // Group by local calendar date (same timezone as fmtDate), up to 4 days
          const byDate = [];
          const seen = new Set();
          [...rows].sort((a, b) => (a.match_date || "").localeCompare(b.match_date || ""))
            .forEach((f) => {
              const day = localDayKey(f.match_date);
              if (!seen.has(day)) { seen.add(day); byDate.push({ day, games: [] }); }
              byDate[byDate.length - 1].games.push(f);
            });
          const days = byDate.slice(0, 5);
          return days.map(({ day, games }) => {
            const label = dayHeaderLabel(day);
            return (
              <div key={day}>
                <div className="border-t px-4 py-1 text-[10px] font-semibold uppercase tracking-wider"
                  style={{ borderColor: C.line, background: C.panel2, color: C.mute }}>
                  {label} · {games.length} {games.length === 1 ? "match" : "matches"}
                </div>
                {games.map((f, i) => (
                  <div key={i} style={{ borderTop: `1px solid ${C.line}` }}>
                    <FixtureRow f={f} comp={tab} onClick={onClickFixture} offline={offline} />
                  </div>
                ))}
              </div>
            );
          });
        })()}
      </div>
    </div>
  );
}
