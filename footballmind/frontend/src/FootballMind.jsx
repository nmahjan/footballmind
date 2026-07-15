import { useState, useEffect, useRef, useLayoutEffect } from "react";
import AppHeader from "./components/AppHeader.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import MatchesSidebar from "./components/MatchesSidebar.jsx";
import PlayersSidebar, { SidebarModeToggle } from "./components/PlayersSidebar.jsx";
import GroupsPanel from "./components/GroupsPanel.jsx";
import StandingsPanel from "./components/StandingsPanel.jsx";
import RankingsPanel from "./components/RankingsPanel.jsx";
import MobileTabBar, { mobilePanelClass } from "./components/MobileTabBar.jsx";
import ShareMeta from "./components/ShareMeta.jsx";
import DataPreloader from "./components/visuals/DataPreloader.jsx";
import ShaderWaves from "./components/visuals/ShaderWaves.jsx";
import { C } from "./fm/theme.js";
import { DEMO_FIXTURES } from "./fm/demo.js";
import { getApiBase } from "./fm/api.js";
import { getAdminKey } from "./fm/session.js";
import { useFootballMindChat } from "./hooks/useFootballMindChat.js";

const API_BASE = getApiBase();

export default function FootballMind() {
  const chat = useFootballMindChat(API_BASE);
  const [wcFixtures, setWcFixtures] = useState(API_BASE ? [] : DEMO_FIXTURES);
  const [plFixtures, setPlFixtures] = useState([]);
  const [groups, setGroups] = useState({});
  const [summary, setSummary] = useState(null);
  const [sidebarMode, setSidebarMode] = useState("matches");
  const [sidebarLoaded, setSidebarLoaded] = useState(false);
  const [adminKey, setAdminKey] = useState(() => getAdminKey());
  const [mobileTab, setMobileTab] = useState("chat");
  const [initialLoading, setInitialLoading] = useState(Boolean(API_BASE));
  const [initialLoaderMinDone, setInitialLoaderMinDone] = useState(!API_BASE);
  const sidebarToggleRef = useRef(null);
  const sidebarTopRef = useRef(null);
  const [chatStretchHeight, setChatStretchHeight] = useState(null);

  useLayoutEffect(() => {
    const measure = () => {
      if (window.innerWidth < 768) {
        setChatStretchHeight(null);
        return;
      }
      const toggleH = sidebarToggleRef.current?.offsetHeight ?? 0;
      const topH = sidebarMode === "matches"
        ? (sidebarTopRef.current?.offsetHeight ?? 0)
        : 0;
      const gap = 16;
      const fallbackTop = sidebarMode === "players" ? 320 : 0;
      const total = toggleH + gap + (topH || fallbackTop);
      if (total > 0) setChatStretchHeight(total);
    };

    measure();
    const ro = new ResizeObserver(measure);
    for (const node of [sidebarToggleRef.current, sidebarTopRef.current]) {
      if (node) ro.observe(node);
    }
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [sidebarMode, sidebarLoaded, summary, chat.offline, chat.backendStatus]);

  async function loadSidebarData() {
    if (!API_BASE) return;
    try {
      const [healthRes, wcRes, plRes, grpRes] = await Promise.all([
        fetch(`${API_BASE}/api/health`),
        fetch(`${API_BASE}/api/fixtures?comp=WC&limit=32&preview=1`),
        fetch(`${API_BASE}/api/fixtures?comp=PL&limit=10&preview=1`),
        fetch(`${API_BASE}/api/groups?comp=WC`),
      ]);
      if (!healthRes.ok) throw new Error("health");
      const wcData = await wcRes.json();
      const plData = await plRes.json();
      const grpData = await grpRes.json();
      if (wcData.fixtures) setWcFixtures(wcData.fixtures);
      if (plData.fixtures) setPlFixtures(plData.fixtures);
      if (grpData.groups) setGroups(grpData.groups);
      chat.setOffline(false);
      chat.setBackendStatus("live");
    } catch {
      chat.setBackendStatus((s) => (s === "live" ? "live" : "unreachable"));
    } finally {
      setSidebarLoaded(true);
    }
  }

  useEffect(() => {
    const k = getAdminKey();
    if (k) setAdminKey(k);
  }, []);

  useEffect(() => {
    if (!API_BASE) {
      chat.setOffline(true);
      setSummary({ graded: 0, correct: 0, hit_rate: null });
      return;
    }
    fetch(`${API_BASE}/api/predictions`).then((r) => r.json())
      .then((d) => setSummary(d.summary)).catch(() => {});
    loadSidebarData();
    const reveal = setTimeout(() => setInitialLoaderMinDone(true), 1400);
    const t1 = setTimeout(loadSidebarData, 4000);
    const t2 = setTimeout(loadSidebarData, 12000);
    const poll = setInterval(() => {
      loadSidebarData();
      fetch(`${API_BASE}/api/predictions`).then((r) => r.json())
        .then((d) => setSummary(d.summary)).catch(() => {});
    }, 90000);
    return () => { clearTimeout(reveal); clearTimeout(t1); clearTimeout(t2); clearInterval(poll); };
  }, []);

  useEffect(() => {
    if (!API_BASE) return;
    if (initialLoaderMinDone && sidebarLoaded) setInitialLoading(false);
  }, [initialLoaderMinDone, sidebarLoaded]);

  const showTablesBelowChat = sidebarMode === "matches";

  return (
    <div className="flex min-h-screen w-full flex-col font-sans"
      style={{
        background: `radial-gradient(circle at 16% 0%, ${C.blueGlow}, transparent 32rem), ${C.bg}`,
        color: C.chalk,
      }}>
      <ShareMeta />
      <ShaderWaves />
      <DataPreloader
        loading={initialLoading}
        loadingText="Loading match intelligence"
      />
      <AppHeader offline={chat.offline} backendStatus={chat.backendStatus} />

      <div className="relative z-10 mx-auto flex w-full max-w-[1680px] min-w-0 flex-1 flex-col gap-4 p-4 pb-0 md:flex-row md:items-start md:pb-4">
        <div className="flex min-w-0 flex-1 flex-col gap-4 md:basis-[64%]">
          <div className={mobilePanelClass(mobileTab, "chat")}>
            <ChatPanel
              messages={chat.messages}
              busy={chat.busy}
              loadPhase={chat.loadPhase}
              input={chat.input}
              setInput={chat.setInput}
              send={chat.send}
              startNewChat={chat.startNewChat}
              sidebarMode={sidebarMode}
              venueMode={chat.venueMode}
              setVenueMode={chat.setVenueMode}
              chatComp={chat.chatComp}
              apiBase={API_BASE}
              stretchHeight={chatStretchHeight}
            />
          </div>

          {showTablesBelowChat && (
            <div className={mobilePanelClass(mobileTab, "data")}>
              <div className={`grid min-w-0 gap-4 ${Object.keys(groups).length > 0 ? "md:grid-cols-2" : "grid-cols-1"}`}>
                {Object.keys(groups).length > 0 && <GroupsPanel groups={groups} />}
                <StandingsPanel apiBase={API_BASE} offline={chat.offline} onCompChange={chat.handleCompChange} />
              </div>
              <RankingsPanel apiBase={API_BASE} offline={chat.offline} defaultOpen />
            </div>
          )}
        </div>

        <aside className={`${sidebarMode === "players"
          ? mobilePanelClass(mobileTab, "players")
          : mobilePanelClass(mobileTab, "fixtures")} md:max-w-[36%] md:basis-[36%] md:shrink-0 flex flex-col gap-4`}>
          <div ref={sidebarToggleRef}>
            <SidebarModeToggle mode={sidebarMode} setMode={(m) => { setSidebarMode(m); setMobileTab("chat"); }} />
          </div>
          {sidebarMode === "matches" ? (
            <MatchesSidebar
              summary={summary}
              apiBase={API_BASE}
              offline={chat.offline}
              wcFixtures={wcFixtures}
              plFixtures={plFixtures}
              sidebarLoaded={sidebarLoaded}
              onClickFixture={(f) => { chat.handleFixtureClick(f); setMobileTab("chat"); }}
              onSummary={setSummary}
              onCompChange={chat.handleCompChange}
              chatComp={chat.chatComp}
              topSectionRef={sidebarTopRef}
            />
          ) : (
            <PlayersSidebar apiBase={API_BASE} offline={chat.offline} onAsk={chat.handlePlayerAsk} onCompChange={chat.handleCompChange} adminKey={adminKey} />
          )}
        </aside>
      </div>

      <MobileTabBar mode={sidebarMode} tab={mobileTab} setTab={setMobileTab} />
    </div>
  );
}
