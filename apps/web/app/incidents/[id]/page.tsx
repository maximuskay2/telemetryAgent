"use client";

import { use, useEffect, useState } from "react";
import type { IncidentEntry } from "../../hooks/useIncidentList";
import { emptyIncident } from "../../hooks/useIncidents";
import { apiUrl, responseDetail } from "../../lib/api";
import type { RunDetail } from "../../types/api";
import { EmptyState } from "../../ui";
import IncidentDrawer from "../../mission/IncidentDrawer";
import { MissionProvider } from "../../mission/state";

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Rebuild the live entry shape from stored steps so the drawer can render. */
function entryFromRun(runId: string, detail: RunDetail): IncidentEntry {
  const steps = detail.steps ?? [];
  const find = (name: string) => steps.find((s) => s.step === name);
  const diagnose = find("diagnose");
  const generate = find("generate");
  const verify = find("verify");
  const done = find("done");
  const status = str((detail.result as { status?: unknown } | null)?.status);
  return {
    ...emptyIncident(),
    runId,
    domain: detail.domain === "appliance" ? "appliance" : "software",
    status: status || str(done?.status) || "done",
    telemetry: str(diagnose?.message),
    diagnosis: str(diagnose?.detail) || str(diagnose?.message),
    diagnosisMeta: str(diagnose?.model),
    suggestions: Array.isArray(diagnose?.suggestions)
      ? (diagnose?.suggestions as unknown[]).filter(
          (s): s is string => typeof s === "string",
        )
      : [],
    fix: str(generate?.detail) || str(generate?.message),
    fixMeta: str(generate?.model),
    verification: str(verify?.detail) || str(verify?.message),
    verificationMeta: str(verify?.model),
    final: str(done?.message),
    activity: "",
  };
}

function IncidentPageBody({ runId }: { runId: string }) {
  const [entry, setEntry] = useState<IncidentEntry | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiUrl}/api/runs/${encodeURIComponent(runId)}`)
      .then(async (response) => {
        if (response.status === 404) throw new Error("missing");
        if (!response.ok) throw new Error(await responseDetail(response));
        return (await response.json()) as RunDetail;
      })
      .then((body) => {
        if (!cancelled) setEntry(entryFromRun(runId, body));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof Error && err.message === "missing") setMissing(true);
        else setError(err instanceof Error ? err.message : "Could not load run.");
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (missing) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-3 bg-bg p-4 text-text">
        <EmptyState
          title="Incident not found"
          hint="Unknown or expired run — the run store is in memory and resets with the API."
        />
        <p>
          <a href="/" className="text-sm text-brand-cyan hover:underline">
            ← Back to mission control
          </a>
        </p>
      </main>
    );
  }

  if (error || !entry) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-3 bg-bg p-4 text-text">
        <p className={error ? "text-sm text-crit" : "text-sm text-text-faint"}>
          {error || "Loading incident report…"}
        </p>
        <p>
          <a href="/" className="text-sm text-brand-cyan hover:underline">
            ← Back to mission control
          </a>
        </p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-bg">
      <IncidentDrawer
        entry={entry}
        onClose={() => {
          window.location.href = "/";
        }}
      />
    </main>
  );
}

export default function IncidentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <MissionProvider>
      <IncidentPageBody runId={id} />
    </MissionProvider>
  );
}
