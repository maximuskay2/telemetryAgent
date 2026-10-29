"use client";

import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { EmptyState } from "../ui";
import Tabs from "../ui/Tabs";
import GateCard from "./GateCard";
import { groupGateDecisions } from "./lib/gate";
import IncidentCard from "./IncidentCard";
import IncidentDrawer from "./IncidentDrawer";
import NewIncidentSheet from "./NewIncidentSheet";
import { useMission } from "./state";

type TabId = "all" | "incidents" | "ignored" | "observing";

/** Incidents + gate rail: tabs, cards, detail drawer, new-incident sheet. */
export default function IncidentsPane() {
  const { incidentList, decisions, counts, selectedRunId, setSelectedRunId } = useMission();
  const [tab, setTab] = useState<TabId>("all");
  const [sheetOpen, setSheetOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  function onListKeyDown(event: KeyboardEvent) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const cards = listRef.current?.querySelectorAll("article") ?? [];
    if (cards.length < 2) return;
    const current = (event.target as HTMLElement).closest("article");
    const index = [...cards].indexOf(current as HTMLElement);
    if (index === -1) return;
    event.preventDefault();
    const next =
      event.key === "ArrowDown"
        ? cards[(index + 1) % cards.length]
        : cards[(index - 1 + cards.length) % cards.length];
    (next.querySelector("button") as HTMLElement | null)?.focus();
  }

  const ignored = useMemo(
    () => groupGateDecisions(decisions.filter((d) => d.decision === "suppress")),
    [decisions],
  );
  const observing = useMemo(
    () => groupGateDecisions(decisions.filter((d) => d.decision === "observe")),
    [decisions],
  );
  const openEntry = incidentList.find((e) => e.runId === selectedRunId) ?? null;

  const showIncidents = tab === "all" || tab === "incidents";
  const showIgnored = tab === "all" || tab === "ignored";
  const showObserving = tab === "all" || tab === "observing";
  const empty =
    (tab === "incidents" && incidentList.length === 0) ||
    (tab === "ignored" && ignored.length === 0) ||
    (tab === "observing" && observing.length === 0) ||
    (tab === "all" &&
      incidentList.length === 0 &&
      ignored.length === 0 &&
      observing.length === 0);

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <Tabs
          tabs={[
            { id: "all", label: "All" },
            { id: "incidents", label: "Incidents", count: incidentList.length },
            { id: "ignored", label: "Ignored as normal", count: counts.suppress },
            { id: "observing", label: "Keeping an eye on it", count: counts.observe },
          ]}
          active={tab}
          onChange={(id) => setTab(id as TabId)}
        />
        <button
          type="button"
          onClick={() => setSheetOpen(true)}
          className="shrink-0 rounded-md bg-brand-cyan px-2.5 py-1.5 text-xs font-semibold text-[#0b1710] hover:brightness-110"
        >
          + New incident
        </button>
      </div>

      <div
        ref={listRef}
        onKeyDown={onListKeyDown}
        className="flex min-h-0 flex-col gap-2 overflow-y-auto"
      >
        {empty ? (
          <EmptyState
            title={
              tab === "ignored"
                ? "Nothing ignored yet"
                : tab === "observing"
                  ? "Nothing under watch"
                  : "No incidents yet"
            }
            hint="Run the full demo, start traffic, or open a new incident."
          />
        ) : (
          <>
            {showIncidents &&
              incidentList.map((entry) => (
                <IncidentCard
                  key={entry.runId}
                  entry={entry}
                  onOpen={(runId) => setSelectedRunId(runId)}
                />
              ))}
            {showObserving &&
              observing.map((group) => <GateCard key={group.key} group={group} />)}
            {showIgnored &&
              ignored.map((group) => <GateCard key={group.key} group={group} />)}
          </>
        )}
      </div>

      {openEntry && (
        <IncidentDrawer entry={openEntry} onClose={() => setSelectedRunId(null)} />
      )}
      {sheetOpen && <NewIncidentSheet onClose={() => setSheetOpen(false)} />}
    </div>
  );
}
