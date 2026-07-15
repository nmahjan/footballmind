import { useState } from "react";
import { C, flag, TeamLabel } from "../fm/theme.js";
import { pct, outcomeColor } from "../fm/format.js";
import { buildPredictUrl } from "../fm/deeplink.js";
import { readApiError } from "../fm/api.js";
import { CardPredictedLineups } from "./PlayersSidebar.jsx";
import MarkdownBody from "./MarkdownBody.jsx";
import AIOrb from "./visuals/AIOrb.jsx";

function ProbBar({ home, draw, away, homeName, awayName }) {
  const seg = [
    { k: homeName, v: home, c: C.home },
    { k: "Draw",   v: draw, c: C.draw },
    { k: awayName, v: away, c: C.away },
  ];
  return (
    <div>
      <div className="flex h-7 w-full overflow-hidden rounded-md" style={{ background: C.panel2 }}>
        {seg.map((s, i) => (
          <div key={i} className="flex items-center justify-center"
            style={{ width: pct(s.v), background: s.c, minWidth: s.v > 0.06 ? undefined : 0 }}>
            <span className="px-1 text-[11px] font-semibold tabular-nums" style={{ color: "#003919" }}>
              {s.v > 0.12 ? pct(s.v) : ""}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px]" style={{ color: C.mute }}>
        {seg.map((s, i) => (
          <span key={i} className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: s.c }} />
            {s.k} <span className="tabular-nums" style={{ color: C.chalk }}>{pct(s.v)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function AdvanceBar({ prog, homeName, awayName }) {
  const ha = prog?.home_advance ?? 0.5;
  const aa = prog?.away_advance ?? 0.5;
  const seg = [
    { k: homeName, v: ha, c: C.home },
    { k: awayName, v: aa, c: C.away },
  ];
  return (
    <div>
      <div className="flex h-7 w-full overflow-hidden rounded-md" style={{ background: C.panel2 }}>
        {seg.map((s, i) => (
          <div key={i} className="flex items-center justify-center"
            style={{ width: pct(s.v), background: s.c, minWidth: s.v > 0.06 ? undefined : 0 }}>
            <span className="px-1 text-[11px] font-semibold tabular-nums" style={{ color: "#003919" }}>
              {s.v > 0.12 ? pct(s.v) : ""}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px]" style={{ color: C.mute }}>
        {seg.map((s, i) => (
          <span key={i} className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: s.c }} />
            {s.k} advance <span className="tabular-nums" style={{ color: C.chalk }}>{pct(s.v)}</span>
          </span>
        ))}
      </div>
      <p className="mt-1 text-[10px]" style={{ color: C.mute }}>
        Knockout — extra time &amp; penalties if level after 90
      </p>
    </div>
  );
}

const FORM_COLOR = { W: C.home, D: C.draw, L: C.away };

function FormDots({ results, label }) {
  if (!results?.length) return null;
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px]" style={{ color: C.mute }}>{label}</span>
      {results.map((r, i) => (
        <span key={i} className="inline-flex h-4 w-4 items-center justify-center rounded-sm text-[9px] font-bold"
          style={{ background: FORM_COLOR[r] ?? C.line, color: "#003919" }}>
          {r}
        </span>
      ))}
    </div>
  );
}

const KO_STAGES = new Set([
  "round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "third_place",
]);

function knockoutProgression(p, comp) {
  if (p?.progression) return p.progression;
  const stage = p?.stage;
  const knockoutStage = stage && KO_STAGES.has(stage);
  const tournamentCtx = (comp === "WC" || comp === "CL") && stage !== "group";
  if (!knockoutStage && !(tournamentCtx && p?.is_knockout)) return null;
  const d = p.draw_prob ?? 0;
  const hw = p.home_win_prob ?? 0;
  const ha = hw + d * 0.5;
  return { home_advance: ha, away_advance: 1 - ha };
}

export default function PredictionCard({ p, home, away, comp = "WC", neutral = null, apiBase = "" }) {
  const color = outcomeColor(p.prediction, home, away);
  const prog = knockoutProgression(p, comp);
  const isKnockout = Boolean(p.is_knockout || prog);
  const [copied, setCopied] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState(null);

  function share() {
    const url = buildPredictUrl(home, away, { comp, neutral });
    const probs = isKnockout && prog
      ? `${flag(home)}${home} ${pct(prog.home_advance)} · ${flag(away)}${away} ${pct(prog.away_advance)} (advance)`
      : `${flag(home)}${home} ${pct(p.home_win_prob)} · Draw ${pct(p.draw_prob)} · ${flag(away)}${away} ${pct(p.away_win_prob)}`;
    const txt = `${probs}\nPrediction: ${p.prediction} (${pct(p.confidence)} confidence)\n${url}\nvia FootballMind`;
    navigator.clipboard?.writeText(txt).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function copyLink() {
    const url = buildPredictUrl(home, away, { comp, neutral });
    navigator.clipboard?.writeText(url).then(() => {
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    });
  }

  async function analyze() {
    if (analyzing || analysis) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const res = await fetch(`${apiBase}/api/analyze`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ home, away, prediction: p, comp }),
      });
      if (res.status === 429) {
        setAnalyzeError(await readApiError(res));
        return;
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.message || "Failed");
      setAnalysis(data.analysis);
    } catch (e) {
      setAnalyzeError(e.message || "Analysis unavailable");
    } finally {
      setAnalyzing(false);
    }
  }

  const h2h = p.h2h;
  const hasH2h = h2h?.played > 0;

  return (
    <div className="mt-2 rounded-lg border p-4" style={{ borderColor: C.line, background: C.panel, boxShadow: `0 0 0 1px ${C.glow}` }}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <AIOrb size={46} active />
          <div className="min-w-0 text-sm font-semibold" style={{ color: C.chalk }}>
            <TeamLabel name={home} /> <span style={{ color: C.mute }}>vs</span> <TeamLabel name={away} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold" style={{ background: color, color: "#003919" }}>
            {p.prediction} · {pct(p.confidence)}
          </div>
          <button onClick={share} title="Copy prediction summary + link"
            className="rounded px-1.5 py-0.5 text-[11px] transition-opacity hover:opacity-70"
            style={{ background: C.line, color: copied ? C.home : C.mute }}>
            {copied ? "✓" : "⎘"}
          </button>
          <button onClick={copyLink} title="Copy share link"
            className="rounded px-1.5 py-0.5 text-[11px] transition-opacity hover:opacity-70"
            style={{ background: C.line, color: linkCopied ? C.home : C.mute }}>
            {linkCopied ? "✓" : "🔗"}
          </button>
        </div>
      </div>

      {(p.home_form?.length > 0 || p.away_form?.length > 0) && (
        <div className="mt-2.5 flex flex-col gap-1">
          <FormDots results={p.home_form} label={home.split(" ")[0]} />
          <FormDots results={p.away_form} label={away.split(" ")[0]} />
        </div>
      )}

      {p.stakes?.labels?.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1">
          {p.stakes.labels.map((lbl) => (
            <span key={lbl} className="rounded-md px-2 py-0.5 text-[10px] font-semibold"
              style={{ background: "rgba(251,191,36,0.12)", color: "#fbbf24", border: "1px solid rgba(251,191,36,0.35)" }}>
              {lbl}
            </span>
          ))}
        </div>
      )}
      {p.stakes?.summary && (
        <p className="mt-1.5 text-[11px] leading-snug" style={{ color: C.mute }}>{p.stakes.summary}</p>
      )}
      {p.stakes_adjustment?.applied && (
        <p className="mt-1 text-[10px] italic" style={{ color: C.mute }}>
          High-pressure adjustment: xG ×{(p.stakes_adjustment.total_xg_multiplier ?? 1).toFixed(3)}
          {p.stakes_adjustment.draw_tilt != null
            ? ` · draw tilt +${Math.round(p.stakes_adjustment.draw_tilt * 100)}%`
            : ""}
        </p>
      )}

      <div className="mt-3">
        {isKnockout && prog
          ? <AdvanceBar prog={prog} homeName={home} awayName={away} />
          : <ProbBar home={p.home_win_prob} draw={p.draw_prob} away={p.away_win_prob} homeName={home} awayName={away} />}
      </div>

      {hasH2h && (
        <div className="mt-2.5 flex items-center gap-1.5 text-[11px]" style={{ color: C.mute }}>
          <span>H2H ({h2h.played}):</span>
          <span style={{ color: C.home }}>{h2h.home_wins}W</span>
          <span>·</span>
          <span style={{ color: C.draw }}>{h2h.draws}D</span>
          <span>·</span>
          <span style={{ color: C.away }}>{h2h.away_wins}L</span>
          <span style={{ color: C.mute }}>for {home.split(" ")[0]}</span>
        </div>
      )}

      <CardPredictedLineups home={home} away={away} comp={comp} apiBase={apiBase} />

      {p.key_factors?.length > 0 && (
        <ul className="mt-2.5 space-y-1">
          {p.key_factors.map((f, i) => (
            <li key={i} className="flex gap-2 text-xs" style={{ color: C.mute }}>
              <span style={{ color: color }}>▸</span>{f}
            </li>
          ))}
        </ul>
      )}

      {!analysis && !analyzeError && apiBase && (
        <button onClick={analyze} disabled={analyzing}
          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border py-1.5 text-xs font-medium transition-opacity hover:opacity-70 disabled:opacity-40"
          style={{ borderColor: C.line, color: C.mute }}>
          {analyzing
            ? <><AIOrb size={24} active label="" /> Analyzing match…</>
            : <><AIOrb size={22} label="" /> Deep analysis</>}
        </button>
      )}
      {analysis && (
        <div className="mt-3 rounded-lg border-l-2 pl-3 pr-2 py-2.5 text-xs leading-relaxed"
          style={{ borderColor: color, background: C.panel2, color: C.chalk }}>
          <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
            <AIOrb size={24} active label="" />
            AI Analysis
          </div>
          <MarkdownBody text={analysis} size="xs" />
        </div>
      )}
      {analyzeError && (
        <div className="mt-2 text-[11px]" style={{ color: C.away }}>
          {analyzeError}
        </div>
      )}
    </div>
  );
}
