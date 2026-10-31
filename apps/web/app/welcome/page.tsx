import type { Metadata } from "next";
import Attribution from "../components/Attribution";
import Logo from "../components/Logo";
import DemoCta from "./DemoCta";
import WelcomeHeader from "./WelcomeHeader";

/** Set to the video URL once recorded; the button stays hidden until then. */
const VIDEO_URL = "";

export const metadata: Metadata = {
  title: "TelemetryAgent — AI on-call engineer",
  description:
    "An AI on-call engineer that catches failures, proves its fix works, and asks before it acts.",
};

const STEPS = [
  {
    title: "Notice",
    text: "Watchers learn what normal looks like, then flag the rest — retries, deadlocks, a freezer door left open.",
  },
  {
    title: "Fix & prove",
    text: "The agent diagnoses the cause, writes a fix with a test, and proves it fails before and passes after.",
  },
  {
    title: "Ask, then act",
    text: "Nothing deploys without a 20-second cancel window. Approve it, cancel it, or let the countdown decide.",
  },
];

function ShopArt() {
  return (
    <svg
      viewBox="0 0 120 72"
      className="h-16 w-full"
      role="img"
      aria-label="Online parts shop serving orders"
    >
      <rect
        x="8"
        y="20"
        width="104"
        height="44"
        rx="6"
        className="fill-surface-2 stroke-border"
      />
      <path d="M8 26 L20 12 H100 L112 26 Z" className="fill-brand/30" />
      <rect x="20" y="34" width="34" height="6" rx="3" className="fill-brand" />
      <rect x="20" y="44" width="46" height="6" rx="3" className="fill-brand/50" />
      <rect x="20" y="54" width="28" height="6" rx="3" className="fill-brand/70" />
      <circle cx="96" cy="47" r="9" className="fill-ok/20 stroke-ok" />
      <path
        d="M91.5 47 l3 3 5-6"
        className="stroke-ok"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  );
}

function FreezerArt() {
  return (
    <svg
      viewBox="0 0 120 72"
      className="h-16 w-full"
      role="img"
      aria-label="Cold-chain freezer holding 2 to 8 degrees"
    >
      <rect
        x="38"
        y="6"
        width="44"
        height="60"
        rx="6"
        className="fill-surface-2 stroke-border"
      />
      <line x1="38" y1="28" x2="82" y2="28" className="stroke-border" />
      <line
        x1="74"
        y1="12"
        x2="74"
        y2="22"
        className="stroke-text-faint"
        strokeWidth="2"
      />
      <line
        x1="74"
        y1="34"
        x2="74"
        y2="46"
        className="stroke-text-faint"
        strokeWidth="2"
      />
      <text x="60" y="62" textAnchor="middle" className="fill-brand-cyan text-[9px]">
        4.0°C
      </text>
    </svg>
  );
}

export default function WelcomePage() {
  return (
    <div className="min-h-screen bg-bg font-sans text-text">
      <WelcomeHeader />

      <main className="mx-auto w-full max-w-5xl px-4 pb-16">
        <div className="mx-auto max-w-3xl pt-12 text-center">
          <div className="flex justify-center">
            <Logo size={44} />
          </div>
          <p className="mt-4 text-xs font-medium tracking-wide text-brand-cyan uppercase">
            AI on-call engineer
          </p>
          <h1 className="mt-3 text-3xl font-semibold text-balance sm:text-4xl">
            An AI on-call engineer that catches failures, proves its fix
            works, and asks before it acts.
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-sm text-text-muted sm:text-base">
            Watch it guard a live parts shop and a cold-chain freezer. Set up
            in about 3 minutes, then break something and see it fixed in 2
            more. No signup.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <DemoCta />
            {VIDEO_URL !== "" && (
              <a
                href={VIDEO_URL}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface-2 px-5 py-2.5 text-sm font-medium text-text outline-none hover:border-text-faint focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
              >
                Watch 3-min video
              </a>
            )}
          </div>
        </div>

        <div className="mx-auto mt-10 grid max-w-3xl gap-3 sm:grid-cols-2">
          <section
            aria-label="Demo business, part one: the parts shop"
            className="rounded-lg border border-border bg-surface p-4"
          >
            <ShopArt />
            <h2 className="mt-2 text-sm font-semibold">AutoParts Lagos</h2>
            <p className="mt-1 text-xs text-text-muted">
              Online parts shop: web, orders and inventory services taking
              real traffic.
            </p>
          </section>
          <section
            aria-label="Demo business, part two: the freezer"
            className="rounded-lg border border-border bg-surface p-4"
          >
            <FreezerArt />
            <h2 className="mt-2 text-sm font-semibold">Cold-chain Freezer</h2>
            <p className="mt-1 text-xs text-text-muted">
              Vaccine and food storage holding 2–8 °C, compressor and sensors
              included.
            </p>
          </section>
        </div>

        <ol className="mx-auto mt-10 grid max-w-4xl list-none gap-3 p-0 sm:grid-cols-3">
          {STEPS.map((step, i) => (
            <li
              key={step.title}
              className="relative rounded-lg border border-border bg-surface p-4"
            >
              <p className="flex items-center gap-2 text-sm font-semibold">
                <span
                  aria-hidden
                  className="flex size-5 items-center justify-center rounded-full bg-brand text-[11px] tabular-nums text-on-brand"
                >
                  {i + 1}
                </span>
                {step.title}
              </p>
              <p className="mt-2 text-xs leading-relaxed text-text-muted">
                {step.text}
              </p>
            </li>
          ))}
        </ol>

        <p className="mx-auto mt-10 max-w-3xl text-center text-xs text-text-faint">
          Diagnosed by Muse Spark · Muse Spark Open on Baseten · Muse Wonder
          · Verified in a Modal sandbox
        </p>
        <Attribution className="mt-2 text-center" />
      </main>
    </div>
  );
}
