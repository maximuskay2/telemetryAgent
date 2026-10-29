"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ONBOARDED_KEY } from "../lib/setupApi";

/**
 * D6: first visit to / lands on /welcome — unless the journey flag is set
 * or the URL carries ?tour / ?skip. ?skip=1 sets the flag (video shortcut).
 */
export default function FirstVisitGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("skip") === "1") {
      try {
        window.localStorage.setItem(ONBOARDED_KEY, "1");
      } catch {
        // Private mode: the gate just runs again next visit.
      }
      setReady(true);
      return;
    }
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
