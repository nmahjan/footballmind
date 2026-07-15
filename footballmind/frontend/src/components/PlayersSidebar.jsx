import { useState, useEffect } from "react";
import { C, TeamLabel } from "../fm/theme.js";

const COMP_OPTIONS = [
  ["WC", "🌍 World Cup"], ["PL", "🏴󠁧󠁢󠁥󠁮󠁧󠁿 PL"], ["PD", "🇪🇸 La Liga"],
  ["BL1", "🇩🇪 Bundesliga"], ["SA", "🇮🇹 Serie A"], ["FL1", "🇫🇷 Ligue 1"],
  ["CL", "⭐ CL"], ["MLS", "🇺🇸 MLS"],
];

function formatPlayerMeta(p) {
  const parts = [];
  if (p.line_role) parts.push(p.line_role);
  const eafc = p.eafc;
  if (eafc?.preferred_foot) parts.push(eafc.preferred_foot);
  if (eafc?.overall_rating) parts.push(`OVR ${eafc.overall_rating}`);
  return parts.length ? parts.join(" · ") : null;
}

const POS_META = {
  GK:  { label: "GK",  bg: "#B8860B", fg: "#003919" },
  DEF: { label: "DEF", bg: "#1A6B47", fg: "#E8F5EE" },
  CB:  { label: "CB",  bg: "#1A6B47", fg: "#E8F5EE" },
  LB:  { label: "LB",  bg: "#1E7A52", fg: "#E8F5EE" },
  RB:  { label: "RB",  bg: "#1E7A52", fg: "#E8F5EE" },
  MID: { label: "MID", bg: "#1A3D6B", fg: "#DCE8FF" },
  CM:  { label: "CM",  bg: "#1A3D6B", fg: "#DCE8FF" },
  CDM: { label: "CDM", bg: "#153256", fg: "#DCE8FF" },
  CAM: { label: "CAM", bg: "#24508F", fg: "#DCE8FF" },
  FWD: { label: "FWD", bg: "#7B1F1F", fg: "#FFE0E0" },
  ST:  { label: "ST",  bg: "#7B1F1F", fg: "#FFE0E0" },
  WING:{ label: "WNG", bg: "#9B3030", fg: "#FFE0E0" },
  "?": { label: "?",   bg: "#333",    fg: "#aaa"    },
};
const POS_TABS = [
  { key: "ALL", label: "All" },
  { key: "FWD", label: "⚡ Forwards" },
  { key: "MID", label: "🎯 Midfielders" },
  { key: "DEF", label: "🛡 Defenders" },
  { key: "GK",  label: "🧤 Keepers" },
];

export function SidebarModeToggle({ mode, setMode }) {
  return (
    <div className="flex rounded-lg border p-0.5" style={{ borderColor: C.line, background: C.panel2 }}>
      {[
        { key: "matches", label: "⚽ Matches" },
        { key: "players", label: "👤 Players" },
      ].map(({ key, label }) => (
        <button key={key} onClick={() => setMode(key)}
          className="flex-1 rounded-md px-3 py-2 text-xs font-semibold transition-colors"
          style={{
            background: mode === key ? C.home : "transparent",
            color: mode === key ? "#003919" : C.mute,
          }}>
          {label}
        </button>
      ))}
    </div>
  );
}

