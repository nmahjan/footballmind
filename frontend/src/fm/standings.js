export const LEAGUES = [
  { code: "PL",  label: "Premier League",  short: "PL"  },
  { code: "PD",  label: "La Liga",         short: "La Liga" },
  { code: "BL1", label: "Bundesliga",      short: "Bundesliga" },
  { code: "SA",  label: "Serie A",         short: "Serie A" },
  { code: "FL1", label: "Ligue 1",         short: "Ligue 1" },
  { code: "CL",  label: "Champions League", short: "CL"  },
  { code: "DED", label: "Eredivisie",      short: "Eredivisie" },
  { code: "MLS", label: "MLS",             short: "MLS" },
];

export const STANDING_ZONES = {
  PL: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 4 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 5, to: 5 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 6, to: 6 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 3, toEnd: 1 },
  ],
  PD: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 4 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 5, to: 5 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 6, to: 6 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 3, toEnd: 1 },
  ],
  BL1: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 4 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 5, to: 5 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 6, to: 6 },
    { id: "playoff", label: "Relegation play-off", short: "PO", color: "#fbbf24", fromEnd: 3, toEnd: 3 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 2, toEnd: 1 },
  ],
  SA: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 4 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 5, to: 5 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 6, to: 6 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 3, toEnd: 1 },
  ],
  FL1: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 3 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 4, to: 4 },
    { id: "uecl", label: "Conference League", short: "UECL", color: "#a78bfa", from: 5, to: 5 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 3, toEnd: 1 },
  ],
  DED: [
    { id: "ucl", label: "Champions League", short: "UCL", color: "#38bdf8", from: 1, to: 2 },
    { id: "uel", label: "Europa League", short: "UEL", color: "#fb923c", from: 3, to: 3 },
    { id: "playoff", label: "Relegation play-off", short: "PO", color: "#fbbf24", fromEnd: 3, toEnd: 3 },
    { id: "rel", label: "Relegation", short: "REL", color: "#f87171", fromEnd: 2, toEnd: 1 },
  ],
  CL: [
    { id: "r16", label: "Round of 16", short: "R16", color: "#34d399", from: 1, to: 8 },
    { id: "kopo", label: "Knockout play-offs", short: "PO", color: "#fbbf24", from: 9, to: 24 },
    { id: "out", label: "Eliminated", short: "OUT", color: "#64748b", from: 25, to: 99 },
  ],
  MLS: [
    { id: "r1", label: "Round One (best-of-3)", short: "R1", color: "#34d399", from: 1, to: 7 },
    { id: "wc", label: "Wild Card", short: "WC", color: "#fbbf24", from: 8, to: 9 },
    { id: "out", label: "Missed playoffs", short: "OUT", color: "#64748b", from: 10, to: 99 },
  ],
};

export const WC_GROUP_ZONES = [
  { id: "adv", label: "Knockout stage", short: "KO", color: "#34d399", from: 1, to: 2 },
];

export function zoneForRank(compCode, rank, teamCount) {
  const zones = STANDING_ZONES[compCode];
  if (!zones || !rank || !teamCount) return null;
  for (const z of zones) {
    if (z.fromEnd != null) {
      const rankHi = teamCount - z.fromEnd + 1;
      const rankLo = teamCount - (z.toEnd ?? 1) + 1;
      if (rank >= rankHi && rank <= rankLo) {
        return { id: z.id, label: z.label, short: z.short, color: z.color };
      }
    } else if (rank >= z.from && rank <= z.to) {
      return { id: z.id, label: z.label, short: z.short, color: z.color };
    }
  }
  return null;
}

export function standingLegend(compCode) {
  const zones = STANDING_ZONES[compCode] ?? [];
  const seen = new Set();
  return zones.filter((z) => {
    if (seen.has(z.id)) return false;
    seen.add(z.id);
    return true;
  }).map(({ id, label, short, color }) => ({ id, label, short, color }));
}

export function rowZone(compCode, row, teamCount) {
  if (row.zone) return row.zone;
  const count = compCode === "MLS"
    ? (row.conference_team_count ?? teamCount)
    : teamCount;
  return zoneForRank(compCode, row.rank, count);
}

export function standingsSections(compCode, rows) {
  if (compCode !== "MLS") return [{ key: "all", label: null, rows }];
  const east = rows.filter((r) => r.conference === "East");
  const west = rows.filter((r) => r.conference === "West");
  const other = rows.filter((r) => !r.conference);
  const sections = [];
  if (east.length) sections.push({ key: "east", label: "Eastern Conference", rows: east });
  if (west.length) sections.push({ key: "west", label: "Western Conference", rows: west });
  if (other.length) sections.push({ key: "other", label: "Unassigned", rows: other });
  return sections.length ? sections : [{ key: "all", label: null, rows }];
}

export const DEMO_STANDINGS = [
  { rank: 1, team: "Arsenal FC",          P: 38, W: 26, D: 7, L: 5, GD: 44, Pts: 85 },
  { rank: 2, team: "Manchester City FC",  P: 38, W: 24, D: 6, L: 8, GD: 42, Pts: 78 },
  { rank: 3, team: "Manchester United FC",P: 38, W: 21, D: 8, L: 9, GD: 19, Pts: 71 },
  { rank: 4, team: "Aston Villa FC",      P: 38, W: 19, D: 8, L: 11, GD:  7, Pts: 65 },
  { rank: 5, team: "Liverpool FC",        P: 38, W: 17, D: 9, L: 12, GD: 10, Pts: 60 },
];
