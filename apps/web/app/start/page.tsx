"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { Button, Card } from "../ui";

function WatchArt() {
  return (
    <svg
      viewBox="0 0 200 72"
      className="h-20 w-full"
      role="img"
      aria-label="Software services and freezer sensors under watch"
    >
      <rect x="8" y="12" width="86" height="48" rx="6" className="fill-surface-2 stroke-border" />
      <rect x="18" y="22" width="40" height="6" rx="3" className="fill-brand" />
      <rect x="18" y="32" width="52" height="6" rx="3" className="fill-brand/50" />
      <rect x="18" y="42" width="34" height="6" rx="3" className="fill-brand/70" />
      <rect x="106" y="12" width="44" height="48" rx="6" className="fill-surface-2 stroke-border" />
      <text x="128" y="44" textAnchor="middle" className="fill-brand-cyan text-[11px]">
        4.0°
      </text>
      <circle cx="172" cy="36" r="12" className="fill-ok/20 stroke-ok" />
      <path
        d="M166 36 l4 4 7-8"
        className="stroke-ok"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SafeArt() {
  return (
    <svg
      viewBox="0 0 200 72"
      className="h-20 w-full"
      role="img"
      aria-label="Learning first, cancel window before acting, hard limits locked"
    >
      <circle cx="40" cy="36" r="20" className="fill-surface-2 stroke-border" />
      <path d="M40 16 a20 20 0 0 1 17 10" className="stroke-brand" strokeWidth="4" fill="none" />
      <text x="40" y="41" textAnchor="middle" className="fill-text text-[11px]">
        20s
      </text>
      <rect x="76" y="20" width="52" height="32" rx="6" className="fill-surface-2 stroke-border" />
      <circle cx="102" cy="32" r="4" className="fill-warn" />
      <rect x="94" y="38" width="16" height="8" rx="2" className="fill-warn/60" />
      <path d="M144 28 h28 M144 36 h28 M144 44 h20" className="stroke-ok" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

function PathArt() {
  return (
    <svg
      viewBox="0 0 200 72"
      className="h-20 w-full"
      role="img"
      aria-label="Two paths: demo business or your own system"
    >
      <circle cx="24" cy="36" r="8" className="fill-brand" />
      <path d="M32 36 H80 M80 36 L120 18 M80 36 L120 54" className="stroke-border" strokeWidth="3" fill="none" />
      <rect x="120" y="8" width="72" height="20" rx="6" className="fill-brand/20 stroke-brand" />
      <rect x="120" y="44" width="72" height="20" rx="6" className="fill-surface-2 stroke-border" />
    </svg>
  );
}

const CARDS = [
  {
    eyebrow: "1 of 3 · What it watches",
    title: "Your software and your equipment",
    body: "TelemetryAgent watches both sides of a business: the services customers click — web, orders, inventory — and the physical equipment — freezers, compressors, sensors. One agent, one timeline.",
    art: <WatchArt />,
  },
  {
    eyebrow: "2 of 3 · How it stays safe",
    title: "It learns normal before it judges",
    body: "First it reads your manuals and watches two quiet minutes, so a defrost cycle or a cold cache never counts as a failure. Then nothing acts without a 20-second cancel window — and hard limits can only be set by a human.",
    art: <SafeArt />,
  },
  {
    eyebrow: "3 of 3 · Choose your path",
    title: "Start with the demo business",
    body: "A live parts shop and a cold-chain freezer are already running. Set them up in about 3 minutes, then break the shop and watch the agent fix it.",
    art: <PathArt />,
  },
];

export default function StartPage() {
  const [index, setIndex] = useState(0);
  const [ownSystem, setOwnSystem] = useState(false);
  const touchX = useRef<number | null>(null);
  const last = CARDS.length - 1;
  const card = CARDS[index];

  const next = useCallback(() => setIndex((i) => Math.min(last, i + 1)), [last]);
  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") next();
      else if (event.key === "ArrowLeft") back();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, back]);

  return (
    <div className="flex min-h-screen flex-col bg-bg font-sans text-text">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex w-full max-w-2xl items-center gap-1.5 px-4 py-3">
          <span className="text-sm text-brand-cyan" aria-hidden>
            ◆
          </span>
          <span className="text-sm font-semibold">TelemetryAgent</span>
          <ThemeToggle className="ms-auto" />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4 py-8">
        <div
          onTouchStart={(e) => {
            touchX.current = e.touches[0]?.clientX ?? null;
          }}
          onTouchEnd={(e) => {
            const start = touchX.current;
            const end = e.changedTouches[0]?.clientX ?? null;
            touchX.current = null;
            if (start === null || end === null) return;
            if (start - end > 48) next();
            else if (end - start > 48) back();
          }}
        >
          <Card>
            <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
              {card.eyebrow}
            </p>
            <h1 className="mt-2 text-xl font-semibold">{card.title}</h1>
            <div className="mt-3">{card.art}</div>
            <p className="mt-3 text-sm leading-relaxed text-text-muted">
              {card.body}
            </p>

            {index === last && (
              <div className="mt-5 flex flex-col gap-2">
                <Link
                  href="/start/setup"
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-on-brand outline-none transition-colors hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
                >
                  Use the demo business
                  <span aria-hidden>→</span>
                </Link>
                <Button tone="ghost" onClick={() => setOwnSystem(!ownSystem)}>
                  Connect my own system
                </Button>
                {ownSystem && (
                  <p className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs leading-relaxed text-text-muted">
                    After the hackathon — join the waitlist. For now you can
                    explore the{" "}
                    <Link
                      href="/setup"
                      className="rounded text-brand-cyan underline outline-none focus-visible:ring-2 focus-visible:ring-brand"
                    >
                      Advanced setup
                    </Link>
                    .
                  </p>
                )}
              </div>
            )}
          </Card>
        </div>

        <div
          className="mt-4 flex items-center justify-center gap-2"
          role="tablist"
          aria-label="Onboarding progress"
        >
          {CARDS.map((c, i) => (
            <button
              key={c.eyebrow}
              type="button"
              role="tab"
              aria-selected={i === index}
              aria-label={`Card ${i + 1}: ${c.title}`}
              onClick={() => setIndex(i)}
              className={`h-2 rounded-full outline-none transition-all focus-visible:ring-2 focus-visible:ring-brand ${
                i === index ? "w-6 bg-brand" : "w-2 bg-border hover:bg-text-faint"
              }`}
            />
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between">
          <Button tone="ghost" disabled={index === 0} onClick={back}>
            ← Back
          </Button>
          {index < last ? (
            <Button tone="primary" onClick={next}>
              Next →
            </Button>
          ) : (
            <span className="text-xs text-text-faint">
              3 clicks to the guided setup
            </span>
          )}
        </div>

        <p className="mt-6 text-center text-xs">
          <Link
            href="/welcome"
            className="rounded text-text-muted underline outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            ← Back to welcome
          </Link>
        </p>
      </main>
    </div>
  );
}
