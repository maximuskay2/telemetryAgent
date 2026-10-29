"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAgentStream } from "../../hooks/useAgentStream";
import {
  armSystem,
  confirmProfile,
  demoBootstrap,
  demoDocuments,
  demoLearn,
  demoStatus,
  finishBaseline,
  getProfile,
  putProfile,
  type DemoStatus,
  type DocumentsResult,
  type SetupConflict,
  type SetupProfile,
} from "../../lib/setupApi";
import type { StreamEvent } from "../../types/api";
import { Button, Card } from "../../ui";
import { ReviewTables } from "../../setup/ReviewTable";

type Side = "shop" | "freezer";

const SIDE_BLURB: Record<Side, string> = {
  shop: "Online parts shop · web, orders and inventory services",
  freezer: "Vaccine and food storage · holding 2–8 °C",
};

const SYSTEM_DOCS: Record<Side, string[]> = {
  shop: ["autoparts_ops_guide.md"],
  freezer: ["coldchain_spec_sheet.pdf", "coldchain_rating_plate.jpg"],
};

const STAGE_TITLES = [
  "Meet the business",
  "Read the manuals",
  "Watch normal",
  "Permissions & start watching",
] as const;

function shortDoc(filename: string): string {
  if (filename.includes("spec_sheet")) return "spec sheet";
  if (filename.includes("rating_plate")) return "rating plate";
  if (filename.includes("ops_guide")) return "ops guide";
  return filename;
}

function prettyMetric(metric: unknown): string {
  if (typeof metric !== "string" || !metric) return "Reading";
  if (metric === "temp_c" || metric === "temperature") return "Holding";
  return metric
    .replace(/_c$|_a$|_g$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtNum(value: unknown): string {
  return typeof value === "number"
    ? String(Math.round(value * 100) / 100)
    : String(value ?? "?");
}

type Fact = { text: string; cite: string };

function profileFacts(profile: SetupProfile): Fact[] {
  const facts: Fact[] = [];
  for (const row of profile.normal_ranges ?? []) {
    const prov = (row.provenance ?? {}) as Record<string, string>;
    facts.push({
      text: `${prettyMetric(row.metric)} ${fmtNum(row.min)}–${fmtNum(row.max)}${row.unit ? ` ${row.unit}` : ""}`,
      cite: `${shortDoc(prov.source_doc ?? "manual")}${prov.page_or_region ? ` ${prov.page_or_region}` : ""}`,
    });
    if (facts.length >= 2) break;
  }
  const limit = (profile.hard_limits ?? [])[0];
  if (limit) {
    const prov = (limit.provenance ?? {}) as Record<string, string>;
    facts.push({
      text: `${prettyMetric(limit.metric)} never ${limit.op === ">" ? "above" : "below"} ${fmtNum(limit.threshold)}`,
      cite: `${shortDoc(prov.source_doc ?? "manual")}`,
    });
  }
  return facts.slice(0, 3);
}

/** Pre-resolved conflict pick: narrowest band wins, else the first reading. */
function safestPick(conflict: SetupConflict): number {
  if (conflict.field === "normal_ranges") {
    let best = 0;
    let span = Number.POSITIVE_INFINITY;
    conflict.values.forEach((candidate, i) => {
      const value = (candidate.value ?? {}) as Record<string, unknown>;
      if (typeof value.min === "number" && typeof value.max === "number") {
        const width = value.max - value.min;
        if (width < span) {
          span = width;
          best = i;
        }
      }
    });
    return best;
  }
  return 0;
}

function Ring({ pct, label }: { pct: number; label: string }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const done = Math.min(100, Math.max(0, pct));
  return (
    <div className="flex items-center gap-2">
      <svg
        viewBox="0 0 64 64"
        className="size-14"
        role="img"
        aria-label={`${label}: ${Math.round(done)} percent`}
      >
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          strokeWidth="7"
          className="stroke-border"
        />
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - done / 100)}
          className="stroke-brand"
          transform="rotate(-90 32 32)"
        />
        <text
          x="32"
          y="36"
          textAnchor="middle"
          className="fill-text text-[13px] font-semibold"
        >
          {Math.round(done)}
        </text>
      </svg>
      <span className="text-xs text-text-muted">{label}</span>
    </div>
  );
}

