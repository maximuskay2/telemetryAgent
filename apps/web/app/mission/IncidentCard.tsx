"use client";

import type { IncidentEntry } from "../hooks/useIncidentList";
import type { VetoAction } from "../types/api";
import { useMission } from "./state";

function sourceBadge(source: string): string {
  switch (source) {
    case "watcher":
      return "Watcher";
    case "sensor":
      return "Sensor";
    case "upload":
      return "Upload";
    case "webhook":
      return "Webhook";
    case "gate":
      return "Gate";
    case "manual":
      return "Manual";
    default:
      return source || "Manual";
  }
}

function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function vetoLabel(veto: VetoAction | undefined): string | null {
  if (!veto) return null;
  switch (veto.state) {
    case "pending":
      return veto.ready ? `Cancel ${veto.secondsLeft}s` : "Verifying fix…";
    case "approved":
      return "Did it now ✓";
    case "auto_applied":
      return "Auto-applied ✓";
    case "disapproved":
      return "Cancelled";
    default:
      return `Cancel ${veto.state}`;
  }
}

export default function IncidentCard({
  entry,
  onOpen,
}: {
  entry: IncidentEntry;
  onOpen: (runId: string) => void;
}) {
  const { systems, now, vetoes, markNormal, warnFixMs } = useMission();
  const running = entry.status === "running";
  const failed = entry.status === "error" || entry.status === "FAIL";
  const verified =
    entry.status === "PASS" ||
    entry.status === "done" ||
    (entry.final !== "" && !failed && !running);
  const system =
    systems.find((s) => s.kind === (entry.domain === "software" ? "software" : "appliance"))
      ?.name ?? (entry.domain === "software" ? "Shop" : "Fridge");
  const veto = vetoes[entry.runId];
  const vetoText = vetoLabel(veto);
  const elapsed = running ? now - entry.startedAt : entry.elapsedMs;
  const title =
    entry.diagnosis.split("\n")[0] || entry.telemetry.split("\n")[0] || "Incident";

  const stages = [
    { label: "CRASH", done: entry.telemetry !== "" },
    { label: "GRAB", done: entry.runId !== "" && !entry.runId.startsWith("pending-") },
    { label: "SUGGEST", done: entry.diagnosis !== "" || entry.suggestions.length > 0 },
    {
      label: entry.domain === "appliance" ? "SAFETY" : "VERIFY",
      done: entry.verification !== "",
    },
    { label: "FIX", done: entry.final !== "" },
  ];

  return (
    <article
      aria-label={`Incident ${entry.runId || "pending"}`}
      className={`rounded-lg border border-border bg-surface p-3 pl-3.5 ${
        running
          ? "border-l-4 border-l-crit"
          : verified
            ? "border-l-4 border-l-ok"
            : failed
              ? "border-l-4 border-l-warn"
              : "border-l-4 border-l-border"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={() => onOpen(entry.runId)}
          className="min-w-0 flex-1 text-left"
        >
          <p className="flex items-center gap-1.5 text-sm font-semibold text-text">
            <span aria-hidden>{entry.domain === "software" ? "🛒" : "❄️"}</span>
            <span className="truncate">{title}</span>
          </p>
          <p className="mt-0.5 truncate text-xs text-text-muted">
            {system} · {entry.runId.startsWith("pending-") ? "submitting…" : entry.runId.slice(0, 12)}
          </p>
        </button>
        <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
          {sourceBadge(entry.source)}
        </span>
      </div>

      <ol aria-label="Progress" className="mt-2 flex items-center gap-1">
        {stages.map((stage, i) => (
          <li key={stage.label} className="flex flex-1 items-center gap-1 last:flex-none">
            <span
              className={`rounded px-1 py-0.5 text-[10px] font-semibold tracking-wide ${
                stage.done ? "bg-ok/15 text-ok" : "bg-surface-2 text-text-faint"
              }`}
            >
              {stage.label}
            </span>
            {i < stages.length - 1 && <span aria-hidden className="h-px flex-1 bg-border" />}
          </li>
        ))}
      </ol>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
        <span className="tabular-nums">
          {running ? `⏱ ${formatElapsed(elapsed)}` : `took ${formatElapsed(elapsed)}`}
        </span>
        {!running && warnFixMs !== null && (
          <span className="tabular-nums">warn→fix {formatElapsed(warnFixMs)}</span>
        )}
        {vetoText && (
          <span className="rounded-full border border-brand-cyan/50 px-2 py-0.5 text-brand-cyan">
            {vetoText}
          </span>
        )}
      </div>
      {running && entry.activity && (
        <p className="mt-1 truncate text-xs text-text-faint">{entry.activity}</p>
      )}

      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onOpen(entry.runId)}
          className="rounded-md border border-border bg-surface-2 px-2.5 py-1 text-xs text-text hover:border-text-faint"
        >
          Open report
        </button>
        {!entry.runId.startsWith("pending-") && (
          <button
            type="button"
            title="Park this incident as normal (pending setup review)"
            onClick={() => markNormal(entry.runId, entry.domain)}
            className="rounded-md border border-border bg-surface-2 px-2.5 py-1 text-xs text-text-muted hover:border-text-faint"
          >
            This is normal
          </button>
        )}
      </div>
    </article>
  );
}
