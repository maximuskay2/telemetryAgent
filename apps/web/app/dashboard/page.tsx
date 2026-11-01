// /dashboard: the signed-in hub. Systems, drafts, recent runs, and
// every destination in one place. Post-login landing.
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import RequireAuth from "../commerce/RequireAuth";
import AccountChrome from "../commerce/AccountChrome";
import {
  APPLIANCE_STEP_TITLES,
  draftStepTitle,
  loadDrafts,
  mergeResumeEntries,
  SOFTWARE_STEP_TITLES,
} from "../connect/draft";
import { useSystems } from "../hooks/useSystems";
import { apiUrl } from "../lib/api";
import { markOnboarded } from "../lib/setupApi";
import { useSession } from "../lib/session";
import {
  loadSetupDrafts,
  STEP_LABELS,
} from "../setup/draft";
import { Card, EmptyState } from "../ui";

type RunRow = {
  run_id: string;
  domain: string;
  status: string;
  decision?: string | null;
  gate_decision?: string | null;
  n_steps?: number;
};

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "armed"
      ? "border-ok/50 text-ok"
      : status === "learning"
        ? "border-brand/50 text-brand-cyan"
        : "border-warn/50 text-warn";
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[11px] ${tone}`}
    >
      {status === "armed" ? "Watching ✓" : status}
    </span>
  );
}

function DecisionPill({ run }: { run: RunRow }) {
  const label = run.decision ?? run.gate_decision ?? run.status;
  return (
    <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-text-muted">
      {label}
    </span>
  );
}

function QuickLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
    >
      {label}
    </Link>
  );
}

export default function DashboardPage() {
  const { getSessionAuth } = useSession();
  const { systems, systemsLoaded } = useSystems();
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [runsFailed, setRunsFailed] = useState(false);

  useEffect(() => {
    // The dashboard is past onboarding: Mission Control opens from here.
    markOnboarded();
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { token, orgId } = getSessionAuth();
        const response = await fetch(`${apiUrl}/api/runs`, {
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(orgId ? { "X-Org-Id": orgId } : {}),
          },
        });
        if (!response.ok) throw new Error("runs failed");
        const body = (await response.json()) as { runs?: RunRow[] };
        if (!cancelled) setRuns([...(body.runs ?? [])].reverse());
      } catch {
        if (!cancelled) setRunsFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [getSessionAuth]);

  const guided = mergeResumeEntries(loadDrafts(), systems);
  const manual = Object.values(loadSetupDrafts())
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .filter((draft) => {
      const server = systems.find((s) => s.system_id === draft.data.systemId);
      return server !== undefined && server.status !== "armed";
    });
  const watching = systems.filter((s) => s.status === "armed").length;

  return (
    <RequireAuth>
      <AccountChrome>
        <main className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 py-8">
          <div>
            <h1 className="text-xl font-semibold text-text">
              Your dashboard
            </h1>
            <p className="mt-1 text-sm text-text-muted">
              {systemsLoaded
                ? `${systems.length} system${systems.length === 1 ? "" : "s"} · ${watching} watching`
                : "Loading your systems…"}
            </p>
          </div>

          <Card
            title="Systems"
            action={
              <Link
                href="/"
                className="rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
              >
                Open Mission Control →
              </Link>
            }
          >
            {!systemsLoaded ? (
              <p className="text-sm text-text-muted">Loading…</p>
            ) : systems.length === 0 ? (
              <EmptyState
                title="No systems yet"
                hint="Connect your first system — guided or manual, about ten minutes."
              />
            ) : (
              <ul className="flex flex-col gap-2">
                {systems.map((system) => {
                  const id = encodeURIComponent(system.system_id);
                  const armed = system.status === "armed";
                  return (
                    <li
                      key={system.system_id}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-surface-2 px-3 py-2"
                    >
                      <span className="text-sm font-medium text-text">
                        {system.name}
                      </span>
                      <span className="font-mono text-xs text-text-faint">
                        {system.system_id}
                      </span>
                      <span className="text-xs text-text-muted">
                        · {system.kind}
                      </span>
                      <StatusPill status={system.status} />
                      <span className="inline-flex flex-wrap gap-2">
                        {armed ? (
                          <Link
                            href="/"
                            className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
                          >
                            Watch
                          </Link>
                        ) : (
                          <Link
                            href={`/connect?resume=${id}`}
                            className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
                          >
                            Continue setup
                          </Link>
                        )}
                        <Link
                          href={`/setup?system=${id}`}
                          className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
                        >
                          Manual setup
                        </Link>
                        <Link
                          href={`/connect?system=${id}`}
                          className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
                        >
                          Connections
                        </Link>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <Link
                href="/connect"
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
              >
                + Connect a system
              </Link>
              <Link
                href="/setup"
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
              >
                Manual setup
              </Link>
            </div>
          </Card>

          {(guided.length > 0 || manual.length > 0) && (
            <Card title="Continue where you left off">
              <ul className="flex flex-col gap-2">
                {guided.map((entry) => {
                  if (entry.origin === "server") {
                    const system = entry.system;
                    return (
                      <li
                        key={system.system_id}
                        className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-surface-2 px-3 py-2"
                      >
                        <span className="text-sm font-medium text-text">
                          {system.name}
                        </span>
                        <span className="text-xs text-text-muted">
                          · guided · not armed yet ({system.status})
                        </span>
                        <span className="inline-flex gap-2">
                          <Link
                            href={`/connect?resume=${encodeURIComponent(system.system_id)}`}
                            className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
                          >
                            Continue
                          </Link>
                        </span>
                      </li>
                    );
                  }
                  const draft = entry.draft;
                  const titles =
                    draft.data.kind === "appliance"
                      ? APPLIANCE_STEP_TITLES
                      : SOFTWARE_STEP_TITLES;
                  return (
                    <li
                      key={draft.data.systemId}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-surface-2 px-3 py-2"
                    >
                      <span className="text-sm font-medium text-text">
                        {draft.data.name}
                      </span>
                      <span className="text-xs text-text-muted">
                        · guided · step {draft.index + 1} ·{" "}
                        {draftStepTitle(draft, titles)}
                      </span>
                      <span className="inline-flex gap-2">
                        <Link
                          href={`/connect?resume=${encodeURIComponent(draft.data.systemId)}`}
                          className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
                        >
                          Continue
                        </Link>
                      </span>
                    </li>
                  );
                })}
                {manual.map((draft) => (
                  <li
                    key={draft.data.systemId}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-surface-2 px-3 py-2"
                  >
                    <span className="text-sm font-medium text-text">
                      {draft.data.name}
                    </span>
                    <span className="text-xs text-text-muted">
                      · manual ·{" "}
                      {STEP_LABELS[draft.data.step] ?? draft.data.step}
                    </span>
                    <span className="inline-flex gap-2">
                      <Link
                        href={`/setup?system=${encodeURIComponent(draft.data.systemId)}`}
                        className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
                      >
                        Continue
                      </Link>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card title="Recent runs">
            {runsFailed ? (
              <p className="text-sm text-text-muted">
                Couldn&apos;t load runs — the API may be waking up.
              </p>
            ) : runs.length === 0 ? (
              <EmptyState
                title="No runs yet"
                hint="Runs appear here when the agent works an incident on your systems."
              />
            ) : (
              <ul className="flex flex-col gap-2">
                {runs.slice(0, 8).map((run) => (
                  <li
                    key={run.run_id}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-surface-2 px-3 py-2"
                  >
                    <span className="font-mono text-xs text-text-faint">
                      {run.run_id.slice(0, 8)}
                    </span>
                    <span className="text-xs text-text-muted">
                      {run.domain}
                      {typeof run.n_steps === "number" &&
                        ` · ${run.n_steps} steps`}
                    </span>
                    <DecisionPill run={run} />
                    <span className="inline-flex gap-2">
                      <Link
                        href={`/incidents/${encodeURIComponent(run.run_id)}`}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
                      >
                        Report
                      </Link>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Everything else">
            <div className="flex flex-wrap gap-2">
              <QuickLink href="/" label="Mission Control" />
              <QuickLink href="/connect" label="Connect" />
              <QuickLink href="/members" label="Members" />
              <QuickLink href="/devices" label="Devices" />
              <QuickLink href="/usage" label="Usage" />
              <QuickLink href="/guide#phone" label="Get the app" />
              <QuickLink href="/guide" label="How to" />
              <QuickLink href="/support" label="Support" />
            </div>
          </Card>

          <div className="flex justify-center">
            <Link
              href="/welcome"
              className="rounded-lg px-3 py-1.5 text-xs text-text-muted underline outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
            >
              About + live demo
            </Link>
          </div>
        </main>
      </AccountChrome>
    </RequireAuth>
  );
}
