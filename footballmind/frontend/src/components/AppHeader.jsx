import { C } from "../fm/theme.js";

export default function AppHeader({ offline, backendStatus }) {
  let badge;
  if (offline) {
    badge = (
      <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.away }}>
        demo data
      </span>
    );
  } else if (backendStatus === "connecting") {
    badge = (
      <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.mute }}>
        connecting…
      </span>
    );
  } else if (backendStatus === "unreachable") {
    badge = (
      <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.away }}>
        backend waking up
      </span>
    );
  } else {
    badge = (
      <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: C.panel, color: C.home }}>
        live
      </span>
    );
  }

  return (
    <header className="sticky top-0 z-30 border-b px-5 py-3 backdrop-blur-xl"
      style={{ borderColor: C.line, background: "rgba(13,17,23,0.88)" }}>
      <div className="mx-auto flex max-w-[1680px] items-center justify-between">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className="text-lg font-bold tracking-tight">Football Mind</span>
          <span className="hidden text-xs sm:inline" style={{ color: C.mute }}>
            Match Intelligence · By Neil M.
          </span>
        </div>
        {badge}
      </div>
    </header>
  );
}