function PlayerCard({ p, onSelect, compact }) {
  const pm = POS_META[p.position] ?? POS_META["?"];
  return (
    <button type="button" onClick={() => onSelect?.(p)}
      className={`rounded-lg border text-left transition-opacity hover:opacity-80 w-full ${compact ? "p-2" : "p-2.5 flex flex-col gap-1"}`}
      style={{ borderColor: C.line, background: C.panel2 }}>
      <div className="flex items-start justify-between gap-1">
        <span className={`font-semibold leading-tight ${compact ? "text-[11px]" : "text-xs"}`} style={{ color: C.chalk }}>
          {p.name}
        </span>
        <span className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase"
          style={{ background: pm.bg, color: pm.fg }}>
          {pm.label}
        </span>
      </div>
      <div className="flex items-center justify-between gap-1 mt-0.5">
        <span className="text-[10px] truncate" style={{ color: C.mute }}>
          <TeamLabel name={p.team} />
          {p.club_team && p.club_team !== p.team
            ? ` · ${p.club_team}`
            : p.nationality && p.nationality !== p.team ? ` · ${p.nationality}` : ""}
        </span>
        {p.age && <span className="shrink-0 text-[10px]" style={{ color: C.mute }}>{p.age}y</span>}
      </div>
      {(p.goals != null || p.assists != null) && p.position !== "GK" && p.position !== "DEF" && (
        <div className="text-[10px] font-semibold tabular-nums mt-0.5" style={{ color: C.home }}>
          {p.goals ?? 0}G{p.assists != null ? ` · ${p.assists}A` : ""}
          {p.appearances != null ? ` · ${p.appearances} apps` : ""}
        </div>
      )}
      {p.position === "GK" && (p.ga_per_game != null || p.saves != null) && (
        <div className="text-[10px] font-semibold tabular-nums mt-0.5" style={{ color: C.home }}>
          {p.saves != null ? `${p.saves} saves` : ""}
          {p.saves != null && p.ga_per_game != null ? " · " : ""}
          {p.ga_per_game != null ? `${p.ga_per_game} GA/game` : ""}
          {p.clean_sheets != null && p.team_gp ? ` · ${p.clean_sheets} CS` : ""}
        </div>
      )}
      {p.position === "DEF" && p.ga_per_game != null && (
        <div className="text-[10px] font-semibold tabular-nums mt-0.5" style={{ color: C.home }}>
          {p.clean_sheets != null ? `${p.clean_sheets} clean sheets` : ""}
          {p.clean_sheets != null ? " · " : ""}
          {p.ga_per_game} GA/game
          {p.appearances != null ? ` · ${p.appearances} apps` : ""}
        </div>
      )}
      {p.standout_rating != null && !compact && (
        <div className="mt-1 flex items-center gap-1.5">
          <div className="h-1 flex-1 overflow-hidden rounded-full" style={{ background: C.line }}>
            <div className="h-full rounded-full"
              style={{
                width: `${Math.min(100, Math.round(p.standout_rating))}%`,
                background: pm.bg === "#7B1F1F" ? C.away : pm.bg === "#1A6B47" ? C.home : C.draw,
              }} />
          </div>
          <span className="shrink-0 text-[9px] font-bold tabular-nums" style={{ color: C.mute }}>
            {Math.round(p.standout_rating)}
          </span>
        </div>
      )}
      {p.team_rating != null && !compact && p.standout_rating == null && !(p.goals != null) && (
        <div className="h-0.5 w-full overflow-hidden rounded-full mt-1" style={{ background: C.line }}>
          <div className="h-full rounded-full"
            style={{
              width: `${Math.min(100, Math.round((p.team_rating - 1200) / 8))}%`,
              background: pm.bg === "#7B1F1F" ? C.away : pm.bg === "#1A6B47" ? C.home : C.draw,
            }} />
        </div>
      )}
    </button>
  );
}