export default function GuidedSetupPage() {
  const router = useRouter();
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [profiles, setProfiles] = useState<Record<Side, SetupProfile | null>>({
    shop: null,
    freezer: null,
  });
  const [docs, setDocs] = useState<Record<Side, DocumentsResult | null>>({
    shop: null,
    freezer: null,
  });
  const [chips, setChips] = useState<Record<string, string>>({});
  const [showAll, setShowAll] = useState<Record<Side, boolean>>({
    shop: false,
    freezer: false,
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [skipped, setSkipped] = useState(false);
  const [replay, setReplay] = useState(false);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    try {
      setSkipped(window.localStorage.getItem("ta_demo_skip_learn") === "1");
    } catch {
      // ignore
    }
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    const snapshot = await demoStatus();
    if (!mounted.current) return snapshot;
    setStatus(snapshot);
    return snapshot;
  }, []);

  // Mount: snapshot the world, pull profiles for stage resume (J6 refresh).
  useEffect(() => {
    (async () => {
      try {
        const snapshot = await refresh();
        const next: Record<Side, SetupProfile | null> = {
          shop: null,
          freezer: null,
        };
        for (const side of ["shop", "freezer"] as Side[]) {
          const row = snapshot[side];
          if (row) {
            const full = await getProfile(row.system_id);
            next[side] = full.profile;
          }
        }
        if (mounted.current) setProfiles(next);
      } catch (err) {
        if (mounted.current) {
          setError(
            err instanceof Error ? err.message : "The demo API is down.",
          );
        }
      } finally {
        if (mounted.current) setLoading(false);
      }
    })();
  }, [refresh]);

  // Poll backstop while anything is unfinished.
  useEffect(() => {
    const timer = window.setInterval(() => {
      refresh().catch(() => {});
    }, 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const onEvent = useCallback((event: StreamEvent) => {
    if (event.type === "setup_progress") {
      const { stage, system_id: sid, doc } = event.payload;
      if (!sid) return;
      if (stage === "extracted") {
        refresh().catch(() => {});
        return;
      }
      if (doc) {
        setChips((current) =>
          current[`${sid}:${doc}`] === stage
            ? current
            : { ...current, [`${sid}:${doc}`]: stage },
        );
      }
      return;
    }
    if (event.type === "baseline_progress") {
      refresh().catch(() => {});
    }
  }, [refresh]);

  const { connection } = useAgentStream({
    onEvent,
    onError: () => {},
  });
  void connection;

  function sideStage(side: Side): number {
    const row = status?.[side];
    if (!row) return 1;
    if (row.status === "armed" && !replay) return 5;
    if (row.baseline_status === "ready" || skipped) return 4;
    const ranges = profiles[side]?.normal_ranges ?? [];
    if (ranges.length > 0 || docs[side] !== null) return 3;
    return 2;
  }

  const current = Math.min(sideStage("shop"), sideStage("freezer"));
  const done = current === 5 && !replay;

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await work();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : `${label} failed.`);
    } finally {
      if (mounted.current) setBusy(null);
    }
  }

  async function meetBusiness() {
    await run("meet", async () => {
      const boot = await demoBootstrap();
      const next: Record<Side, SetupProfile | null> = {
        shop: boot.shop,
        freezer: boot.freezer,
      };
      for (const side of ["shop", "freezer"] as Side[]) {
        const full = await getProfile(next[side]?.system_id ?? "");
        next[side] = full.profile;
      }
      setProfiles(next);
    });
  }

  async function readManuals() {
    await run("manuals", async () => {
      const sides = (["shop", "freezer"] as Side[]).filter(
        (side) => sideStage(side) === 2,
      );
      const results = await Promise.all(
        sides.map(async (side) => {
          const id = status?.[side]?.system_id ?? "";
          const result = await demoDocuments(id);
          return [side, result] as const;
        }),
      );
      setDocs((prev) => {
        const next = { ...prev };
        for (const [side, result] of results) next[side] = result;
        return next;
      });
      setProfiles((prev) => {
        const next = { ...prev };
        for (const [side, result] of results) next[side] = result.profile;
        return next;
      });
    });
  }

  async function watchNormal() {
    await run("watch", async () => {
      const sides = (["shop", "freezer"] as Side[]).filter(
        (side) => sideStage(side) === 3,
      );
      await Promise.all(
        sides.map((side) => demoLearn(status?.[side]?.system_id ?? "")),
      );
    });
  }

  function skipLearn() {
    try {
      window.localStorage.setItem("ta_demo_skip_learn", "1");
    } catch {
      // ignore
    }
    setSkipped(true);
  }

  async function startWatching() {
    await run("arm", async () => {
      const sides = (["shop", "freezer"] as Side[]).filter(
        (side) => status?.[side] && status[side]?.status !== "armed",
      );
      await Promise.all(
        sides.map(async (side) => {
          const id = status?.[side]?.system_id ?? "";
          const row = status?.[side];
          if (row?.status === "learning") {
            await finishBaseline(id);
          }
          const full = await getProfile(id);
          const withPolicy: SetupProfile = {
            ...full.profile,
            policy: {
              ...(full.profile.policy ?? {}),
              auto_fix_allowed: true,
              countdown_s: 20,
            },
          };
          const saved = await putProfile(id, withPolicy);
          const picks = (docs[side]?.conflicts ?? full.conflicts).map(
            (conflict) => ({
              field: conflict.field,
              key: conflict.key,
              pick: safestPick(conflict),
            }),
          );
          await confirmProfile(id, "Demo visitor", picks);
          await armSystem(id);
          void saved;
        }),
      );
      router.push("/?tour=1");
    });
  }

  function stageState(n: number): "done" | "active" | "locked" {
    if (done || current > n) return "done";
    if (current === n) return "active";
    return "locked";
  }

  function SideCard({ side }: { side: Side }) {
    const row = status?.[side];
    const profile = profiles[side];
    const result = docs[side];
    const learning = row?.status === "learning";
    const learnedCount =
      (profile?.normal_ranges?.length ?? 0) +
      (profile?.expected_behaviours?.length ?? 0) +
      (profile?.modes?.length ?? 0) +
      (profile?.failure_definitions?.length ?? 0) +
      (profile?.hard_limits?.length ?? 0);
    if (!row) {
      return (
        <div className="rounded-lg border border-dashed border-border p-3">
          <p className="text-sm font-medium text-text-muted">
            {side === "shop" ? "AutoParts Lagos" : "Cold-chain Freezer"}
          </p>
          <p className="mt-1 text-xs text-text-faint">Not created yet.</p>
        </div>
      );
    }
    return (
      <div className="rounded-lg border border-border bg-surface-2/50 p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium">{profile?.name ?? row.system_id}</p>
          <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-text-muted">
            {row.status === "armed" && !replay
              ? "Already running"
              : row.status === "learning"
                ? "Watching normal…"
                : row.status}
          </span>
        </div>
        <p className="mt-1 text-xs text-text-faint">{SIDE_BLURB[side]}</p>

        {current >= 2 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {SYSTEM_DOCS[side].map((doc) => {
              const key = `${row.system_id}:${doc}`;
              const seen = chips[key];
              const finished =
                result !== null || (profile?.normal_ranges?.length ?? 0) > 0;
              return (
                <span
                  key={doc}
                  className={`rounded-full border px-2 py-0.5 font-mono text-[11px] ${
                    finished
                      ? "border-ok/50 text-ok"
                      : seen
                        ? "border-brand/50 text-brand-cyan"
                        : "border-border text-text-faint"
                  }`}
                >
                  {finished ? "✓ " : seen ? "… " : ""}
                  {shortDoc(doc)}
                </span>
              );
            })}
          </div>
        )}

        {result?.fallback === true && (
          <p className="mt-2 text-xs text-warn">
            Using the saved reading of these manuals.
          </p>
        )}

        {profile && (profile.normal_ranges?.length ?? 0) > 0 && (
          <ul className="mt-2 flex list-none flex-col gap-1 p-0">
            {profileFacts(profile).map((fact) => (
              <li
                key={fact.text}
                className="text-xs text-text-muted"
              >
                <span className="text-text">“{fact.text}”</span>
                <span className="text-text-faint"> — {fact.cite}</span>
              </li>
            ))}
          </ul>
        )}

        {(result?.conflicts?.length ?? 0) > 0 && (
          <p className="mt-2 text-xs text-text-muted">
            {result?.conflicts.length} reading
            {(result?.conflicts.length ?? 0) === 1 ? "" : "s"} differed — using
            the safest ✓{" "}
            <Link
              href={`/setup?system=${row.system_id}`}
              className="rounded text-brand-cyan underline outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              change
            </Link>
          </p>
        )}

        {learnedCount > 0 && (
          <div className="mt-2">
            <Button
              tone="ghost"
              onClick={() =>
                setShowAll((prev) => ({ ...prev, [side]: !prev[side] }))
              }
            >
              {showAll[side] ? "Hide everything" : "See everything it learned"}
            </Button>
            {showAll[side] && profile && (
              <div className="mt-2">
                <ReviewTables profile={profile} />
              </div>
            )}
          </div>
        )}

        {(learning || row.baseline_status === "ready") && (
          <div className="mt-2 flex items-center gap-3">
            <Ring
              pct={learning ? (row.baseline_pct ?? 0) : 100}
              label={learning ? "learning" : "learned"}
            />
            <p className="text-xs text-text-muted">
              {row.baseline_patterns} pattern
              {row.baseline_patterns === 1 ? "" : "s"} so far
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg font-sans text-text">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex w-full max-w-3xl items-center gap-2 px-4 py-3">
          <Link
            href="/start"
            aria-label="Back to onboarding"
            className="rounded text-sm text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            ←
          </Link>
          <Link
            href="/welcome"
            title="Home"
            aria-label="TelemetryAgent home"
            className="rounded text-sm text-brand-cyan outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            ◆
          </Link>
          <span className="text-sm font-semibold">Guided setup</span>
          <span className="ms-auto text-xs text-text-muted">
            {done ? "Done ✓" : `Stage ${Math.min(current, 4)} of 4`}
          </span>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-3 px-4 py-6">
        {loading && (
          <Card>
            <p className="text-sm text-text-muted" role="status">
              Checking the demo world…
            </p>
          </Card>
        )}

        {!loading && error && (
          <Card className="border-crit/50">
            <p className="text-sm text-crit" role="alert">
              {error}
            </p>
          </Card>
        )}

        {!loading && done && (
          <Card title="Already running ✓">
            <p className="text-sm text-text-muted">
              Both systems were set up by an earlier visitor and are watching
              now. Jump straight to the incident — or replay the setup to
              watch each step again.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link
                href="/?tour=1"
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-[#0b1710] outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
              >
                Jump to the incident →
              </Link>
              <Button tone="ghost" onClick={() => setReplay(true)}>
                Replay setup
              </Button>
            </div>
          </Card>
        )}

        {!loading &&
          !done &&
          STAGE_TITLES.map((title, i) => {
            const n = (i + 1) as 1 | 2 | 3 | 4;
            const state = stageState(n);
            if (state === "done") {
              return (
                <p
                  key={title}
                  className="flex items-center gap-2 text-sm text-text-muted"
                >
                  <span aria-hidden className="text-ok">
                    ✓
                  </span>
                  {title}
                </p>
              );
            }
            if (state === "locked") {
              return (
                <p
                  key={title}
                  className="flex items-center gap-2 text-sm text-text-faint"
                >
                  <span
                    aria-hidden
                    className="flex size-5 items-center justify-center rounded-full bg-surface-2 font-mono text-[11px]"
                  >
                    {n}
                  </span>
                  {title}
                </p>
              );
            }
            return (
              <Card
                key={title}
                title={
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden
                      className="flex size-5 items-center justify-center rounded-full bg-brand font-mono text-[11px] text-[#0b1710]"
                    >
                      {n}
                    </span>
                    {title}
                  </span>
                }
              >
                {n === 1 && (
                  <div className="flex flex-col gap-3">
                    <p className="text-sm text-text-muted">
                      Two demo systems: the parts shop and the freezer. One
                      click creates them side by side.
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <SideCard side="shop" />
                      <SideCard side="freezer" />
                    </div>
                    <div>
                      <Button
                        tone="primary"
                        disabled={busy !== null}
                        onClick={meetBusiness}
                      >
                        {busy === "meet"
                          ? "Setting up…"
                          : "Set up my demo business"}
                      </Button>
                    </div>
                  </div>
                )}
                {n === 2 && (
                  <div className="flex flex-col gap-3">
                    <p className="text-sm text-text-muted">
                      The agent reads the real manuals — the ops guide, the
                      spec sheet, the rating-plate photo — and pulls out what
                      normal means.
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <SideCard side="shop" />
                      <SideCard side="freezer" />
                    </div>
                    <div>
                      <Button
                        tone="primary"
                        disabled={busy !== null}
                        onClick={readManuals}
                      >
                        {busy === "manuals"
                          ? "Reading… (up to ~45 s each)"
                          : "Read the manuals"}
                      </Button>
                    </div>
                  </div>
                )}
                {n === 3 && (
                  <div className="flex flex-col gap-3">
                    <p className="text-sm text-text-muted">
                      Two quiet minutes. It&apos;s learning that a defrost
                      cycle and a cold cache look scary but are normal.
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <SideCard side="shop" />
                      <SideCard side="freezer" />
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <Button
                        tone="primary"
                        disabled={busy !== null}
                        onClick={watchNormal}
                      >
                        {busy === "watch"
                          ? "Starting…"
                          : status?.shop?.status === "learning" ||
                              status?.freezer?.status === "learning"
                            ? "Watching…"
                            : "Watch normal for 2 min"}
                      </Button>
                      <button
                        type="button"
                        onClick={skipLearn}
                        className="rounded text-xs text-text-muted underline outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
                      >
                        Skip (not recommended)
                      </button>
                    </div>
                  </div>
                )}
                {n === 4 && (
                  <div className="flex flex-col gap-3">
                    <p className="text-sm text-text-muted">
                      It may fix the shop on its own after a 20-second cancel
                      window. It will alert, not act, on the freezer&apos;s
                      hard limits.
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <SideCard side="shop" />
                      <SideCard side="freezer" />
                    </div>
                    <div>
                      {replay &&
                      status?.shop?.status === "armed" &&
                      status?.freezer?.status === "armed" ? (
                        <Link
                          href="/?tour=1"
                          className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-[#0b1710] outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
                        >
                          Back to the incident →
                        </Link>
                      ) : (
                        <Button
                          tone="primary"
                          disabled={busy !== null}
                          onClick={startWatching}
                        >
                          {busy === "arm" ? "Starting…" : "Start watching"}
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
      </main>
    </div>
  );
}
