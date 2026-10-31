"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import Logo from "../components/Logo";
import ThemeToggle from "../components/ThemeToggle";
import { signInHref } from "../lib/nextPath";
import { useSession } from "../lib/session";

function menuClass(active: boolean): string {
  return active
    ? "rounded-lg bg-brand/10 px-2.5 py-1.5 text-xs font-medium text-brand-cyan outline-none focus-visible:ring-2 focus-visible:ring-brand"
    : "rounded-lg px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand";
}

function MenuLinks() {
  const pathname = usePathname();
  return (
    <>
      <Link href="/guide" className={menuClass(pathname === "/guide")}>
        How to
      </Link>
      <Link href="/guide#phone" className={menuClass(false)}>
        Get the app
      </Link>
      <Link href="/support" className={menuClass(pathname === "/support")}>
        Support
      </Link>
    </>
  );
}

export default function WelcomeHeader() {
  const { status } = useSession();
  const signedIn = status === "signed-in";

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
        <Link
          href="/welcome"
          className="flex items-center gap-1.5 rounded outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <Logo size={18} />
          <span className="text-sm font-semibold">TelemetryAgent</span>
        </Link>
        <div className="ms-auto flex flex-wrap items-center gap-2">
          <Suspense
            fallback={
              <>
                <Link href="/guide" className={menuClass(false)}>
                  How to
                </Link>
                <Link href="/guide#phone" className={menuClass(false)}>
                  Get the app
                </Link>
                <Link href="/support" className={menuClass(false)}>
                  Support
                </Link>
              </>
            }
          >
            <MenuLinks />
          </Suspense>
          <Link
            href="/start"
            className="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            Live demo
          </Link>
          {signedIn ? (
            <Link
              href="/connect"
              className="rounded-lg bg-brand px-2.5 py-1.5 text-xs font-medium text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
            >
              Your production
            </Link>
          ) : (
            <Link
              href={signInHref("/connect")}
              className="rounded-lg bg-brand px-2.5 py-1.5 text-xs font-medium text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
            >
              Sign in
            </Link>
          )}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
