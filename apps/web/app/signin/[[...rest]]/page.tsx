// Sign-in (C-N3, C-N6, C-N7). Dev mock signs in locally; with a
// Clerk key the Clerk component owns sign-in; otherwise a pasted
// test JWT signs in local dev.
// Catch-all so Clerk path routing can own /signin/* (factor-one, sso-callback).
"use client";

import { SignIn } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Logo from "../../components/Logo";
import ThemeToggle from "../../components/ThemeToggle";
import { safeNext } from "../../lib/nextPath";
import { useSession } from "../../lib/session";
import { Card } from "../../ui";

function SignInInner() {
  const { status, devMode, clerkMode, signInDev, signInToken } = useSession();
  const router = useRouter();
  const search = useSearchParams();
  const next = safeNext(search.get("next"));
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (status === "signed-in") router.replace(next);
  }, [status, router, next]);

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
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    }
  }

  async function submitToken(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await signInToken(token);
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    }
  }

  return (
    <main className="mx-auto w-full max-w-md px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <Link
          href="/welcome"
          className="inline-flex items-center gap-1.5 text-sm text-brand-cyan"
        >
          <Logo size={18} />
          TelemetryAgent
        </Link>
        <ThemeToggle />
      </div>
      {clerkMode ? (
        <div className="flex justify-center">
          <SignIn
            routing="path"
            path="/signin"
            forceRedirectUrl={next}
            appearance={{
              variables: {
                colorPrimary: "#0866FF",
                borderRadius: "12px",
                fontFamily: "Optimistic, Helvetica, Arial, sans-serif",
              },
            }}
          />
        </div>
      ) : (
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
      )}
      {!devMode && (
        <details className="mt-4 rounded-xl border border-border bg-surface p-4">
          <summary className="cursor-pointer text-sm text-text">
            Local development: sign in with a test token
          </summary>
          <form onSubmit={submitToken} className="mt-3 space-y-3">
            <label className="flex flex-col gap-1 text-xs text-text-muted">
              Test session JWT (local API with TA_AUTH_TEST_ISSUER only)
              <input
                value={token}
                onChange={(event) => setToken(event.target.value)}
                placeholder="eyJhbGciOi…"
                autoComplete="off"
                spellCheck={false}
                className="rounded-lg border border-border bg-surface-2 px-2.5 py-2 font-mono text-xs text-text outline-none focus-visible:ring-2 focus-visible:ring-brand"
              />
            </label>
            {error && <p className="text-sm text-crit">{error}</p>}
            <button
              type="submit"
              className="w-full cursor-pointer rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm font-medium text-text outline-none hover:bg-surface-3 focus-visible:ring-2 focus-visible:ring-brand"
            >
              Sign in with test token
            </button>
          </form>
        </details>
      )}
      <p className="mt-4 text-center text-xs text-text-faint">
        New here? Signing in creates your organization. The live demo stays
        open from the home page — no account needed.
      </p>
    </main>
  );
}

export default function SignInPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto w-full max-w-md px-4 py-16">
          <p className="text-sm text-text-muted">Loading…</p>
        </main>
      }
    >
      <SignInInner />
    </Suspense>
  );
}
