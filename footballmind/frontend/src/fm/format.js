import { C } from "./theme.js";

export const pct = (x) => `${Math.round((x || 0) * 100)}%`;

export const outcomeColor = (label, home, away) =>
  label?.startsWith(home) ? C.home : label?.startsWith(away) ? C.away : C.draw;

/** Style for a team name in the upcoming-fixtures list from a model preview. */
export function fixtureTeamStyle(team, home, away, preview) {
  if (!preview?.prediction) return { color: C.chalk };
  const pred = preview.prediction;
  if (pred === "Draw") return { color: C.draw };
  const homePick = pred === home || pred.startsWith(home) || pred.includes(`${home} advance`);
  const awayPick = pred === away || pred.startsWith(away) || pred.includes(`${away} advance`);
  if (homePick) {
    return team === home
      ? { color: C.home, fontWeight: 600 }
      : { color: C.away, opacity: 0.92 };
  }
  if (awayPick) {
    return team === away
      ? { color: C.home, fontWeight: 600 }
      : { color: C.away, opacity: 0.92 };
  }
  return { color: C.chalk };
}

export function fixturePreviewLabel(preview) {
  if (!preview?.prediction) return null;
  if (preview.prediction === "Draw") return "Draw";
  if (preview.is_knockout && preview.prediction.includes(" advance")) {
    return preview.prediction.replace(" advance", "");
  }
  return preview.prediction;
}

export function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { weekday: "short", month: "short", day: "numeric" })
    + " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function localDayKey(iso) {
  if (!iso) return "TBD";
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function dayHeaderLabel(dayKey) {
  if (dayKey === "TBD") return "TBD";
  const [y, m, d] = dayKey.split("-").map(Number);
  const target = new Date(y, m - 1, d);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = Math.round((target - today) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  return target.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}
