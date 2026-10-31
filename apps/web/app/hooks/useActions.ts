"use client";

import { useCallback, useRef, useState } from "react";
import { apiUrl } from "../lib/api";
import type { LogEvent, VetoAction } from "../types/api";
import { feedItem } from "./useFeed";

export function useActions() {
  const [vetoes, setVetoes] = useState<Record<string, VetoAction>>({});
  const fetchedRuns = useRef<Set<string>>(new Set());
  const knownRuns = useRef<Set<string>>(new Set());

  const applyActionPayload = useCallback((payload: Record<string, unknown>) => {
    const runId = payload.run_id;
    if (typeof runId !== "string" || !runId) return;
    knownRuns.current.add(runId);
    setVetoes((current) => {
      const prev = current[runId];
      const merged: VetoAction = {
        runId,
        domain:
          typeof payload.domain === "string"
            ? payload.domain
            : (prev?.domain ?? ""),
        summary:
          typeof payload.action === "string"
            ? payload.action
            : (prev?.summary ?? ""),
        deadlineMs:
          typeof payload.deadline === "number"
            ? payload.deadline * 1000
            : (prev?.deadlineMs ?? 0),
        secondsLeft:
          typeof payload.seconds_left === "number"
            ? payload.seconds_left
            : typeof payload.seconds === "number"
              ? Math.ceil(payload.seconds)
              : (prev?.secondsLeft ?? 0),
        state:
          typeof payload.state === "string"
            ? payload.state
            : (prev?.state ?? "pending"),
        decidedBy:
          typeof payload.decided_by === "string"
            ? payload.decided_by
            : (prev?.decidedBy ?? ""),
        detail:
          typeof payload.detail === "string"
            ? payload.detail
            : (prev?.detail ?? ""),
        ready:
          typeof payload.ready === "boolean"
            ? payload.ready
            : (prev?.ready ?? true),
      };
      return { ...current, [runId]: merged };
    });
  }, []);

  // Late joiners only see ticks; fetch the full window once per run.
  const fetchRunDecision = useCallback(
    async (runId: string) => {
      if (fetchedRuns.current.has(runId)) return;
      fetchedRuns.current.add(runId);
      try {
        const response = await fetch(`${apiUrl}/api/runs/${runId}`);
        if (!response.ok) return;
        const body = (await response.json()) as { decision?: unknown };
        if (body.decision && typeof body.decision === "object") {
          applyActionPayload(body.decision as Record<string, unknown>);
        }
      } catch {
        fetchedRuns.current.delete(runId);
      }
    },
    [applyActionPayload],
  );

  const applyActionTick = useCallback(
    (payload: Record<string, unknown>) => {
      const runId = payload.run_id;
      const unknown =
        typeof runId === "string" && runId !== "" && !knownRuns.current.has(runId);
      applyActionPayload(payload);
      if (unknown) void fetchRunDecision(runId);
    },
    [applyActionPayload, fetchRunDecision],
  );

  const applyActionResolved = useCallback(
    (payload: Record<string, unknown>): LogEvent | null => {
      applyActionPayload(payload);
      const state = payload.state;
      if (typeof state !== "string" || state === "pending") return null;
      const summary = typeof payload.action === "string" ? payload.action : "action";
      return feedItem(
        "veto",
        state === "auto_applied"
          ? `Auto-applied ✓ at 0s: ${summary}`
          : state === "approved"
            ? `Did it now ✓: ${summary}`
            : state === "disapproved"
              ? `Cancelled — left for a human: ${summary}`
              : `Cancel window ${state}: ${summary}`,
        state === "failed" ? "ERROR" : "INFO",
      );
    },
    [applyActionPayload],
  );

  const reset = useCallback(() => {
    setVetoes({});
    fetchedRuns.current.clear();
    knownRuns.current.clear();
  }, []);

  return { vetoes, applyActionPayload, applyActionTick, applyActionResolved, reset };
}
