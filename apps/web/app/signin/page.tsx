// Sign-in (C-N3). Dev mock signs in locally; the hosted flow plugs a
// Clerk session into SessionProvider once keys land (see NEEDS).
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { useSession } from "../lib/session";
import { Card } from "../ui";

export default function SignInPage() {
  const { status, devMode, signInDev } = useSession();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  if (status === "loading") {
    return (
      <main className="mx-auto w-full max-w-md px-4 py-16">
        <p className="text-sm text-text-muted">Loading…</p>
      </main>
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await signInDev(email);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    }
  }

  return (
    <main className="mx-auto w-full max-w-md px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <Link href="/welcome" className="text-sm text-brand-cyan">
          ← TelemetryAgent
        </Link>
        <ThemeToggle />
      </div>
      <Card title="Sign in">
        {devMode && (
          <p className="mb-3 inline-flex rounded-full border border-warn/40 bg-warn/10 px-2 py-0.5 text-[11px] text-warn">
            Development sign-in
          </p>
        )}
        <form onSubmit={submit} className="space-y-3">
          <label className="flex flex-col gap-1 text-xs text-text-muted">
            Work email
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.co"
              disabled={!devMode}
              className="rounded-lg border border-border bg-surface-2 px-2.5 py-2 text-sm text-text outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
            />
          </label>
          {error && <p className="text-sm text-crit">{error}</p>}
          {!devMode && (
            <p className="text-sm text-text-muted">
              Account sign-in is being connected. The demo stays open meanwhile.
            </p>
          )}
          <button
            type="submit"
            disabled={!devMode}
            className="w-full cursor-pointer rounded-lg bg-brand px-3 py-2 text-sm font-medium text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
          >
            Continue with email
          </button>
        </form>
      </Card>
      <p className="mt-4 text-center text-xs text-text-faint">
        New here? Signing in creates your organization.
      </p>
    </main>
  );
}
