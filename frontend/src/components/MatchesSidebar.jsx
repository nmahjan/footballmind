import BracketPanel from "./BracketPanel.jsx";
import SyncHealthPanel from "./SyncHealthPanel.jsx";
import FixturesPanel from "./FixturesPanel.jsx";
import RankingsPanel from "./RankingsPanel.jsx";
import CalibrationPanel from "./CalibrationPanel.jsx";

export default function MatchesSidebar({
  summary,
  apiBase,
  offline,
  wcFixtures,
  plFixtures,
  sidebarLoaded,
  onClickFixture,
  onSummary,
  onCompChange,
  chatComp,
}) {
  return (
    <>
      <CalibrationPanel summary={summary} apiBase={apiBase} offline={offline} />
      <SyncHealthPanel apiBase={apiBase} offline={offline} />
      <FixturesPanel
        initialWc={wcFixtures}
        initialPl={plFixtures}
        sidebarLoaded={sidebarLoaded}
        onClickFixture={onClickFixture}
        apiBase={apiBase}
        onSummary={onSummary}
        onCompChange={onCompChange}
      />
      <BracketPanel apiBase={apiBase} offline={offline} defaultComp={chatComp === "CL" ? "CL" : "WC"} />
      <RankingsPanel apiBase={apiBase} offline={offline} />
    </>
  );
}
