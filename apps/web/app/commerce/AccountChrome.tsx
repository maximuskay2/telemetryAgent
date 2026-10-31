"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { useSession } from "../lib/session";
import { OrgSwitcher } from "./components";

const NAV = [
  { href: "/connect", label: "Connect" },
  { href: "/members", label: "Members" },
  { href: "/devices", label: "Devices" },
  { href: "/usage", label: "Usage" },
] as const;

function navClass(active: boolean): string {
  return active
    ? "rounded-lg bg-brand/10 px-2.5 py-1.5 text-xs font-medium text-brand-cyan outline-none focus-visible:ring-2 focus-visible:ring-brand"
    : "rounded-lg px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand";
}

/** Shared header for signed-in production pages. Demo stays on /welcome and /start. */
export default function AccountChrome({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user, orgs, activeOrg, switchOrg, signOut } = useSession();

  return (
    <div className="min-h-screen bg-bg font-sans text-text">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
          <Link
            href="/welcome"
            className="flex items-center gap-1.5 rounded outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <span className="text-sm text-brand-cyan" aria-hidden>
              ◆
            </span>
            <span className="text-sm font-semibold">TelemetryAgent</span>
          </Link>
          <nav aria-label="Your account" className="flex flex-wrap items-center gap-0.5">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={navClass(pathname === item.href || pathname.startsWith(`${item.href}/`))}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ms-auto flex flex-wrap items-center gap-2">
            <Link
              href="/guide"
              className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
            >
              How to
            </Link>
            <Link
              href="/support"
              className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
            >
              Support
            </Link>
            <Link
              href="/start"
              className="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
            >
              Live demo
            </Link>
            {orgs.length > 0 && (
              <OrgSwitcher
                orgs={orgs}
                activeId={activeOrg?.id ?? null}
                onSwitch={switchOrg}
              />
            )}
            {user && (
              <span className="hidden text-xs text-text-muted sm:inline">{user.email}</span>
            )}
            <button
              type="button"
              onClick={signOut}
              className="cursor-pointer rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
            >
              Sign out
            </button>
            <ThemeToggle />
          </div>
        </div>
      </header>
      {children}
    </div>
  );
}
