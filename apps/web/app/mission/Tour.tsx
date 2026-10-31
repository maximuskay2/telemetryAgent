"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAgentStream } from "../hooks/useAgentStream";
import { apiUrl, responseDetail } from "../lib/api";
import { demoStatus } from "../lib/setupApi";
import {
  EMPTY_MARKS,
  STEP_LABELS,
  TRACK_DOMAIN,
  TRACK_NAME,
  maxReadyStep,
  stepTarget,
  trackOfDomain,
  type DemoTrack,
  type StepMarks,
} from "../lib/tourSteps";
import type { StreamEvent } from "../types/api";
import { Button } from "../ui";
import { useMission } from "./state";

export type TourSummary = {
  attempts: number;
  runId: string | null;
  track: DemoTrack;
};

const STEP_TIMEOUT_MS = 120000;

type TrackNotes = { diagnose: string; verify: string; done: string };
const EMPTY_NOTES: TrackNotes = { diagnose: "", verify: "", done: "" };

/** J7: first-incident coach-mark rail, driven by live demo state. */
export default function Tour({
  onComplete,
}: {
  onComplete: (summary: TourSummary) => void;
}) {
  const router = useRouter();
  const { systems, systemsLoaded, resetWorld, fridgeControl, vetoes, now } =
    useMission();
  const [enabled, setEnabled] = useState(false);
  const [track, setTrack] = useState<DemoTrack>("shop");
  const [marks, setMarks] = useState<Record<DemoTrack, StepMarks>>({
    shop: { ...EMPTY_MARKS },
    freezer: { ...EMPTY_MARKS },
  });
  const [notes, setNotes] = useState<Record<DemoTrack, TrackNotes>>({
    shop: { ...EMPTY_NOTES },
    freezer: { ...EMPTY_NOTES },
  });
  const [viewed, setViewed] = useState(1);
  const [dismissed, setDismissed] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [prUrl, setPrUrl] = useState<string | null>(null);
  const stats = useRef<
    Record<DemoTrack, { attempts: number; runId: string | null }>
  >({
    shop: { attempts: 0, runId: null },
    freezer: { attempts: 0, runId: null },
  });
  const trackRef = useRef<DemoTrack>("shop");
  const doneRef = useRef(onComplete);
  doneRef.current = onComplete;
  const headingRef = useRef<HTMLHeadingElement>(null);
  trackRef.current = track;

  const live = maxReadyStep(marks[track]);
  const labels = STEP_LABELS[track];
  const note = notes[track];
  const shop = systems.find((s) => s.kind === "software") ?? null;
  const fridge = systems.find((s) => s.kind === "appliance") ?? null;
  const shopArmed = shop !== null && shop.status === "armed";
  const fridgeArmed = fridge !== null && fridge.status === "armed";

  // The live view follows the demo; tapping the rail only looks back.
  useEffect(() => {
    setViewed(live);
  }, [live]);

  useEffect(() => {
    setEnabled(
      new URLSearchParams(window.location.search).get("tour") === "1",
    );
  }, []);

  // Start on whichever demo is armed when only one is.
  useEffect(() => {
    if (!systemsLoaded) return;
    const shopReady = systems.some(
      (s) => s.kind === "software" && s.status === "armed",
    );
    const fridgeReady = systems.some(
      (s) => s.kind === "appliance" && s.status === "armed",
    );
    if (!shopReady && fridgeReady) setTrack("freezer");
  }, [systemsLoaded, systems]);

  // ?tour=1 with nothing armed bounces to the guided setup.
  useEffect(() => {
    if (!enabled || !systemsLoaded) return;
    const armed = systems.some((s) => s.status === "armed");
    if (!armed) router.replace("/start/setup");
  }, [enabled, systemsLoaded, systems, router]);

  // Focus + scroll the viewed step's target into view.
  useEffect(() => {
    if (!enabled || dismissed) return;
    headingRef.current?.focus({ preventScroll: true });
    document
      .getElementById(stepTarget(viewed, track))
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [enabled, dismissed, viewed, track]);

  // Per-step 120 s timeout.
  useEffect(() => {
    if (!enabled || dismissed) return;
    setTimedOut(false);
    const timer = window.setTimeout(() => setTimedOut(true), STEP_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [enabled, dismissed, live, track]);

  // Escape dismisses; Mission Control stays fully usable.
  useEffect(() => {
    if (!enabled || dismissed) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDismissed(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, dismissed]);

  // Step 5: poll for the PR link until it exists.
  useEffect(() => {
    if (!enabled || dismissed || viewed !== 5 || prUrl) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const snapshot = await demoStatus();
        if (!cancelled && snapshot.pr_url) setPrUrl(snapshot.pr_url);
      } catch {
        // keep polling
      }
    };
    poll();
    const timer = window.setInterval(poll, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled, dismissed, viewed, prUrl]);

  const finish = useCallback(() => {
    const t = trackRef.current;
    doneRef.current({
      attempts: stats.current[t].attempts,
      runId: stats.current[t].runId,
      track: t,
    });
  }, []);

  const mark = useCallback(
    (t: DemoTrack, patch: Partial<StepMarks>, notePatch?: Partial<TrackNotes>) => {
      setMarks((prev) => {
        const next = { ...prev[t], ...patch };
        if (
          next.triggered === prev[t].triggered &&
          next.diagnosed === prev[t].diagnosed &&
          next.verified === prev[t].verified &&
          next.resolved === prev[t].resolved
        ) {
          return prev;
        }
        return { ...prev, [t]: next };
      });
      if (notePatch) {
        setNotes((prev) => ({ ...prev, [t]: { ...prev[t], ...notePatch } }));
      }
    },
    [],
  );

  const onEvent = useCallback(
    (event: StreamEvent) => {
      if (event.type === "watcher_trigger") {
        const t = trackOfDomain(event.payload.domain);
        if (!t) return;
        mark(t, { triggered: true });
        return;
      }
      if (event.type === "step") {
        const e = event.event;
        const t = trackOfDomain(e.domain);
        if (!t) return;
        if (t === trackRef.current) {
          if (e.run_id) stats.current[t].runId = e.run_id;
          stats.current[t].attempts = Math.max(
            stats.current[t].attempts,
            e.attempt + 1,
          );
        }
        if (e.step === "diagnose") {
          mark(t, { diagnosed: true }, { diagnose: e.message || "Diagnosing…" });
          return;
        }
        if (e.step === "verify") {
          if (e.status === "ok" || e.status === "PASS") {
            mark(
              t,
              { verified: true },
              { verify: `Verify attempt ${e.attempt + 1} · passed` },
            );
            if (t === trackRef.current) setRetrying(false);
          } else if (
            e.status === "FAIL" ||
            e.status === "fail" ||
            e.status === "error"
          ) {
            mark(
              t,
              {},
              {
                verify: `Verify attempt ${e.attempt + 1} · failed — retrying`,
              },
            );
            if (t === trackRef.current) setRetrying(true);
          }
        }
        return;
      }
      if (event.type === "action_resolved" || event.type === "fix_applied") {
        const t = trackOfDomain(event.payload.domain);
        if (!t) return;
        if (event.type === "action_resolved") {
          const state = event.payload.state;
          if (typeof state !== "string" || state === "pending") return;
          mark(t, { resolved: true }, { done: `Decision: ${state}` });
        } else {
          mark(t, { resolved: true }, { done: "Fix applied" });
        }
        return;
      }
    },
    [mark],
  );

  useAgentStream({ onEvent, onError: () => {} });

  if (!enabled || dismissed) return null;

  const domain = TRACK_DOMAIN[track];
  const openVeto =
    Object.values(vetoes)
      .filter((v) => v.state === "pending" && v.domain === domain)
      .sort((a, b) => a.deadlineMs - b.deadlineMs)[0] ?? null;
  const lastVeto =
    [...Object.values(vetoes)]
      .reverse()
      .find((v) => v.state !== "pending" && v.domain === domain) ?? null;
  const vetoDeadlineLeft = openVeto
    ? openVeto.deadlineMs > 0
      ? Math.max(0, Math.ceil((openVeto.deadlineMs - now) / 1000))
      : openVeto.secondsLeft
    : 0;
  const vetoLeft =
    openVeto &&
    openVeto.secondsLeft > 0 &&
    Math.abs(openVeto.secondsLeft - vetoDeadlineLeft) > 2
      ? openVeto.secondsLeft
      : vetoDeadlineLeft;

  async function breakShop() {
    setTrack("shop");
    setBusy("shop");
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/shop/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shoppers: 8, rate: 30, duration: 60 }),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not break the shop.");
    } finally {
      setBusy(null);
    }
  }

  function openFreezer() {
    setTrack("freezer");
    setBusy("freezer");
    setError("");
    try {
      fridgeControl("fault", { fault: "door_open" });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not open the freezer door.",
      );
    } finally {
      setBusy(null);
    }
  }

  function switchTrack(next: DemoTrack) {
    setTrack(next);
    setRetrying(false);
    setTimedOut(false);
    setPrUrl(null);
    setError("");
  }

  function restartDemo() {
    resetWorld();
    setMarks({
      shop: { ...EMPTY_MARKS },
      freezer: { ...EMPTY_MARKS },
    });
    setNotes({
      shop: { ...EMPTY_NOTES },
      freezer: { ...EMPTY_NOTES },
    });
    stats.current = {
      shop: { attempts: 0, runId: null },
      freezer: { attempts: 0, runId: null },
    };
    setTimedOut(false);
    setRetrying(false);
    setPrUrl(null);
    setViewed(1);
  }

  const unarmed = [
    shopArmed ? null : "Shop",
    fridgeArmed ? null : "Freezer",
  ].filter((name): name is string => name !== null);

  return (
    <aside
      aria-label="Guided demo tour"
      className="fixed top-20 right-3 z-40 w-72 rounded-lg border border-brand/40 bg-surface p-4 shadow-xl"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
          Guided demo · {TRACK_NAME[track]} · {viewed} of 5
        </p>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Close tour"
          className="rounded px-1.5 py-0.5 text-sm text-text-muted outline-none hover:bg-surface-2 hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
        >
          ✕
        </button>
      </div>
      <ol className="mt-2 flex list-none gap-1.5 p-0" aria-label="Demo steps">
        {labels.map((label, i) => {
          const n = i + 1;
          const ready = n <= live;
          const seen = n <= viewed;
          return (
            <li key={label} className="flex-1">
              <button
                type="button"
                disabled={!ready}
                onClick={() => setViewed(n)}
                aria-label={`${n}. ${label}${n === live ? " (live)" : ""}${
                  ready ? "" : " (locked)"
                }`}
                className="w-full rounded py-1 outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed"
              >
                <span
                  className={`block h-1.5 rounded-full ${
                    seen ? "bg-brand" : ready ? "bg-brand/40" : "bg-border"
                  }`}
                />
              </button>
            </li>
          );
        })}
      </ol>
      {viewed < live && (
        <button
          type="button"
          onClick={() => setViewed(live)}
          className="mt-1 rounded text-xs text-brand-cyan underline outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          Back to live (step {live}) →
        </button>
      )}

      <h2
        ref={headingRef}
        tabIndex={-1}
        className="mt-3 text-sm font-semibold outline-none"
      >
        {labels[viewed - 1]}
      </h2>

      {viewed === 1 && (
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs leading-relaxed text-text-muted">
            {track === "shop" ? (
              <>
                This is AutoParts Lagos taking orders — the little storefront
                below is live. Let&apos;s give it a rush hour.
              </>
            ) : (
              <>
                This is the cold-chain freezer below — live temperature, door,
                and compressor. Let&apos;s open the door and watch it get
                caught.
              </>
            )}
          </p>
          {track === "shop" && (
            <iframe
              title="Customer storefront preview"
              src="/shop"
              className="h-36 w-full rounded-md border border-border bg-bg"
              loading="lazy"
            />
          )}
          <Button
            tone={track === "shop" ? "primary" : "secondary"}
            disabled={busy !== null || !shopArmed}
            onClick={breakShop}
          >
            {busy === "shop" ? "Starting rush hour…" : "Break the shop"}
          </Button>
          <Button
            tone={track === "freezer" ? "primary" : "secondary"}
            disabled={busy !== null || !fridgeArmed}
            onClick={openFreezer}
          >
            {busy === "freezer" ? "Opening…" : "Open the freezer door"}
          </Button>
          {unarmed.length > 0 && (
            <p className="text-xs text-text-faint">
              {unarmed.join(" and ")} not armed — finish the guided setup
              first.
            </p>
          )}
        </div>
      )}
      {viewed === 2 && (
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs leading-relaxed text-text-muted">
            It noticed the errors itself — no one pressed anything. Now
            it&apos;s diagnosing with Muse Spark. Follow the agent trace. ←
          </p>
          <p className="text-xs text-brand-cyan">
            {note.diagnose || "Waiting for diagnosis…"}
          </p>
        </div>
      )}
      {viewed === 3 && (
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs leading-relaxed text-text-muted">
            {retrying
              ? "First fix failed its test — it's learning from the failure and trying again."
              : "It wrote a fix and a test, and proved the test fails before the fix and passes after, in a sandbox."}
          </p>
          <p className="text-xs text-brand-cyan">
            {note.verify || "Waiting for verification…"}
          </p>
        </div>
      )}
      {viewed === 4 && (
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs leading-relaxed text-text-muted">
            It will deploy in 20 s unless someone cancels. You&apos;re in
            control — watch the cancel window. ←
          </p>
          <p className="text-xs text-brand-cyan">
            {openVeto
              ? `Cancel window: ${vetoLeft}s left — decide below ←`
              : (note.done ||
                (lastVeto ? `Decision: ${lastVeto.state}` : "")) ||
                "Waiting for the cancel window…"}
          </p>
        </div>
      )}
      {viewed === 5 && (
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs leading-relaxed text-text-muted">
            Fixed, verified, and a pull request is on GitHub.
          </p>
          {prUrl ? (
            <a
              href={prUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded text-xs text-brand-cyan underline outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              View pull request ↗
            </a>
          ) : (
            <p className="text-xs text-text-faint">
              Waiting for the pull request link…
            </p>
          )}
          <Button
            tone="secondary"
            onClick={() =>
              switchTrack(track === "shop" ? "freezer" : "shop")
            }
          >
            {track === "shop" ? "Now try the freezer" : "Now try the shop"}
          </Button>
          <Button tone="ghost" onClick={finish}>
            Finish tour
          </Button>
        </div>
      )}

      {error && (
        <p className="mt-2 text-xs text-crit" role="alert">
          {error}
        </p>
      )}
      {timedOut && (
        <p className="mt-2 rounded-md border border-warn/40 bg-warn/10 px-2 py-1.5 text-xs text-warn">
          Taking longer than usual — keep watching or{" "}
          <button
            type="button"
            onClick={restartDemo}
            className="rounded underline outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            Restart demo
          </button>
        </p>
      )}
    </aside>
  );
}
