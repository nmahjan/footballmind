export const STAGE_BADGE = {
  group: "GS", GROUP_STAGE: "GS", group_stage: "GS",
  round_of_32: "R32", LAST_32: "R32",
  round_of_16: "R16", LAST_16: "R16",
  quarter_final: "QF", QUARTER_FINALS: "QF",
  semi_final: "SF", SEMI_FINALS: "SF",
  final: "Final", FINAL: "Final",
};

export const FIXTURE_TABS = [
  { code: "WC",  label: "🌍 WC"         },
  { code: "PL",  label: "🏴󠁧󠁢󠁥󠁮󠁧󠁿 PL"          },
  { code: "PD",  label: "🇪🇸 La Liga"   },
  { code: "BL1", label: "🇩🇪 Bundesliga" },
  { code: "SA",  label: "🇮🇹 Serie A"   },
  { code: "FL1", label: "🇫🇷 Ligue 1"   },
  { code: "CL",  label: "⭐ CL"         },
  { code: "MLS", label: "🇺🇸 MLS"      },
  { code: "DED", label: "🇳🇱 Eredivisie" },
];

export const COMP_LABELS = {
  WC: "World Cup", PL: "Premier League", PD: "La Liga", BL1: "Bundesliga",
  SA: "Serie A", FL1: "Ligue 1", CL: "Champions League", DED: "Eredivisie",
  MLS: "MLS",
};

export const DEMO_FIXTURES = [
  { home: "Mexico", away: "South Africa", match_date: "2026-06-11T19:00:00Z", stage: "group" },
  { home: "South Korea", away: "Czechia", match_date: "2026-06-12T02:00:00Z", stage: "group" },
  { home: "United States", away: "Paraguay", match_date: "2026-06-13T01:00:00Z", stage: "group" },
  { home: "Brazil", away: "Morocco", match_date: "2026-06-13T22:00:00Z", stage: "group" },
];

export function demoPredict(home, away) {
  const edge = (home.length - away.length) * 0.04;
  let h = 0.42 + edge, d = 0.27, a = 0.31 - edge;
  const s = h + d + a; h /= s; d /= s; a /= s;
  const label = h >= d && h >= a ? home : a >= d ? away : "Draw";
  return {
    prediction: label, confidence: Math.max(h, d, a),
    home_win_prob: h, draw_prob: d, away_win_prob: a,
    reasoning: `${home} edged on current form; expected goals ${(1.3 + edge).toFixed(2)}-${(1.1 - edge).toFixed(2)}.`,
    key_factors: [`Form favours ${h > a ? home : away}`, "Home advantage applied", "Demo estimate"],
  };
}
