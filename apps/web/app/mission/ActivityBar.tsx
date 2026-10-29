"use client";

import { Info, OctagonAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { LogEvent } from "../types/api";
import { useMission } from "./state";

function levelIcon(level: string) {
  switch (level) {
    case "ERROR":
      return <OctagonAlert size={13} className="shrink-0 text-crit" aria-hidden />;
    case "WARNING":
      return <TriangleAlert size={13} className="shrink-0 text-warn" aria-hidden />;
    case "DEBUG":
      return <ShieldCheck size={13} className="shrink-0 text-text-faint" aria-hidden />;
    default:
      return <Info size={13} className="shrink-0 text-brand-cyan" aria-hidden />;
  }
}

function Row({ item }: { item: LogEvent }) {
  return (
    <div className="flex items-center gap-2 py-0.5">
      {levelIcon(item.level)}
      <time className="shrink-0 font-mono text-[11px] tabular-nums text-text-faint">
        {new Date(item.timestamp).toLocaleTimeString()}
      </time>
      <span className="shrink-0 font-mono text-[11px] text-text-faint">{item.source}</span>
      <span className="truncate text-xs text-text">
        {item.tag && <span className="me-1 font-mono text-[11px] text-brand-cyan">{item.tag}</span>}
        {item.message}
      </span>
    </div>
  );
}

export default function ActivityBar() {
  const { events, presenterMode } = useMission();
  const [expanded, setExpanded] = useState(false);
  const latest = events.length > 0 ? events[events.length - 1] : null;
  if (presenterMode) return null;

  return (
    <footer className="border-t border-border bg-surface">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse activity feed" : "Expand activity feed"}
        title={expanded ? "Collapse activity feed" : "Expand activity feed"}
        className="flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left outline-none hover:bg-surface-2/50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
      >
        <span className="shrink-0 text-[11px] font-semibold tracking-wide text-text-faint uppercase">
          Activity
        </span>
        {latest ? (
          <span className="flex min-w-0 flex-1 items-center gap-2">
            {levelIcon(latest.level)}
            <time className="shrink-0 font-mono text-[11px] tabular-nums text-text-faint">
              {new Date(latest.timestamp).toLocaleTimeString()}
            </time>
            <span className="truncate text-xs text-text-muted">{latest.message}</span>
          </span>
        ) : (
          <span className="text-xs text-text-faint">Waiting for telemetry…</span>
        )}
        <span className="shrink-0 font-mono text-[11px] tabular-nums text-text-faint">
          {events.length}
        </span>
      </button>
      {expanded && (
        <div className="max-h-56 overflow-y-auto border-t border-border px-3 py-1.5" role="log" aria-label="Activity feed">
          {events.length === 0 ? (
            <p className="py-2 text-xs text-text-faint">
              Nothing yet — inject an incident or start traffic.
            </p>
          ) : (
            [...events].reverse().map((item) => <Row key={item.id} item={item} />)
          )}
        </div>
      )}
    </footer>
  );
}
