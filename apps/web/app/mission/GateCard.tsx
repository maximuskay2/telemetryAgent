"use client";

import { useMission } from "./state";
import type { GateGroup } from "./lib/gate";

export default function GateCard({ group }: { group: GateGroup }) {
  const { systems, now } = useMission();
  const { decision, count } = group;
  const ignored = decision.decision === "suppress";
  const system =
    systems.find((s) => s.system_id === decision.system_id)?.name ?? decision.system_id;
  const recheckLeft = ignored
    ? null
    : Math.max(0, Math.round(decision.recheck_in_s - (Date.now() / 1000 - decision.ts)));
  void now;

  return (
    <article
      aria-label={`${ignored ? "Ignored as normal" : "Keeping an eye on it"}: ${decision.rule || "gate"}`}
      className="rounded-lg border border-border bg-surface p-3"
    >
      <p className="flex items-center gap-1.5 text-sm text-text">
        <span aria-hidden>{ignored ? "✓" : "◐"}</span>
        <span className="font-medium">
          {ignored ? "Ignored as normal" : "Keeping an eye on it"}
          {count > 1 ? ` ×${count}` : ""}
        </span>
      </p>
      <p className="mt-1 text-xs text-text-muted">
        {decision.rule || "no rule"} · {system || "unknown system"}
      </p>
      {decision.reason && (
        <p className="mt-1 text-xs text-text-muted">{decision.reason}</p>
      )}
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {decision.citation && (
          <a
            href={`/setup`}
            title={`Profile field: ${decision.citation}`}
            className="text-brand-cyan hover:underline"
          >
            {decision.citation}
          </a>
        )}
        {recheckLeft !== null && decision.recheck_in_s > 0 && (
          <span className="tabular-nums text-text-faint">re-check in {recheckLeft} s</span>
        )}
      </div>
    </article>
  );
}
