"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { signInHref } from "../lib/nextPath";
import { useSession } from "../lib/session";

/** Production pages: signed-in only. Demo pages never wrap this. */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();

  useEffect(() => {
    if (status !== "signed-out") return;
    const here = pathname + (search.toString() ? `?${search.toString()}` : "");
    router.replace(signInHref(here));
  }, [status, pathname, search, router]);

  if (status === "loading" || status === "signed-out") {
    return (
      <main className="mx-auto w-full max-w-md px-4 py-16">
        <p className="text-sm text-text-muted" role="status">
          {status === "signed-out" ? "Taking you to sign in…" : "Loading…"}
        </p>
      </main>
    );
  }
  return <>{children}</>;
}
