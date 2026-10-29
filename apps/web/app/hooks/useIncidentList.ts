"use client";

import { useCallback, useState } from "react";
import type { AgentStepEvent, IncidentState } from "../types/api";
import { applyStep, emptyIncident } from "./useIncidents";

export type IncidentEntry = IncidentState & {
  domain: "software" | "appliance";
  /** Last step message: the card's "current activity" line. */
  activity: string;
};

const MAX_ENTRIES = 50;

function withActivity(
  entry: IncidentState & { domain: "software" | "appliance"; activity?: string },
  msg: AgentStepEvent,
): IncidentEntry {
  return { ...entry, activity: msg.message || msg.step || entry.activity || "" };
}

/**
 * Incident list keyed by run_id: several runs can be tracked at once and
 * finished incidents stay listed. The classic single-run `useIncidents()`
 * slots are fed separately and stay untouched.
 */
export function useIncidentList() {
  const [entries, setEntries] = useState<IncidentEntry[]>([]);

  const applyListStep = useCallback((msg: AgentStepEvent) => {
    if (!msg.run_id) return;
    const domain = msg.domain === "appliance" ? "appliance" : "software";
    setEntries((current) => {
      const index = current.findIndex((e) => e.runId === msg.run_id);
      if (index === -1) {
        const fresh: IncidentEntry = {
          ...emptyIncident(),
          runId: msg.run_id,
          domain,
          status: "running",
          source: msg.source || "",
          startedAt: Date.now(),
          activity: "",
        };
        return [withActivity({ ...applyStep(fresh, msg), domain }, msg), ...current].slice(
          0,
          MAX_ENTRIES,
        );
      }
      const next = [...current];
      next[index] = withActivity({ ...applyStep(next[index], msg), domain }, msg);
      return next;
    });
  }, []);

  /** List a manual run immediately, before its first step arrives. */
  const seed = useCallback((entry: IncidentEntry) => {
    setEntries((current) =>
      current.some((e) => e.runId === entry.runId)
        ? current
        : [entry, ...current].slice(0, MAX_ENTRIES),
    );
  }, []);

  const patch = useCallback((runId: string, update: Partial<IncidentEntry>) => {
    setEntries((current) =>
      current.map((e) => (e.runId === runId ? { ...e, ...update } : e)),
    );
  }, []);

  const reset = useCallback(() => setEntries([]), []);

  return { entries, applyListStep, seed, patch, reset };
}
