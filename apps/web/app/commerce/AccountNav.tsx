// Demo Mission Control: one door into production. Account pages live
// behind /signin, not as extra icons on the public demo chrome.
"use client";

import Link from "next/link";
import { signInHref } from "../lib/nextPath";
import { useSession } from "../lib/session";

const LINK =
  "inline-flex items-center justify-center rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand";

export default function AccountNav() {
  const { status, signOut } = useSession();
  if (status === "loading") return null;
  if (status === "signed-out") {
    return (
      <Link href={signInHref("/connect")} className={LINK}>
        Connect production
      </Link>
    );
  }
  return (
    <>
      <Link href="/connect" className={LINK}>
        Your production
      </Link>
      <button
        type="button"
        onClick={signOut}
        className={`${LINK} cursor-pointer`}
      >
        Sign out
      </button>
    </>
  );
}
