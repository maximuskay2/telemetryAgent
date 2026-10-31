"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { signInHref } from "../lib/nextPath";
import { useSession } from "../lib/session";
import { apiHealth } from "../lib/setupApi";

/** Landing CTA: demo is public; production starts at sign-in. */
export default function DemoCta() {
  const { status } = useSession();
  const [awake, setAwake] = useState<boolean | null>(null);
  const productionHref =
    status === "signed-in" ? "/connect" : signInHref("/connect");

  useEffect(() => {
    let cancelled = false;
    const ping = async () => {
      const ok = await apiHealth();
      if (!cancelled) setAwake(ok);
      return ok;
    };
    ping();
    const timer = window.setInterval(async () => {
      if (cancelled) return;
      if (await ping()) window.clearInterval(timer);
    }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <>
      {awake === false ? (
        <button
          type="button"
          disabled
          className="inline-flex cursor-wait items-center justify-center gap-2 rounded-lg border border-border bg-surface-2 px-5 py-2.5 text-sm font-medium text-text-muted"
        >
          <span
            aria-hidden
            className="size-2 animate-pulse rounded-full bg-warn"
          />
          Demo is waking up…
        </button>
      ) : (
        <Link
          href="/start"
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-on-brand outline-none transition-colors hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
        >
          Try the live demo
          <span aria-hidden>→</span>
        </Link>
      )}
      <Link
        href={productionHref}
        className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface-2 px-5 py-2.5 text-sm font-medium text-text transition-colors outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
      >
        {status === "signed-in" ? "Your production" : "Connect your production"}
      </Link>
    </>
  );
}
