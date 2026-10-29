"use client";

import { useMission } from "./state";

const chip =
  "rounded-full border px-2 py-0.5 text-xs whitespace-nowrap";

/** One status chip per tile: gate state > incident activity > baseline > live. */
export default function TileStatus({
  domain,
  systemId,
}: {
  domain: "software" | "appliance";
  systemId: string | null;
}) {
  const { software, appliance, decisions, systems, baselinePct } = useMission();

  if (systemId === null) {
    return (
      <span className={`${chip} border-border text-text-faint`}>Not registered</span>
    );
  }

  const blocked = decisions.some(
    (d) =>
      d.system_id === systemId &&
      (d.decision === "block" || d.decision === "veto" || d.decision === "deny"),
  );
  const suppressing = decisions.some(
    (d) => d.system_id === systemId && d.decision === "suppress",
  );
  const incident = domain === "software" ? software : appliance;
  const failed = incident.status === "error" || incident.status === "FAIL";
  const running = incident.status === "running";
  const system = systems.find((s) => s.system_id === systemId);
  const baseline = baselinePct[systemId];

  if (blocked || failed) {
    return (
      <span className={`${chip} border-crit/50 text-crit`}>
        {failed ? "Failed" : "Blocked"}
      </span>
    );
  }
  if (suppressing) {
    return (
      <span className={`${chip} border-text-faint/50 text-text-faint`}>
        Ignored as normal
      </span>
    );
  }
  if (running) {
    return (
      <span className={`${chip} border-warn/50 text-warn`}>
        Handling incident
      </span>
    );
  }
  if (incident.status === "done" && incident.final !== "") {
    return <span className={`${chip} border-brand-cyan/50 text-brand-cyan`}>Fix ready</span>;
  }
  if (system && system.status !== "confirmed" && system.status !== "armed") {
    return (
      <span className={`${chip} border-border text-text-muted`}>
        {system.status === "learning" && typeof baseline === "number"
          ? `Watching normal ${baseline}%`
          : system.status}
      </span>
    );
  }
  if (system?.status === "armed") {
    return <span className={`${chip} border-ok/50 text-ok`}>Watching</span>;
  }
  return <span className={`${chip} border-brand/50 text-brand-cyan`}>Ready</span>;
}
