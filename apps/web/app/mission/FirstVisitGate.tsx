"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ONBOARDED_KEY } from "../lib/setupApi";

/**
 * First visit to / lands on /welcome. Mission Control opens only after
 * the demo walkthrough (`/?tour=1`) or a finished production connect.
 */
export default function FirstVisitGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    let onboarded = false;
    try {
      onboarded = window.localStorage.getItem(ONBOARDED_KEY) === "1";
    } catch {
      onboarded = false;
    }
    if (!onboarded && params.get("tour") === null) {
      router.replace("/welcome");
      return;
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg font-sans text-text">
        <p className="text-sm text-text-muted" role="status">
          Loading Mission Control…
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
