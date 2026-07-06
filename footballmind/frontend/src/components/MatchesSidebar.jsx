import BracketPanel from "./BracketPanel.jsx";
import SyncHealthPanel from "./SyncHealthPanel.jsx";
import FixturesPanel from "./FixturesPanel.jsx";
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
  topSectionRef,
}) {
  return (
    <>
      <div ref={topSectionRef} className="flex flex-col gap-4">
        <CalibrationPanel summary={summary} apiBase={apiBase} offline={offline} />
        <SyncHealthPanel apiBase={apiBase} offline={offline} />
      </div>
      <FixturesPanel
        initialWc={wcFixtures}
        initialPl={plFixtures}
        sidebarLoaded={sidebarLoaded}
        onClickFixture={onClickFixture}
        apiBase={apiBase}
        onSummary={onSummary}
        onCompChange={onCompChange}
        offline={offline}
      />
      <BracketPanel apiBase={apiBase} offline={offline} defaultComp={chatComp === "CL" ? "CL" : "WC"} />
    </>
  );
}
