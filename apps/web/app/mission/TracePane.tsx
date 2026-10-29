"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "../ui";
import { apiUrl } from "../lib/api";
import type { RunDetail } from "../types/api";
import { modelProvider } from "./lib/models";
import { useMission } from "./state";

type StepRow = {
  step: string;
  attempt: number;
  model: string;
  status: string;
  message: string;
  duration_ms: number;
  detail: string;
  suggestions: string[];
};

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function toStepRow(raw: Record<string, unknown>): StepRow {
  return {
    step: str(raw.step),
    attempt: typeof raw.attempt === "number" ? raw.attempt : 0,
    model: str(raw.model),
    status: str(raw.status),
    message: str(raw.message),
    duration_ms: typeof raw.duration_ms === "number" ? raw.duration_ms : 0,
    detail: str(raw.detail),
    suggestions: Array.isArray(raw.suggestions)
      ? raw.suggestions.filter((s): s is string => typeof s === "string")
      : [],
  };
}

function Stage({
  name,
  model,
  ms,
  status,
  summary,
}: {
  name: string;
  model?: string;
  ms?: number;
  status?: string;
  summary?: string;
}) {
  return (
    <li className="rounded-md border border-border bg-surface-2 p-2">
      <p className="flex flex-wrap items-baseline gap-x-2 text-xs">
        <span className="font-semibold text-text">{name}</span>
        {status && <span className="text-text-muted">{status}</span>}
        {typeof ms === "number" && ms > 0 && (
          <span className="ml-auto tabular-nums text-text-faint">{Math.round(ms)} ms</span>
        )}
      </p>
      {model && (
        <p className="mt-0.5 text-[11px] text-text-muted">
          {modelProvider(model)}{" "}
          <span className="font-mono text-text-faint">{model}</span>
        </p>
      )}
      {summary && <p className="mt-0.5 line-clamp-3 text-xs text-text-faint">{summary}</p>}
    </li>
  );
}

/** Agent trace for the selected incident, else the latest one. */
export default function TracePane() {
  const { incidentList, selectedRunId, vetoes } = useMission();
  const entry =
    incidentList.find((e) => e.runId === selectedRunId) ?? incidentList[0] ?? null;
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const liveStatus = entry?.status;

  useEffect(() => {
    setDetail(null);
    if (!entry || entry.runId.startsWith("pending-")) return;
    let cancelled = false;
    fetch(`${apiUrl}/api/runs/${encodeURIComponent(entry.runId)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!cancelled && body) setDetail(body as RunDetail);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // Refetch when the live entry finishes so the full step list lands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry?.runId, liveStatus]);

  if (!entry) {
    return (
      <section id="tour-trace" aria-label="Agent trace" className="rounded-lg border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold text-text">Agent trace</h2>
        <div className="mt-2">
          <EmptyState title="No runs yet" hint="Traces appear once an incident runs." />
        </div>
      </section>
    );
  }

  const steps: StepRow[] = (detail?.steps ?? []).map((s) =>
    toStepRow(s as Record<string, unknown>),
  );
  const diagnose = steps.find((s) => s.step === "diagnose");
  const generates = steps.filter((s) => s.step === "generate");
  const verifies = steps.filter((s) => s.step === "verify");
  const done = steps.find((s) => s.step === "done");
  const gate = (detail?.gate ?? {}) as {
    decision?: unknown;
    rule?: unknown;
    reason?: unknown;
  };
  const veto = vetoes[entry.runId];
  const suggestions =
    diagnose && diagnose.suggestions.length > 0 ? diagnose.suggestions : entry.suggestions;

  const gateSummary = str(gate.decision)
    ? `${str(gate.decision)}${str(gate.rule) ? ` · ${str(gate.rule)}` : ""}${str(gate.reason) ? ` — ${str(gate.reason)}` : ""}`
    : entry.source === "watcher" || entry.source === "sensor"
      ? `acted · via ${entry.source}`
      : "manual run · gate skipped";

  return (
    <section id="tour-trace" aria-label="Agent trace" className="rounded-lg border border-border bg-surface p-4">
      <h2 className="text-sm font-semibold text-text">Agent trace</h2>
      <p className="mt-0.5 truncate text-[11px] text-text-faint">
        {entry.runId.startsWith("pending-") ? "submitting…" : entry.runId} · {entry.domain}
      </p>
      <ol className="mt-2 flex flex-col gap-1.5">
        <Stage name="Gate" summary={gateSummary} />
        <Stage
          name="Diagnose"
          model={diagnose?.model || undefined}
          ms={diagnose?.duration_ms}
          status={diagnose?.status || (entry.diagnosis ? "ok" : undefined)}
          summary={
            (diagnose?.detail || diagnose?.message || entry.diagnosis).split("\n")[0] || undefined
          }
        />
        {generates.length > 0
          ? generates.map((gen, i) => (
              <Stage
                key={i}
                name={`Generate${gen.attempt > 0 ? ` · attempt ${gen.attempt}` : ""}`}
                model={gen.model || undefined}
                ms={gen.duration_ms}
                status={gen.status || undefined}
                summary={(gen.detail || gen.message).split("\n")[0] || undefined}
              />
            ))
          : entry.fix && (
              <Stage
                name="Generate"
                status={entry.status}
                summary={entry.fix.split("\n")[0] || undefined}
              />
            )}
        {verifies.length > 0
          ? verifies.map((ver, i) => (
              <Stage
                key={i}
                name={entry.domain === "appliance" ? "Safety" : "Verify"}
                model={ver.model || undefined}
                ms={ver.duration_ms}
                status={ver.status || undefined}
                summary={(ver.detail || ver.message).split("\n")[0] || undefined}
              />
            ))
          : entry.verification && (
              <Stage
                name={entry.domain === "appliance" ? "Safety" : "Verify"}
                status={entry.status}
                summary={entry.verification.split("\n")[0] || undefined}
              />
            )}
        <Stage
          name="Act"
          status={
            done?.status ||
            veto?.state ||
            (entry.status === "running" ? "pending" : entry.status) ||
            undefined
          }
          summary={
            (done?.message || entry.final).split("\n")[0] ||
            (entry.status === "running" ? "waiting for the agent…" : undefined)
          }
        />
      </ol>
      {suggestions.length > 0 && (
        <div className="mt-2">
          <h3 className="text-xs font-semibold tracking-wide text-text-faint uppercase">
            Suggestions
          </h3>
          <ul className="mt-1 flex flex-col gap-1">
            {suggestions.map((s, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-text-muted">
                <span aria-hidden>☐</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
