// Account cluster for the Mission Control header (C-N3): org switcher,
// members/devices/usage links, sign in/out.
"use client";

import { ChartColumn, LogIn, LogOut, Smartphone, Users } from "lucide-react";
import Link from "next/link";
import { useSession } from "../lib/session";
import { OrgSwitcher } from "./components";

const LINK =
  "inline-flex items-center justify-center rounded-lg border border-border bg-surface-2 p-1.5 text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand";

export default function AccountNav() {
  const { status, user, orgs, activeOrg, signOut, switchOrg } = useSession();
  if (status === "loading") return null;
  if (status === "signed-out") {
    return (
      <Link href="/signin" title="Sign in" aria-label="Sign in" className={LINK}>
        <LogIn size={15} aria-hidden />
      </Link>
    );
  }
  return (
    <>
      <OrgSwitcher orgs={orgs} activeId={activeOrg?.id ?? null} onSwitch={switchOrg} />
      <Link href="/members" title="Members" aria-label="Members" className={LINK}>
        <Users size={15} aria-hidden />
      </Link>
      <Link href="/devices" title="Your devices" aria-label="Your devices" className={LINK}>
        <Smartphone size={15} aria-hidden />
      </Link>
      <Link href="/usage" title="Usage" aria-label="Usage" className={LINK}>
        <ChartColumn size={15} aria-hidden />
      </Link>
      <button
        type="button"
        onClick={signOut}
        title={user ? `Sign out (${user.email})` : "Sign out"}
        aria-label="Sign out"
        className={`${LINK} cursor-pointer`}
      >
        <LogOut size={15} aria-hidden />
      </button>
    </>
  );
}
