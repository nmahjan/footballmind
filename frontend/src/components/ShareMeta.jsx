import { useEffect, useState } from "react";
import { parseDeepLinkSearch, parseVs, deepLinkSignature } from "../fm/deeplink.js";

const DEFAULT_TITLE = "FootballMind — Match Intelligence";
const DEFAULT_DESC = "Predict match outcomes, explore squads, and track World Cup & league standings.";

function setMeta(property, content) {
  if (!content) return;
  let el = document.querySelector(`meta[property="${property}"]`)
    || document.querySelector(`meta[name="${property}"]`);
  if (!el) {
    el = document.createElement("meta");
    if (property.startsWith("og:")) el.setAttribute("property", property);
    else el.setAttribute("name", property);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

export default function ShareMeta() {
  const [, bump] = useState(0);

  useEffect(() => {
    const refresh = () => bump((n) => n + 1);
    window.addEventListener("hashchange", refresh);
    window.addEventListener("popstate", refresh);
    return () => {
      window.removeEventListener("hashchange", refresh);
      window.removeEventListener("popstate", refresh);
    };
  }, []);

  useEffect(() => {
    const link = parseDeepLinkSearch();
    if (!link) {
      document.title = DEFAULT_TITLE;
      setMeta("og:title", DEFAULT_TITLE);
      setMeta("og:description", DEFAULT_DESC);
      setMeta("description", DEFAULT_DESC);
      return;
    }
    const teams = parseVs(link.query);
    const title = teams
      ? `FootballMind — ${teams.home} vs ${teams.away}`
      : DEFAULT_TITLE;
    const desc = teams
      ? `AI match prediction: ${teams.home} vs ${teams.away}. Probabilities, form, lineups, and knockout context.`
      : DEFAULT_DESC;
    document.title = title;
    setMeta("og:title", title);
    setMeta("og:description", desc);
    setMeta("description", desc);
    setMeta("og:type", "website");
    setMeta("twitter:card", "summary");
  }, [bump]);

  return null;
}
