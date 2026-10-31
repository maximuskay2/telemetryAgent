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
    "Telemetry is the signals a system sends while it runs. TelemetryAgent reports a proven fix, asks you, and acts if you do not answer — you give that permission.",
};

const STEPS = [
  {
    title: "Learn the system",
    text: "It reads the manuals and watches a quiet stretch. After that it knows what normal looks like.",
  },
  {
    title: "Fix, prove, report",
    text: "It writes a fix with a test, proves it, and sends you the report. You see the diagnosis and the proof first.",
  },
  {
    title: "You give permission",
    text: "It asks. Approve, cancel, or do nothing. If no one answers, it acts — because you already allowed that.",
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
            Telemetry is the signal. TelemetryAgent is the engineer.
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-sm text-text-muted sm:text-base">
            Every running system talks. Software writes logs. Equipment
            sends sensor readings. TelemetryAgent understands the system,
            sends you a report, and asks. If no one answers, it acts —
            you gave that permission.
          </p>
        </div>

        <section
          aria-labelledby="what-telemetry-is"
          className="mx-auto mt-10 grid max-w-3xl gap-3 sm:grid-cols-2"
        >
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
              In software
            </p>
            <h2 id="what-telemetry-is" className="mt-1 text-sm font-semibold">
              Logs, errors, retries, latency
            </h2>
            <p className="mt-2 text-xs leading-relaxed text-text-muted">
              A crash traceback is telemetry. So is a burst of retries.
              So is a shop that cannot take an order.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
              In hardware
            </p>
            <h2 className="mt-1 text-sm font-semibold">
              Temperature, door, current, vibration
            </h2>
            <p className="mt-2 text-xs leading-relaxed text-text-muted">
              A freezer climbing past 8 °C is telemetry. So is a door left
              open. A scheduled defrost is also telemetry — it is normal.
            </p>
          </div>
        </section>

        <section
          aria-labelledby="what-the-agent-is"
          className="mx-auto mt-3 max-w-3xl rounded-lg border border-border bg-surface p-5"
        >
          <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
            What TelemetryAgent is
          </p>
          <h2 id="what-the-agent-is" className="mt-1 text-sm font-semibold">
            One agent for both kinds of signal
          </h2>
          <p className="mt-2 text-xs leading-relaxed text-text-muted">
            It learns the system from your manuals and a quiet watch. Then
            it flags only real failures. It writes a fix, proves it, and
            sends you the report. It asks. If there is no human
            interaction, it acts — because you already gave permission.
            Free for now. No signup for the live demo.
          </p>
        </section>

        <div className="mx-auto mt-10 grid max-w-3xl gap-3 sm:grid-cols-2">
          <section
            aria-label="Software example: AutoParts Lagos"
            className="rounded-lg border border-border bg-surface p-4"
          >
            <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
              Example · software
            </p>
            <ShopArt />
            <h2 className="mt-2 text-sm font-semibold">AutoParts Lagos</h2>
            <p className="mt-2 text-xs leading-relaxed text-text-muted">
              A live parts shop. Web, orders, inventory. Two customers buy
              the same part and the shop deadlocks. The agent reads the
              crash log, writes a lock-order fix, and proves it with a
              test.
            </p>
          </section>
          <section
            aria-label="Hardware example: cold-chain freezer"
            className="rounded-lg border border-border bg-surface p-4"
          >
            <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
              Example · hardware
            </p>
            <FreezerArt />
            <h2 className="mt-2 text-sm font-semibold">Cold-chain freezer</h2>
            <p className="mt-2 text-xs leading-relaxed text-text-muted">
              Vaccine and food storage at 2–8 °C. Door, compressor,
              sensors. A door left open is an incident. A defrost cycle is
              not. The agent knows the difference.
            </p>
          </section>
        </div>

        <div className="mx-auto mt-8 flex max-w-3xl flex-wrap items-center justify-center gap-3">
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