function PredictedPitch({ rows, formation, compact = false, label = "Predicted XI" }) {
  const displayRows = [...(rows ?? [])].reverse();
  return (
    <div className="rounded-lg border overflow-hidden" style={{ borderColor: "#2a5c3e", background: "linear-gradient(180deg, #1a4d35 0%, #143d2a 100%)" }}>
      <div className="px-3 py-2 flex items-center justify-between border-b" style={{ borderColor: "#2a5c3e55" }}>
        <span className="text-[11px] font-bold tracking-wider" style={{ color: "#b8e6c8" }}>{formation}</span>
        <span className="text-[9px] uppercase tracking-wider" style={{ color: "#7ab896" }}>{label}</span>
      </div>
      <div className={`px-2 py-3 space-y-2 flex flex-col justify-around ${compact ? "min-h-[120px]" : "min-h-[220px]"}`}>
        {displayRows.map((row, ri) => (
          <div key={ri} className="flex justify-center gap-1.5 flex-wrap">
            {row.players.map((p, pi) => {
              const posKey = p.position ?? row.line;
              const pm = POS_META[posKey] ?? POS_META["?"];
              return (
              <div key={pi} className={`flex flex-col items-center ${compact ? "w-[52px]" : "w-[72px]"}`}>
                <div className={`rounded-full flex items-center justify-center font-bold border-2 ${compact ? "w-7 h-7 text-[7px]" : "w-9 h-9 text-[8px]"}`}
                  style={{ background: "#0d2818", borderColor: "#4ade80", color: "#ecfdf5" }}>
                  {pm.label}
                </div>
                <span className={`mt-1 font-semibold text-center leading-tight line-clamp-2 w-full ${compact ? "text-[8px]" : "text-[9px]"}`}
                  style={{ color: "#f0fdf4" }}>
                  {p.shirt_number ? `${p.shirt_number} ` : ""}{p.name.split(" ").pop()}
                </span>
                {!compact && (
                  <span className="text-[8px] tabular-nums" style={{ color: "#86efac88" }}>
                    {p.rating != null ? p.rating.toFixed(1) : p.score != null ? Math.round(p.score) : ""}
                  </span>
                )}
              </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function MiniLineupColumn({ teamName, data, loading }) {
  if (loading) {
    return (
      <div className="flex-1 min-w-0 text-[10px]" style={{ color: C.mute }}>
        <TeamLabel name={teamName}>{teamName.split(" ")[0]}…</TeamLabel>
      </div>
    );
  }
  if (!data?.rows?.length) return null;
  const starters = data.rows.flatMap((r) => r.players.map((p) => p.name.split(" ").pop()));
  return (
    <div className="flex-1 min-w-0">
      <div className="text-[10px] font-semibold truncate" style={{ color: C.chalk }}>
        <TeamLabel name={teamName}>{teamName.split(" ")[0]} · {data.formation}</TeamLabel>
      </div>
      <div className="mt-1 text-[9px] leading-snug" style={{ color: C.mute }}>
        {starters.join(", ")}
      </div>
      {data.unavailable?.length > 0 && (
        <div className="mt-1 text-[9px] leading-snug" style={{ color: C.away }}>
          Out: {data.unavailable.map((u) => u.name.split(" ").pop()).join(", ")}
        </div>
      )}
    </div>
  );
}

export function CardPredictedLineups({ home, away, comp, apiBase }) {
  const [homeLineup, setHomeLineup] = useState(null);
  const [awayLineup, setAwayLineup] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!apiBase || !home || !away) return;
    let cancelled = false;
    setLoading(true);
    setHomeLineup(null);
    setAwayLineup(null);
    const c = comp || "WC";
    Promise.all([
      fetch(`${apiBase}/api/players/predicted-lineup?team=${encodeURIComponent(home)}&comp=${c}`)
        .then((r) => (r.ok ? r.json() : null)),
      fetch(`${apiBase}/api/players/predicted-lineup?team=${encodeURIComponent(away)}&comp=${c}`)
        .then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([h, a]) => {
        if (cancelled) return;
        setHomeLineup(h?.error ? null : h);
        setAwayLineup(a?.error ? null : a);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [home, away, comp, apiBase]);

  const hasLineup = homeLineup?.rows?.length || awayLineup?.rows?.length;
  if (!loading && !hasLineup) return null;

  return (
    <div className="mt-3 pt-2.5 border-t" style={{ borderColor: C.line }}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          ⚽ Predicted XI
        </span>
        {hasLineup && (
          <button type="button" onClick={() => setExpanded((v) => !v)}
            className="text-[10px] font-medium transition-opacity hover:opacity-70"
            style={{ color: C.home }}>
            {expanded ? "Compact" : "Pitch view"}
          </button>
        )}
      </div>
      {expanded && hasLineup ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {homeLineup?.rows?.length > 0 && (
            <PredictedPitch rows={homeLineup.rows} formation={homeLineup.formation} compact />
          )}
          {awayLineup?.rows?.length > 0 && (
            <PredictedPitch rows={awayLineup.rows} formation={awayLineup.formation} compact />
          )}
        </div>
      ) : (
        <div className="flex gap-3">
          <MiniLineupColumn teamName={home} data={homeLineup} loading={loading} />
          <MiniLineupColumn teamName={away} data={awayLineup} loading={loading} />
        </div>
      )}
    </div>
  );
}

function AvailabilityAdminPanel({ team, comp, apiBase, adminKey, onUpdated }) {
  const [player, setPlayer] = useState("");
  const [status, setStatus] = useState("injured");
  const [reason, setReason] = useState("");
  const [flags, setFlags] = useState([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!adminKey || !apiBase || !team) return;
    fetch(`${apiBase}/api/players/availability?team=${encodeURIComponent(team)}&comp=${comp}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setFlags(d?.flags ?? []))
      .catch(() => setFlags([]));
  }, [team, comp, apiBase, adminKey, msg]);

  async function submit(e) {
    e.preventDefault();
    if (!player.trim() || busy) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch(`${apiBase}/api/admin/availability`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${adminKey}` },
        body: JSON.stringify({ player: player.trim(), team, comp, status, reason: reason.trim() || null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.message || "Failed");
      setPlayer("");
      setReason("");
      setMsg(`Flagged ${data.player} as ${data.status}`);
      onUpdated?.();
    } catch (err) {
      setMsg(err.message || "Could not save flag");
    } finally {
      setBusy(false);
    }
  }

  async function removeFlag(name) {
    if (busy) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch(`${apiBase}/api/admin/availability`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${adminKey}` },
        body: JSON.stringify({ player: name, team, comp }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed");
      setMsg(`Cleared flag for ${data.player}`);
      onUpdated?.();
    } catch (err) {
      setMsg(err.message || "Could not clear flag");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border p-2.5 space-y-2" style={{ borderColor: C.line, background: C.panel2 }}>
      <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: C.mute }}>
        Admin · flag player out
      </div>
      <form onSubmit={submit} className="space-y-2">
        <input
          value={player}
          onChange={(e) => setPlayer(e.target.value)}
          placeholder="Player name"
          className="w-full rounded-md px-2 py-1.5 text-xs outline-none"
          style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}
        />
        <div className="flex gap-2">
          <select value={status} onChange={(e) => setStatus(e.target.value)}
            className="flex-1 rounded-md px-2 py-1.5 text-xs outline-none"
            style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}>
            <option value="injured">Injured</option>
            <option value="doubtful">Doubtful</option>
            <option value="suspended">Suspended (manual)</option>
          </select>
          <button type="submit" disabled={busy}
            className="shrink-0 rounded-md px-3 py-1.5 text-[10px] font-semibold disabled:opacity-50"
            style={{ background: C.home, color: "#003919" }}>
            Save
          </button>
        </div>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason (optional) e.g. Hamstring"
          className="w-full rounded-md px-2 py-1.5 text-xs outline-none"
          style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}
        />
      </form>
      {msg && <div className="text-[10px]" style={{ color: C.mute }}>{msg}</div>}
      {flags.length > 0 && (
        <div className="space-y-1 pt-1 border-t" style={{ borderColor: C.line }}>
          <div className="text-[9px] uppercase tracking-wider" style={{ color: C.mute }}>Manual flags</div>
          {flags.map((f) => (
            <div key={f.player} className="flex items-center justify-between gap-2 text-[10px]">
              <span style={{ color: C.chalk }}>{f.player} · {f.status}{f.reason ? ` (${f.reason})` : ""}</span>
              <button type="button" onClick={() => removeFlag(f.player)} disabled={busy}
                className="shrink-0 text-[9px] font-semibold hover:opacity-70"
                style={{ color: C.away }}>
                Clear
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PlayersSidebar({ apiBase, offline, onAsk, onCompChange, adminKey }) {
  const [comp, setComp] = useState("WC");
  const [posTab, setPosTab] = useState("ALL");
  const [tab, setTab] = useState("standouts");
  const [standouts, setStandouts] = useState(null);
  const [teams, setTeams] = useState([]);
  const [team, setTeam] = useState("");
  const [squad, setSquad] = useState(null);
  const [search, setSearch] = useState("");
  const [searchHits, setSearchHits] = useState(null);
  const [scorers, setScorers] = useState(null);
  const [lineup, setLineup] = useState(null);
  const [lineupView, setLineupView] = useState("predicted");

  function loadPredictedLineup(t, c) {
    if (!apiBase || offline || !t) { setLineup(null); return; }
    setLineup(null);
    fetch(`${apiBase}/api/players/predicted-lineup?team=${encodeURIComponent(t)}&comp=${c}`)
      .then((r) => r.json())
      .then((d) => (d.error ? setLineup({ error: d.error }) : setLineup(d)))
      .catch(() => setLineup({ error: "Failed to load predicted lineup" }));
  }

  function reloadLineup() {
    if (team) loadPredictedLineup(team, comp);
  }

  function loadScorers(c) {
    if (!apiBase || offline) { setScorers([]); return; }
    setScorers(null);
    fetch(`${apiBase}/api/players/scorers?comp=${c}&limit=25`)
      .then((r) => r.json())
      .then((d) => setScorers(d.scorers ?? []))
      .catch(() => setScorers([]));
  }

  function loadStandouts(c) {
    if (!apiBase || offline) { setStandouts([]); return; }
    setStandouts(null);
    fetch(`${apiBase}/api/standouts?comp=${c}&limit=40`)
      .then((r) => r.json())
      .then((d) => setStandouts(d.standouts ?? []))
      .catch(() => setStandouts([]));
  }

  function loadTeams(c) {
    if (!apiBase || offline) { setTeams([]); return; }
    fetch(`${apiBase}/api/players/teams?comp=${c}`)
      .then((r) => r.json())
      .then((d) => {
        const list = d.teams ?? [];
        setTeams(list);
        const preferred = list.includes("Spain") ? "Spain" : list[0];
        if (list.length && (!team || !list.includes(team))) setTeam(preferred);
      })
      .catch(() => setTeams([]));
  }

  function loadSquad(t, c) {
    if (!apiBase || offline || !t) { setSquad(null); return; }
    setSquad(null);
    fetch(`${apiBase}/api/players/squad?team=${encodeURIComponent(t)}&comp=${c}`)
      .then((r) => r.json())
      .then((d) => (d.error ? setSquad({ error: d.error }) : setSquad(d)))
      .catch(() => setSquad({ error: "Failed to load squad" }));
  }

  useEffect(() => {
    loadStandouts(comp);
    loadTeams(comp);
    if (tab === "scorers") loadScorers(comp);
  }, [comp, apiBase, offline]);

  useEffect(() => {
    if (tab === "squad" && team) loadSquad(team, comp);
    if (tab === "scorers") loadScorers(comp);
    if (tab === "lineup" && team) loadPredictedLineup(team, comp);
  }, [tab, team, comp, apiBase, offline]);

  function pickComp(c) {
    setComp(c);
    setPosTab("ALL");
    onCompChange?.(c);
  }

  function askPlayer(p) {
    onAsk(`Tell me about ${p.name} (${p.team}) — their role, strengths, and why they matter`);
  }

  function askTeamLineup(t) {
    onAsk(`What's ${t}'s most likely starting XI for ${comp}? Who's out injured or suspended?`);
  }

  function askTeamSquad(t) {
    onAsk(`Explain ${t}'s squad — key players by position and why this team works tactically`);
  }

  function runSearch(e) {
    e?.preventDefault();
    const q = search.trim();
    if (!q || !apiBase || offline) return;
    setSearchHits(null);
    fetch(`${apiBase}/api/players/search?q=${encodeURIComponent(q)}&comp=${comp}`)
      .then((r) => r.json())
      .then((d) => setSearchHits(d.players ?? []))
      .catch(() => setSearchHits([]));
  }

  const visibleStandouts = standouts
    ? (posTab === "ALL" ? standouts : standouts.filter((p) => p.position === posTab))
    : [];

  const squadList = squad?.squad ?? [];
  const squadByPos = squad?.by_position ?? {};

  return (
    <div className="rounded-lg border flex flex-col max-h-[calc(100vh-8rem)]" style={{ borderColor: C.line, background: C.panel }}>
      <div className="border-b px-4 py-2.5 shrink-0" style={{ borderColor: C.line }}>
        <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: C.mute }}>
          Players & Squads
        </div>
        <p className="mt-1 text-[10px]" style={{ color: C.mute }}>
          Tap a player to ask the chat. Standouts use stats from the selected competition only — goals/assists for attackers, clean sheets and low GA for defenders, saves for keepers (max 2 per nation).
        </p>
      </div>

      <div className="border-b px-3 pt-2 pb-2 space-y-1.5 shrink-0" style={{ borderColor: C.line }}>
        <div className="flex gap-1 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
          {COMP_OPTIONS.map(([c, lbl]) => (
            <button key={c} onClick={() => pickComp(c)}
              className="shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors"
              style={{ background: c === comp ? C.home : C.line, color: c === comp ? "#003919" : C.mute }}>
              {lbl}
            </button>
          ))}
        </div>
        <div className="flex gap-1 flex-wrap">
          {[["standouts", "⚡ Standouts"], ["scorers", "🥅 Scorers"], ["lineup", "⚽ Predicted XI"], ["squad", "📋 Squad"]].map(([k, lbl]) => (
            <button key={k} onClick={() => setTab(k)}
              className="flex-1 min-w-[45%] rounded-md px-2 py-1 text-[11px] font-semibold transition-colors"
              style={{ background: tab === k ? C.home : C.line, color: tab === k ? "#003919" : C.mute }}>
              {lbl}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {tab === "standouts" && (
          <>
            <div className="flex gap-1 overflow-x-auto px-3 py-2 border-b" style={{ borderColor: C.line, scrollbarWidth: "none" }}>
              {POS_TABS.map(({ key, label }) => (
                <button key={key} onClick={() => setPosTab(key)}
                  className="shrink-0 rounded-md px-2 py-0.5 text-[10px] font-semibold transition-colors"
                  style={{ background: key === posTab ? C.home : C.line, color: key === posTab ? "#003919" : C.mute }}>
                  {label}
                </button>
              ))}
            </div>
            {standouts === null ? (
              <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>Loading…</div>
            ) : visibleStandouts.length === 0 ? (
              <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>
                {offline || !apiBase ? "Connect to the backend to browse players." : "No squad data — run sync to populate."}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2 p-3">
                {visibleStandouts.map((p, i) => (
                  <PlayerCard key={`${p.name}-${i}`} p={p} onSelect={askPlayer} />
                ))}
              </div>
            )}
          </>
        )}

        {tab === "scorers" && (
          <>
            {scorers === null ? (
              <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>Loading scorers…</div>
            ) : scorers.length === 0 ? (
              <div className="px-4 py-5 text-center text-xs" style={{ color: C.mute }}>
                {offline || !apiBase
                  ? "Connect to the backend."
                  : "No scorer stats yet — run sync to pull league data."}
              </div>
            ) : (
              <div className="divide-y" style={{ borderColor: C.line }}>
                {scorers.map((p) => (
                  <button key={p.rank} type="button" onClick={() => askPlayer(p)}
                    className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:opacity-80"
                    style={{ borderColor: C.line }}>
                    <span className="w-5 shrink-0 text-xs font-bold tabular-nums" style={{ color: C.mute }}>
                      {p.rank}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-semibold truncate" style={{ color: C.chalk }}>{p.name}</div>
                      <div className="text-[10px] truncate" style={{ color: C.mute }}>
                        <TeamLabel name={p.team} />
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-sm font-bold tabular-nums" style={{ color: C.home }}>{p.goals}</div>
                      <div className="text-[10px] tabular-nums" style={{ color: C.mute }}>{p.assists}A</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {tab === "lineup" && (
          <div className="p-3 space-y-3">
            <div className="flex gap-2">
              <select value={team} onChange={(e) => setTeam(e.target.value)}
                className="flex-1 rounded-lg px-2 py-1.5 text-xs outline-none"
                style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}>
                {teams.length === 0
                  ? <option value="">No teams</option>
                  : teams.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              {team && (
                <button type="button" onClick={() => askTeamLineup(team)}
                  className="shrink-0 rounded-lg px-2 py-1.5 text-[10px] font-semibold"
                  style={{ background: C.home, color: "#003919" }}>
                  Ask AI
                </button>
              )}
            </div>
            {lineup === null ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>Building predicted XI…</div>
            ) : lineup.error ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>{lineup.error}</div>
            ) : (
              <>
                {lineup.confirmed?.rows?.length > 0 && (
                  <div className="flex rounded-lg border p-0.5" style={{ borderColor: C.line, background: C.panel2 }}>
                    {[["predicted", "Predicted"], ["confirmed", "Last match"]].map(([k, lbl]) => (
                      <button key={k} type="button" onClick={() => setLineupView(k)}
                        className="flex-1 rounded-md px-2 py-1.5 text-[10px] font-semibold transition-colors"
                        style={{
                          background: lineupView === k ? C.home : "transparent",
                          color: lineupView === k ? "#003919" : C.mute,
                        }}>
                        {lbl}
                      </button>
                    ))}
                  </div>
                )}
                {(() => {
                  const showConfirmed = lineupView === "confirmed" && lineup.confirmed?.rows?.length > 0;
                  const view = showConfirmed ? lineup.confirmed : lineup;
                  const matchMeta = showConfirmed ? lineup.confirmed?.match : null;
                  return (
                    <>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px]" style={{ color: C.mute }}>
                        <span><TeamLabel name={lineup.team} /></span>
                        <span>·</span>
                        <span>{
                          showConfirmed
                            ? `Confirmed vs ${matchMeta?.opponent ?? "opponent"}`
                            : lineup.source === "recent_lineup"
                              ? "Based on last match XI"
                              : lineup.source === "recent_formation"
                                ? "Based on recent formation"
                                : "Depth + form model"
                        }</span>
                        {matchMeta?.match_date && showConfirmed && (
                          <>
                            <span>·</span>
                            <span>{matchMeta.match_date.slice(0, 10)}</span>
                          </>
                        )}
                        {!showConfirmed && lineup.next_opponent && (
                          <>
                            <span>·</span>
                            <span>Next: vs <TeamLabel name={lineup.next_opponent} /></span>
                          </>
                        )}
                      </div>
                      {!showConfirmed && !lineup.confirmed?.rows?.length && (
                        <p className="text-[9px] leading-snug" style={{ color: C.mute }}>
                          Model prediction — not official lineups. Confirmed XIs appear when match detail sync includes lineups (paid API tier).
                        </p>
                      )}
                      {lineup.recent_formations?.length > 0 && !showConfirmed && (
                        <div className="text-[10px]" style={{ color: C.mute }}>
                          Recent: {lineup.recent_formations.join(", ")}
                        </div>
                      )}
                      <PredictedPitch
                        rows={view.rows}
                        formation={view.formation}
                        label={showConfirmed ? "Confirmed XI" : "Predicted XI"}
                      />
                    </>
                  );
                })()}
                {lineup.unavailable?.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider" style={{ color: C.away }}>
                      Out ({lineup.unavailable.length})
                    </div>
                    <div className="space-y-1">
                      {lineup.unavailable.map((u) => (
                        <div key={u.player_id} className="flex items-center justify-between rounded-md border px-2 py-1.5 text-[11px]"
                          style={{ borderColor: C.line, background: C.panel2 }}>
                          <span style={{ color: C.chalk }}>{u.name}</span>
                          <span className="shrink-0 ml-2 text-[10px] font-semibold capitalize"
                            style={{ color: u.status === "suspended" ? C.away : u.status === "injured" ? "#e67e22" : C.mute }}>
                            {u.status}{u.reason ? ` · ${u.reason}` : ""}
                            {u.source && u.source !== "manual" ? ` · ${u.source}` : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {lineup.bench?.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider" style={{ color: C.mute }}>
                      Bench
                    </div>
                    <div className="grid grid-cols-2 gap-1">
                      {lineup.bench.map((p) => (
                        <div key={p.name} className="rounded-md border px-2 py-1 text-[10px]"
                          style={{ borderColor: C.line, background: C.panel2, color: C.chalk }}>
                          <span className="font-medium">{p.name}</span>
                          <span className="ml-1" style={{ color: C.mute }}>{p.position}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {adminKey && team && (
                  <AvailabilityAdminPanel
                    team={team}
                    comp={comp}
                    apiBase={apiBase}
                    adminKey={adminKey}
                    onUpdated={reloadLineup}
                  />
                )}
              </>
            )}
          </div>
        )}

        {tab === "squad" && (
          <div className="p-3 space-y-3">
            <div className="flex gap-2">
              <select value={team} onChange={(e) => setTeam(e.target.value)}
                className="flex-1 rounded-lg px-2 py-1.5 text-xs outline-none"
                style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }}>
                {teams.length === 0
                  ? <option value="">No teams</option>
                  : teams.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              {team && (
                <button type="button" onClick={() => askTeamSquad(team)}
                  className="shrink-0 rounded-lg px-2 py-1.5 text-[10px] font-semibold"
                  style={{ background: C.home, color: "#003919" }}>
                  Ask AI
                </button>
              )}
            </div>
            {squad === null ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>Loading squad…</div>
            ) : squad.error ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>{squad.error}</div>
            ) : squadList.length === 0 ? (
              <div className="text-center text-xs py-4" style={{ color: C.mute }}>No squad on file for {team}.</div>
            ) : (
              <>
                <div className="flex items-center justify-between text-[10px]" style={{ color: C.mute }}>
                  <span><TeamLabel name={squad.team} /></span>
                  <span>{squad.squad_size} players{squad.team_rating ? ` · Elo ${squad.team_rating}` : ""}</span>
                </div>
                {["GK", "DEF", "MID", "FWD"].map((pos) => {
                  const group = squadByPos[pos];
                  if (!group?.length) return null;
                  const pm = POS_META[pos];
                  return (
                    <div key={pos}>
                      <div className="mb-1 text-[10px] font-bold uppercase tracking-wider"
                        style={{ color: pm.fg, background: pm.bg, display: "inline-block", padding: "2px 6px", borderRadius: 4 }}>
                        {pm.label} ({group.length})
                      </div>
                      <div className="space-y-1 mt-1">
                        {group.map((p) => (
                          <button key={p.name} type="button" onClick={() => askPlayer({ ...p, team: squad.team })}
                            className="flex w-full items-center justify-between rounded-md border px-2 py-1.5 text-left hover:opacity-80"
                            style={{ borderColor: C.line, background: C.panel2 }}>
                            <div className="min-w-0">
                              <div className="text-xs font-medium truncate" style={{ color: C.chalk }}>{p.name}</div>
                              {formatPlayerMeta(p) && (
                                <div className="text-[9px] truncate mt-0.5" style={{ color: C.mute }}>
                                  {formatPlayerMeta(p)}
                                </div>
                              )}
                            </div>
                            <span className="text-[10px] shrink-0 ml-2 text-right" style={{ color: C.mute }}>
                              {p.age ? `${p.age}y` : ""}{p.nationality ? ` · ${p.nationality}` : ""}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        )}
      </div>

      <form onSubmit={runSearch} className="border-t p-3 shrink-0 space-y-2" style={{ borderColor: C.line }}>
        <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.mute }}>Search players</div>
        <div className="flex gap-1">
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="e.g. Yamal, Martinez"
            className="flex-1 rounded-lg px-2 py-1.5 text-xs outline-none"
            style={{ background: C.bg, color: C.chalk, border: `1px solid ${C.line}` }} />
          <button type="submit" className="rounded-lg px-2.5 py-1.5 text-xs font-semibold"
            style={{ background: C.line, color: C.chalk }}>Go</button>
        </div>
        {searchHits && (
          searchHits.length === 0
            ? <div className="text-[10px]" style={{ color: C.mute }}>No matches.</div>
            : <div className="grid grid-cols-1 gap-1 max-h-32 overflow-y-auto">
                {searchHits.map((p, i) => (
                  <PlayerCard key={i} p={p} onSelect={askPlayer} compact />
                ))}
              </div>
        )}
      </form>
    </div>
  );
}
