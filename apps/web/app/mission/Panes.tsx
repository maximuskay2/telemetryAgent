"use client";

import { useEffect, useState } from "react";
import { Card, ErrorState } from "../ui";
import IncidentsPane from "./IncidentsPane";
import LeftPane from "./LeftPane";
import { useMission } from "./state";
import Toasts from "./Toasts";
import Tour, { type TourSummary } from "./Tour";
import TracePane from "./TracePane";
import VetoRing from "./VetoRing";
import WrapUp from "./WrapUp";

const API_DOWN = "Can't reach the agent API at :8001 — start it with ./scripts/demo.sh";

function Pane({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex min-h-0 flex-col gap-2">
      <header>
        <p className="text-[11px] font-semibold tracking-wide text-text-faint uppercase">
          {eyebrow}
        </p>
        <h2 className="text-sm font-semibold text-text">{title}</h2>
      </header>
      {children}
    </section>
  );
}

export default function MissionPanes() {
  const {
    connection,
    systemsLoaded,
    focusMode,
    setFocusMode,
    presenterMode,
    setPresenterMode,
  } = useMission();
  const live = connection === "connected";
  const loading = connection === "connecting";
  const [tourSummary, setTourSummary] = useState<TourSummary | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "f" || event.key === "F") {
        event.preventDefault();
        setFocusMode(!focusMode);
      } else if (event.key === "p" || event.key === "P") {
        event.preventDefault();
        setPresenterMode(!presenterMode);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focusMode, presenterMode, setFocusMode, setPresenterMode]);

  if (!live && !loading) {
    return (
      <main className="mx-auto w-full max-w-6xl p-6">
        <Card>
          <ErrorState title="Agent API unreachable" hint={API_DOWN} onRetry={() => window.location.reload()} />
        </Card>
      </main>
    );
  }

  return (
    <>
      <main
        style={presenterMode ? { zoom: 1.2 } : undefined}
        className={
          focusMode
            ? "mx-auto w-full max-w-3xl p-3"
            : "mx-auto grid w-full max-w-[1600px] grid-cols-1 gap-3 p-3 lg:grid-cols-[30fr_40fr_30fr]"
        }
      >
        {!focusMode && (
          <Pane eyebrow="World" title="Topology & State">
            {!systemsLoaded || loading ? (
              <Card title="Systems">
                <p className="text-xs text-text-faint">Loading…</p>
              </Card>
            ) : (
              <LeftPane />
            )}
          </Pane>
        )}
        <Pane eyebrow="Work" title="Incidents & Gate">
          <IncidentsPane />
        </Pane>
        {!focusMode && (
          <Pane eyebrow="Agent" title="Trace & Cancel window">
            <VetoRing />
            <TracePane />
          </Pane>
        )}
      </main>
      <Toasts />
      <Tour onComplete={setTourSummary} />
      {tourSummary && (
        <WrapUp
          summary={tourSummary}
          onClose={() => setTourSummary(null)}
        />
      )}
    </>
  );
}
