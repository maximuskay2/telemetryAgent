"use client";

import { useCallback, useState } from "react";
import type { AgentStepEvent, IncidentState, LogEvent } from "../types/api";
import { stepFeed } from "./useFeed";

export const emptyIncident = (): IncidentState => ({
  runId: "",
  status: "idle",
  source: "",
  startedAt: 0,
  elapsedMs: 0,
  telemetry: "",
  diagnosis: "",
  diagnosisMeta: "",
  suggestions: [],
  fix: "",
  fixMeta: "",
  verification: "",
  verificationMeta: "",
  final: "",
  finalMeta: "",
});

function stageMeta(model: string, ms: number): string {
  const parts: string[] = [];
  if (model) parts.push(model);
  if (ms > 0) parts.push(`${Math.round(ms)}ms`);
  return parts.join(" · ");
}

/** Unchanged reducer: one run per panel; a newer click owns the panel. */
export function applyStep(prev: IncidentState, msg: AgentStepEvent): IncidentState {
  let base = prev;
  if (msg.run_id && msg.run_id !== prev.runId) {
    // A run this panel never started (e.g. from the log watcher): adopt it
    // only when the panel is idle, otherwise a newer click owns the panel.
    if (prev.status === "running") return prev;
    base = {
      ...emptyIncident(),
      status: "running",
      runId: msg.run_id,
      telemetry: `Live incident · run ${msg.run_id}`,
      source: msg.source || "",
      startedAt: Date.now(),
    };
  }
  const next: IncidentState = { ...base, runId: msg.run_id || base.runId };
  if (!next.startedAt) next.startedAt = Date.now();
  if (!next.source && msg.source) next.source = msg.source;
  if (msg.step === "diagnose") {
    next.diagnosis = msg.detail;
    next.diagnosisMeta = stageMeta(msg.model, msg.duration_ms);
    next.suggestions = Array.isArray(msg.suggestions)
      ? msg.suggestions.filter((s): s is string => typeof s === "string")
      : [];
  } else if (msg.step === "generate") {
    const tag = msg.attempt > 0 ? `attempt ${msg.attempt}: ` : "";
    next.fix = `${tag}${msg.detail}`;
    next.fixMeta = stageMeta(msg.model, msg.duration_ms);
  } else if (msg.step === "verify") {
    const tag = msg.attempt > 0 ? `[${msg.status} attempt ${msg.attempt}] ` : "";
    next.verification = `${tag}${msg.detail}`;
    next.verificationMeta = stageMeta(msg.model, msg.duration_ms);
  } else if (msg.step === "done") {
    next.status = msg.status || "done";
    next.final = msg.message;
    next.finalMeta = stageMeta(msg.model, 0);
    next.elapsedMs = Date.now() - (next.startedAt || Date.now());
  }
  return next;
}

export function laneProps(incident: IncidentState) {
  return {
    reached: [
      incident.telemetry !== "",
      incident.runId !== "" || incident.status === "running",
      incident.diagnosis !== "",
      incident.verification !== "",
      incident.final !== "",
    ],
    running: incident.status === "running",
    failed: incident.status === "error" || incident.status === "FAIL",
  };
}

export function useIncidents() {
  const [software, setSoftware] = useState<IncidentState>(emptyIncident);
  const [appliance, setAppliance] = useState<IncidentState>(emptyIncident);

  const applyAgentStep = useCallback((msg: AgentStepEvent): LogEvent | null => {
    const update = msg.domain === "software" ? setSoftware : setAppliance;
    update((prev) => applyStep(prev, msg));
    return stepFeed(msg);
  }, []);

  const reset = useCallback(() => {
    setSoftware(emptyIncident());
    setAppliance(emptyIncident());
  }, []);

  return { software, appliance, setSoftware, setAppliance, applyAgentStep, reset };
}
