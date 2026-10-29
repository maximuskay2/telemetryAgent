"use client";

import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useAgentStream } from "../hooks/useAgentStream";
import { apiUrl, responseDetail } from "../lib/api";
import { demoStatus } from "../lib/setupApi";
import type { StreamEvent } from "../types/api";
import { Button } from "../ui";
import { useMission } from "./state";

export type TourSummary = { attempts: number; runId: string | null };

const STEP_TARGET: Record<number, string> = {
  1: "tour-shop",
  2: "tour-trace",
  3: "tour-trace",
  4: "tour-veto",
  5: "tour-shop",
};

const STEP_LABEL = [
  "Break the shop",
  "Watch it diagnose",
  "Watch it prove the fix",
  "The cancel window",
  "Fixed — try the freezer",
] as const;

const STEP_TIMEOUT_MS = 120000;

/** J7: first-incident coach-mark rail, driven by live WebSocket events. */
export default function Tour({
  onComplete,
}: {
  onComplete: (summary: TourSummary) => void;
}) {
  const router = useRouter();
  const { systems, systemsLoaded, resetWorld, fridgeControl } = useMission();
  const [enabled, setEnabled] = useState(false);
  const [step, setStep] = useState(1);
  const [dismissed, setDismissed] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [prUrl, setPrUrl] = useState<string | null>(null);
  const [freezerSent, setFreezerSent] = useState(false);
  const attempts = useRef(0);
  const runId = useRef<string | null>(null);
  const stepRef = useRef(1);
  const doneRef = useRef(onComplete);
  doneRef.current = onComplete;
  const headingRef = useRef<HTMLHeadingElement>(null);
  stepRef.current = step;

  useEffect(() => {
    setEnabled(
      new URLSearchParams(window.location.search).get("tour") === "1",
    );
  }, []);

  // ?tour=1 with nothing armed bounces to the guided setup.
  useEffect(() => {
    if (!enabled || !systemsLoaded) return;
    const armed = systems.some((s) => s.status === "armed");
    if (!armed) router.replace("/start/setup");
  }, [enabled, systemsLoaded, systems, router]);

  // Focus + scroll the current step's target into view.
  useEffect(() => {
    if (!enabled || dismissed) return;
    headingRef.current?.focus({ preventScroll: true });
    document
      .getElementById(STEP_TARGET[step])
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [enabled, dismissed, step]);

  // Per-step 120 s timeout.
  useEffect(() => {
    if (!enabled || dismissed) return;
    setTimedOut(false);
    const timer = window.setTimeout(() => setTimedOut(true), STEP_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [enabled, dismissed, step]);

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
    if (!enabled || dismissed || step !== 5 || prUrl) return;
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
  }, [enabled, dismissed, step, prUrl]);

  const finish = useCallback(() => {
    doneRef.current({ attempts: attempts.current, runId: runId.current });
  }, []);

  const onEvent = useCallback(
    (event: StreamEvent) => {
      const at = stepRef.current;
      if (event.type === "watcher_trigger") {
        if (at === 1) setStep(2);
        return;
      }
      if (event.type === "step") {
        const e = event.event;
        if (e.run_id) runId.current = e.run_id;
        attempts.current = Math.max(attempts.current, e.attempt + 1);
        if (at === 2 && e.step === "diagnose") {
          setStep(3);
          return;
        }
        if (at === 3 && e.step === "verify") {
          if (e.status === "ok" || e.status === "PASS") setStep(4);
          else if (
            e.status === "FAIL" ||
            e.status === "fail" ||
            e.status === "error"
          ) {
            setRetrying(true);
          }
        }
        return;
      }
      if (event.type === "action_resolved" || event.type === "fix_applied") {
        if (at === 4) {
          if (event.type === "action_resolved") {
            const state = event.payload.state;
            if (typeof state !== "string" || state === "pending") return;
          }
          setStep(5);
          return;
        }
        if (at === 5 && event.type === "action_resolved") {
          if (event.payload.domain === "appliance") finish();
        }
      }
    },
    [finish],
  );

  useAgentStream({ onEvent, onError: () => {} });

  if (!enabled || dismissed) return null;

  async function breakShop() {
    setBusy(true);
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
      setBusy(false);
    }
  }

  function restartDemo() {
    resetWorld();
    setTimedOut(false);
    setRetrying(false);
    setStep(1);
  }

  return (
    <aside
      aria-label="Guided demo tour"
      className="fixed top-20 right-3 z-40 w-72 rounded-lg border border-brand/40 bg-surface p-4 shadow-xl"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
          Guided demo · {step} of 5
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
      <ol className="mt-2 flex list-none gap-1.5 p-0" aria-hidden>
        {STEP_LABEL.map((label, i) => (
          <li
            key={label}
            className={`h-1.5 flex-1 rounded-full ${i + 1 <= step ? "bg-brand" : "bg-border"}`}
          />
        ))}
      </ol>

      <h2
        ref={headingRef}
        tabIndex={-1}
        className="mt-3 text-sm font-semibold outline-none"
      >
        {STEP_LABEL[step - 1]}
      </h2>

      {step === 1 && (
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs leading-relaxed text-text-muted">
            This is AutoParts Lagos taking orders — the little storefront
            below is live. Let&apos;s give it a rush hour.
          </p>
          <iframe
            title="Customer storefront preview"
            src="/shop"
            className="h-36 w-full rounded-md border border-border bg-bg"
            loading="lazy"
          />
          <Button tone="primary" disabled={busy} onClick={breakShop}>
            {busy ? "Starting rush hour…" : "Break the shop"}
          </Button>
        </div>
      )}
      {step === 2 && (
        <p className="mt-2 text-xs leading-relaxed text-text-muted">
          It noticed the errors itself — no one pressed anything. Now
          it&apos;s diagnosing with Muse Spark. Follow the agent trace. ←
        </p>
      )}
      {step === 3 && (
        <p className="mt-2 text-xs leading-relaxed text-text-muted">
          {retrying
            ? "First fix failed its test — it's learning from the failure and trying again."
            : "It wrote a fix and a test, and proved the test fails before the fix and passes after, in a sandbox."}
        </p>
      )}
      {step === 4 && (
        <p className="mt-2 text-xs leading-relaxed text-text-muted">
          It will deploy in 20 s unless someone cancels. You&apos;re in
          control — watch the cancel window. ←
        </p>
      )}
      {step === 5 && (
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
          {!freezerSent ? (
            <Button
              tone="secondary"
              onClick={() => {
                fridgeControl("fault", { fault: "door_open" });
                setFreezerSent(true);
              }}
            >
              Now try the freezer
            </Button>
          ) : (
            <p className="text-xs text-text-muted">
              Freezer door opened — watch it get caught…
            </p>
          )}
          <Button tone="ghost" onClick={finish}>
            Skip the freezer
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
