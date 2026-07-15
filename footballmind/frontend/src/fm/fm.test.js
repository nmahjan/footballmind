import { describe, it, expect } from "vitest";
import { pct, outcomeColor, localDayKey, dayHeaderLabel, fixtureTeamStyle, fixturePreviewLabel } from "./format.js";
import { C, flagCode } from "./theme.js";
import { parseVs, buildPredictUrl } from "./deeplink.js";
import { zoneForRank, rowZone, standingLegend } from "./standings.js";
import { bracketDisplayTeam, bracketDisplayWinner, normaliseBracket } from "../components/BracketPanel.jsx";

describe("format", () => {
  it("pct rounds to whole percent", () => {
    expect(pct(0.623)).toBe("62%");
    expect(pct(null)).toBe("0%");
  });

  it("outcomeColor picks team colors", () => {
    expect(outcomeColor("Spain win", "Spain", "Germany")).toBe(C.home);
    expect(outcomeColor("Draw", "Spain", "Germany")).toBe(C.draw);
  });

  it("fixtureTeamStyle highlights pick and underdog", () => {
    const preview = { prediction: "Spain", confidence: 0.58 };
    expect(fixtureTeamStyle("Spain", "Spain", "Germany", preview).color).toBe(C.home);
    expect(fixtureTeamStyle("Germany", "Spain", "Germany", preview).color).toBe(C.away);
    const draw = { prediction: "Draw", confidence: 0.31 };
    expect(fixtureTeamStyle("Spain", "Spain", "Germany", draw).color).toBe(C.draw);
  });

  it("fixturePreviewLabel normalizes knockout picks", () => {
    expect(fixturePreviewLabel({ prediction: "Draw" })).toBe("Draw");
    expect(fixturePreviewLabel({
      prediction: "Brazil advance",
      is_knockout: true,
    })).toBe("Brazil");
  });

  it("localDayKey uses local calendar date", () => {
    const key = localDayKey("2026-07-01T22:00:00Z");
    expect(key).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("dayHeaderLabel marks today", () => {
    const now = new Date();
    const key = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    expect(dayHeaderLabel(key)).toBe("Today");
  });
});

describe("theme flags", () => {
  it("maps national teams to cross-platform flag image codes", () => {
    expect(flagCode("Argentina")).toBe("ar");
    expect(flagCode("United States")).toBe("us");
    expect(flagCode("England")).toBe("gb-eng");
    expect(flagCode("Austria")).toBe("at");
    expect(flagCode("Congo DR")).toBe("cd");
    expect(flagCode("Curaçao")).toBe("cw");
    expect(flagCode("Iraq")).toBe("iq");
    expect(flagCode("Jordan")).toBe("jo");
    expect(flagCode("Tunisia")).toBe("tn");
    expect(flagCode("Uzbekistan")).toBe("uz");
  });
});

describe("deeplink", () => {
  it("parseVs extracts teams", () => {
    expect(parseVs("Predict Spain vs Germany")).toEqual({ home: "Spain", away: "Germany" });
    expect(parseVs("Who will win Brazil vs Argentina?")).toEqual({ home: "Brazil", away: "Argentina" });
  });

  it("buildPredictUrl uses hash params", () => {
    const url = buildPredictUrl("Mexico", "USA", { comp: "WC", neutral: true });
    expect(url).toContain("#predict=Mexico+vs+USA");
    expect(url).toContain("neutral=1");
  });
});

describe("standings", () => {
  it("zoneForRank marks UCL spots in PL", () => {
    const z = zoneForRank("PL", 1, 20);
    expect(z?.short).toBe("UCL");
  });

  it("rowZone uses conference for MLS", () => {
    const z = rowZone("MLS", { rank: 1, conference: "East" }, 14);
    expect(z).toBeTruthy();
  });

  it("standingLegend returns PL zones", () => {
    expect(standingLegend("PL").length).toBeGreaterThan(0);
  });
});

describe("bracket projection", () => {
  it("uses projected teams and winner only when predictions are on", () => {
    const match = {
      home: "TBD",
      away: "TBD",
      projected_home: "Spain",
      projected_away: "Brazil",
      projected_winner: "Spain",
      home_goals: null,
      away_goals: null,
    };

    expect(bracketDisplayTeam(match, "home", false)).toBe("TBD");
    expect(bracketDisplayWinner(match, "TBD", "TBD", false)).toBeNull();
    expect(bracketDisplayTeam(match, "home", true)).toBe("Spain");
    expect(bracketDisplayTeam(match, "away", true)).toBe("Brazil");
    expect(bracketDisplayWinner(match, "Spain", "Brazil", true)).toBe("Spain");
  });

  it("does not render third-place as part of the main bracket tree", () => {
    const rounds = normaliseBracket([
      { round: "semi_final", matches: [{ home: "Spain", away: "France" }] },
      { round: "final", matches: [{ home: "Spain", away: "Argentina" }] },
      { round: "third_place", matches: [{ home: "France", away: "England" }] },
    ]);

    expect(rounds.map((r) => r.round)).toEqual(["semi_final", "final"]);
  });
});
