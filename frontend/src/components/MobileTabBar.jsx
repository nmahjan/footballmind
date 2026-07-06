import { C } from "../fm/theme.js";

const MATCH_TABS = [
  { id: "chat", label: "Chat" },
  { id: "data", label: "Data" },
  { id: "fixtures", label: "Fixtures" },
];

const PLAYER_TABS = [
  { id: "chat", label: "Chat" },
  { id: "players", label: "Players" },
];

export default function MobileTabBar({ mode, tab, setTab }) {
  const tabs = mode === "players" ? PLAYER_TABS : MATCH_TABS;
  return (
    <nav
      className="sticky bottom-0 z-20 flex border-t md:hidden"
      style={{ borderColor: C.line, background: C.panel2 }}>
      {tabs.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          onClick={() => setTab(id)}
          className="flex-1 py-2.5 text-xs font-semibold transition-colors"
          style={{
            color: tab === id ? C.home : C.mute,
            borderTop: tab === id ? `2px solid ${C.home}` : "2px solid transparent",
          }}>
          {label}
        </button>
      ))}
    </nav>
  );
}

export function mobilePanelClass(tab, panelId) {
  return tab === panelId ? "flex flex-col gap-4 min-w-0" : "hidden md:flex md:flex-col md:gap-4 md:min-w-0";
}
