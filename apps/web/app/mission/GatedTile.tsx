"use client";

import Link from "next/link";
import TileStatus from "./TileStatus";

type GatedTileProps = {
  domain: "software" | "appliance";
  title: string;
  systemId: string | null;
  systemName: string | null;
  status: string | null;
};

/** Placeholder shown until its system is armed: nothing streams, nothing runs. */
export default function GatedTile({
  domain,
  title,
  systemId,
  systemName,
  status,
}: GatedTileProps) {
  const missing = systemId === null;
  return (
    <section
      aria-label={title}
      className="rounded-lg border border-dashed border-border bg-surface p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-text-muted">{title}</h2>
        <TileStatus domain={domain} systemId={systemId} />
      </div>
      <p className="mt-3 text-sm text-text-muted">
        {missing
          ? domain === "software"
            ? "No shop registered yet. Watching starts after setup."
            : "No freezer registered yet. Watching starts after setup."
          : `${systemName ?? "This system"} is ${status === "confirmed" ? "ready — start watching" : (status ?? "not watching yet")}.`}
      </p>
      <Link
        href={missing ? "/setup" : `/setup?system=${systemId}`}
        className="mt-3 inline-block rounded-md border border-brand/50 bg-brand/10 px-3 py-1.5 text-xs font-medium text-brand-cyan hover:bg-brand/20"
      >
        {missing ? "Set up now →" : "Finish setup →"}
      </Link>
    </section>
  );
}
