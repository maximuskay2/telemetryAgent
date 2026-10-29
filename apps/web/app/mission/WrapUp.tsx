"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { apiUrl, responseDetail } from "../lib/api";
import { demoStatus, ONBOARDED_KEY } from "../lib/setupApi";
import { Button } from "../ui";
import { useMission } from "./state";
import type { TourSummary } from "./Tour";

function fmtMs(ms: number | null): string {
  if (ms === null) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** J8: what-just-happened modal after the tour. Sets the onboarded flag. */
export default function WrapUp({
  summary,
  onClose,
}: {
  summary: TourSummary;
  onClose: () => void;
}) {
  const { warnFixMs, resetWorld } = useMission();
  const [prUrl, setPrUrl] = useState<string | null>(null);
  const [pairUrl, setPairUrl] = useState<string | null>(null);
  const [pairOpen, setPairOpen] = useState(false);
  const [pairFailed, setPairFailed] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(ONBOARDED_KEY, "1");
    } catch {
      // ignore
    }
    headingRef.current?.focus();
    demoStatus()
      .then((snapshot) => {
        if (snapshot.pr_url) setPrUrl(snapshot.pr_url);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function togglePair() {
    if (pairOpen) {
      setPairOpen(false);
      return;
    }
    setPairOpen(true);
    setPairFailed("");
    if (pairUrl) return;
    try {
      const response = await fetch(`${apiUrl}/api/pairing`);
      if (!response.ok) throw new Error(await responseDetail(response));
      const body = (await response.json()) as { api_url?: unknown };
      if (typeof body.api_url !== "string") {
        throw new Error("Pairing URL unavailable.");
      }
      setPairUrl(body.api_url);
    } catch (err) {
      setPairFailed(err instanceof Error ? err.message : "Pairing failed.");
    }
  }

  async function replay() {
    await resetWorld();
    window.location.assign("/?tour=1");
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="wrapup-title"
        className="w-full max-w-md rounded-lg border border-border bg-surface p-5 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <h2
          id="wrapup-title"
          ref={headingRef}
          tabIndex={-1}
          className="text-base font-semibold outline-none"
        >
          Fixed ✓ — here&apos;s what just happened
        </h2>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-center">
          <div className="rounded-md border border-border bg-surface-2 px-2 py-2">
            <dt className="text-[11px] text-text-faint">Warning → fixed</dt>
            <dd className="text-sm font-semibold tabular-nums">
              {fmtMs(warnFixMs)}
            </dd>
          </div>
          <div className="rounded-md border border-border bg-surface-2 px-2 py-2">
            <dt className="text-[11px] text-text-faint">Fix attempts</dt>
            <dd className="text-sm font-semibold tabular-nums">
              {Math.max(1, summary.attempts)}
            </dd>
          </div>
        </dl>

        <div className="mt-4 flex flex-col gap-2">
          {prUrl && (
            <a
              href={prUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded text-sm text-brand-cyan underline outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              View pull request ↗
            </a>
          )}
          {summary.runId && (
            <Link
              href={`/incidents/${summary.runId}`}
              className="rounded text-sm text-brand-cyan underline outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              Read incident report
            </Link>
          )}
          <div>
            <Button tone="ghost" onClick={() => void togglePair()}>
              Get alerts on your phone
            </Button>
            {pairOpen &&
              (pairUrl ? (
                <div className="mt-2 rounded-md border border-border bg-surface-2 p-3">
                  <QRCodeSVG
                    value={JSON.stringify({ api: pairUrl })}
                    size={120}
                  />
                  <p className="mt-2 font-mono text-[11px] break-all text-text-muted">
                    {pairUrl}
                  </p>
                </div>
              ) : (
                <p className="mt-2 text-xs text-text-muted">
                  {pairFailed || "Loading…"}
                </p>
              ))}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button tone="primary" onClick={() => void replay()}>
            Replay the demo
          </Button>
          <Link
            href="/setup"
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[13px] font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
          >
            Advanced setup
          </Link>
          <Button tone="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
