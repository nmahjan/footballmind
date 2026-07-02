import { describe, it, expect } from "vitest";
import { pct, outcomeColor, localDayKey, dayHeaderLabel } from "./format.js";
import { C } from "./theme.js";
import { parseVs, buildPredictUrl } from "./deeplink.js";
import { zoneForRank, rowZone, standingLegend } from "./standings.js";

describe("format", () => {
  it("pct rounds to whole percent", () => {
    expect(pct(0.623)).toBe("62%");
    expect(pct(null)).toBe("0%");
  });

  it("outcomeColor picks team colors", () => {
    expect(outcomeColor("Spain win", "Spain", "Germany")).toBe(C.home);
    expect(outcomeColor("Draw", "Spain", "Germany")).toBe(C.draw);
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
