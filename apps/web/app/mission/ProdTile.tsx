"use client";

import Link from "next/link";
import type { SystemSummary } from "../types/api";
import TileStatus from "./TileStatus";

/** A connected production system: live gate status plus its setup links. */
export default function ProdTile({ system }: { system: SystemSummary }) {
  const domain = system.kind === "appliance" ? "appliance" : "software";
  const id = encodeURIComponent(system.system_id);
  return (
    <section
      aria-label={system.name}
      className="rounded-lg border border-border bg-surface p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="truncate text-sm font-semibold text-text">
          {system.name}
        </h2>
        <TileStatus domain={domain} systemId={system.system_id} />
      </div>
      <p className="mt-1 font-mono text-xs text-text-faint">
        {system.system_id} · {domain === "software" ? "Software" : "Hardware"}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Link
          href={`/connect?system=${id}`}
          className="inline-block rounded-md border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium text-text hover:bg-surface-2/70"
        >
          Connections
        </Link>
        <Link
          href={`/setup?system=${id}`}
          className="inline-block rounded-md border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium text-text hover:bg-surface-2/70"
        >
          Setup
        </Link>
      </div>
    </section>
  );
}
