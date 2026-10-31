import type { Metadata } from "next";
import Link from "next/link";
import WelcomeHeader from "../welcome/WelcomeHeader";

export const metadata: Metadata = {
  title: "Support — TelemetryAgent",
  description: "Get help with the TelemetryAgent demo or your production setup.",
};

export default function SupportPage() {
  return (
    <div className="min-h-screen bg-bg font-sans text-text">
      <WelcomeHeader />
      <main className="mx-auto w-full max-w-2xl px-4 py-12">
        <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
          Support
        </p>
        <h1 className="mt-2 text-2xl font-semibold">We are here to help</h1>
        <p className="mt-3 text-sm leading-relaxed text-text-muted">
          Questions about the live demo, connecting production, members,
          devices, or teaching the agent what normal looks like — write or
          call. We read every message.
        </p>

        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <section className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-sm font-semibold">Email</h2>
            <p className="mt-2 text-xs text-text-muted">
              Best for setup details, screenshots, and anything that needs a
              paper trail.
            </p>
            <a
              href="mailto:support@maxit.com.ng"
              className="mt-3 inline-block rounded text-sm font-medium text-brand-cyan underline outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
            >
              support@maxit.com.ng
            </a>
          </section>
          <section className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-sm font-semibold">Phone</h2>
            <p className="mt-2 text-xs text-text-muted">
              For a quick walkthrough or if you are stuck mid-setup.
            </p>
            <a
              href="tel:+2348036954577"
              className="mt-3 inline-block rounded text-sm font-medium text-brand-cyan underline outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
            >
              0803 695 4577
            </a>
          </section>
        </div>

        <section className="mt-6 rounded-lg border border-border bg-surface p-5">
          <h2 className="text-sm font-semibold">What to include</h2>
          <ul className="mt-3 list-disc space-y-1.5 ps-5 text-xs leading-relaxed text-text-muted">
            <li>Whether you are on the live demo or connecting production.</li>
            <li>The page you were on (Home, guided setup, Connect, Mission Control).</li>
            <li>What you expected, and what happened instead.</li>
            <li>The system name, if you have already created one.</li>
          </ul>
        </section>

        <p className="mt-8 text-sm text-text-muted">
          Prefer to try it first?{" "}
          <Link
            href="/guide"
            className="rounded font-medium text-brand-cyan underline outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            Read the how-to
          </Link>{" "}
          or{" "}
          <Link
            href="/start"
            className="rounded font-medium text-brand-cyan underline outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            start the live demo
          </Link>
          .
        </p>
      </main>
    </div>
  );
}
