"use client";

import { useEffect, useRef, useState } from "react";
import { apiUrl, responseDetail } from "../lib/api";
import type { VetoAction } from "../types/api";
import { useMission } from "./state";

const RADIUS = 34;
const CIRCLE = 2 * Math.PI * RADIUS;

function outcomeOf(veto: VetoAction): string {
  switch (veto.state) {
    case "auto_applied":
      return "Auto-applied ✓";
    case "approved":
      return "Did it now ✓";
    case "disapproved":
      return "Cancelled — left for a human";
    default:
      return `Cancel window ${veto.state}`;
  }
}

function beep() {
  try {
    const Ctx = window.AudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 660;
    gain.gain.value = 0.08;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.18);
    window.setTimeout(() => void ctx.close(), 400);
  } catch {
    // Sound is decorative; never break the pane.
  }
}

export default function VetoRing() {
  const { vetoes, now, soundOn, authHeaders } = useMission();
  const [deciding, setDeciding] = useState<string | null>(null);
  const [late, setLate] = useState<string | null>(null);
  const [failed, setFailed] = useState("");
  const totalRef = useRef(0);
  const soundedRef = useRef<string | null>(null);

  const list = Object.values(vetoes);
  const open = list
    .filter((v) => v.state === "pending")
    .sort((a, b) => a.deadlineMs - b.deadlineMs)[0];
  const lastResolved = [...list].reverse().find((v) => v.state !== "pending");

  useEffect(() => {
    if (open && soundedRef.current !== open.runId) {
      soundedRef.current = open.runId;
      if (soundOn) beep();
    }
    if (!open) soundedRef.current = null;
  }, [open, soundOn]);

  if (!open) {
    return (
      <section id="tour-veto" aria-label="Cancel window" className="rounded-lg border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold text-text">Cancel window</h2>
        <p className="mt-2 text-xs text-text-muted">
          {lastResolved
            ? `Last: ${outcomeOf(lastResolved)}${lastResolved.decidedBy ? ` (${lastResolved.decidedBy})` : ""}`
            : "Nothing waiting for a decision."}
        </p>
        <p className="mt-1 text-[11px] text-text-faint">
          Auto-fix on · 20 s cancel window · kill switch off
        </p>
      </section>
    );
  }

  if (!open.ready) {
    return (
      <section id="tour-veto" aria-label="Cancel window" className="rounded-lg border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold text-text">Cancel window</h2>
        <p className="mt-2 animate-pulse text-sm text-text" aria-live="polite">
          Verifying fix…
        </p>
        <p className="mt-0.5 text-xs text-text-muted">{open.summary || `${open.domain} fix`}</p>
        <p className="mt-1 text-[11px] text-text-faint">
          The 20 s countdown starts once the fix passes verification.
        </p>
      </section>
    );
  }

  const deadlineLeft =
    open.deadlineMs > 0 ? Math.max(0, Math.ceil((open.deadlineMs - now) / 1000)) : open.secondsLeft;
  // Server ticks correct the deadline-derived countdown when they disagree.
  const left =
    open.secondsLeft > 0 && Math.abs(open.secondsLeft - deadlineLeft) > 2
      ? open.secondsLeft
      : deadlineLeft;
  if (left > totalRef.current) totalRef.current = left;
  const total = Math.max(totalRef.current, 1);
  const frac = Math.max(0, Math.min(1, left / total));
  const tone = left <= 5 ? "crit" : left <= 10 ? "amber" : "indigo";
  const stroke =
    tone === "crit" ? "stroke-crit" : tone === "amber" ? "stroke-warn" : "stroke-brand";

  async function decide(approve: boolean) {
    if (deciding) return;
    setDeciding(open.runId);
    setFailed("");
    setLate(null);
    try {
      const response = await fetch(
        `${apiUrl}/api/actions/${encodeURIComponent(open.runId)}/${approve ? "approve" : "disapprove"}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ device: "dashboard" }),
        },
      );
      if (response.status === 409) {
        setLate(open.runId);
        return;
      }
      if (response.status === 401) {
        throw new Error("Operator only — the countdown will act for you.");
      }
      if (!response.ok) throw new Error(await responseDetail(response));
    } catch (err) {
      setFailed(err instanceof Error ? err.message : "Decision failed.");
    } finally {
      setDeciding((current) => (current === open.runId ? null : current));
    }
  }

  return (
    <section id="tour-veto" aria-label="Cancel window" className="rounded-lg border border-border bg-surface p-4">
      <h2 className="text-sm font-semibold text-text">Cancel window</h2>
      <div className="mt-2 flex items-center gap-3">
        <svg
          viewBox="0 0 80 80"
          className={`h-20 w-20 -rotate-90 ${tone === "crit" ? "animate-pulse" : ""}`}
          role="img"
          aria-label={`${left} seconds left to cancel`}
        >
          <circle cx="40" cy="40" r={RADIUS} fill="none" strokeWidth="7" className="stroke-border" />
          <circle
            cx="40"
            cy="40"
            r={RADIUS}
            fill="none"
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={CIRCLE}
            strokeDashoffset={CIRCLE * (1 - frac)}
            className={stroke}
          />
        </svg>
        <div className="min-w-0">
          <p className="text-4xl tabular-nums text-text" aria-live="polite">
            {left}
            <span className="ml-1 text-sm text-text-faint">s</span>
          </p>
          <p className="mt-0.5 truncate text-xs text-text-muted" title={open.summary}>
            {open.summary || `${open.domain} fix`}
          </p>
        </div>
      </div>
      {late === open.runId ? (
        <p className="mt-2 text-sm text-warn">Too late — the window already closed.</p>
      ) : (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            disabled={deciding !== null}
            onClick={() => void decide(false)}
            className="flex-1 rounded-md bg-danger px-3 py-2 text-sm font-semibold text-on-brand hover:brightness-110 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={deciding !== null}
            onClick={() => void decide(true)}
            className="flex-1 rounded-md bg-brand px-3 py-2 text-sm font-semibold text-on-brand hover:brightness-110 disabled:opacity-50"
          >
            Do it now
          </button>
        </div>
      )}
      {failed && <p className="mt-1.5 text-xs text-crit">{failed}</p>}
      {open.detail && <p className="mt-1.5 line-clamp-2 text-xs text-text-faint">{open.detail}</p>}
    </section>
  );
}
