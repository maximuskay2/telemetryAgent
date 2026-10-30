// /connect: guided wizard, or the connections panel with ?system=… (N-R4).
"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import ConnectionsPanel from "./ConnectionsPanel";
import Wizard from "./Wizard";

function ConnectInner() {
  const systemId = useSearchParams().get("system");
  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-8">
      <h1 className="mb-1 text-xl font-semibold text-text">
        {systemId ? "Connections" : "Connect your production"}
      </h1>
      <p className="mb-5 text-sm text-text-muted">
        {systemId
          ? "Keys stay server-side; secrets are never shown again."
          : "Eight steps, about ten minutes. Nothing arms until you say so."}
      </p>
      {systemId ? <ConnectionsPanel systemId={systemId} /> : <Wizard />}
    </main>
  );
}

export default function ConnectPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto w-full max-w-2xl px-4 py-8">
          <p className="text-sm text-text-muted">Loading…</p>
        </main>
      }
    >
      <ConnectInner />
    </Suspense>
  );
}
