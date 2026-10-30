// Usage (C-N5): usage vs free allowance, no prices or billing.
"use client";

import { useCallback, useEffect, useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { CommerceError, Usage } from "../lib/commerce";
import { useSession } from "../lib/session";
import { Card } from "../ui";
import {
  ApiErrorView,
  Loading,
  OrgSwitcher,
  UsageView,
} from "../commerce/components";

export default function UsagePage() {
  const { status, orgs, activeOrg, api, switchOrg } = useSession();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<unknown>(null);

  const reload = useCallback(async () => {
    if (!activeOrg) return;
    setError(null);
    try {
      setUsage(await api.getUsage(activeOrg.id));
    } catch (err) {
      setError(err);
    }
  }, [api, activeOrg]);

  useEffect(() => {
    setUsage(null);
    void reload();
  }, [reload]);

  if (status === "loading") {
    return (
      <main className="mx-auto w-full max-w-2xl px-4 py-8">
        <Loading />
      </main>
    );
  }
  if (status === "signed-out" || !activeOrg) {
    return (
      <main className="mx-auto w-full max-w-2xl space-y-4 px-4 py-8">
        <ApiErrorView error={new CommerceError(401, "Signed out")} />
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 px-4 py-8">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="mb-1 text-xl font-semibold text-text">Usage</h1>
          <p className="text-sm text-text-muted">
            What {activeOrg.name} used against the free allowance.
          </p>
        </div>
        <ThemeToggle />
      </div>
      <OrgSwitcher orgs={orgs} activeId={activeOrg.id} onSwitch={switchOrg} />
      {error ? (
        <ApiErrorView error={error} />
      ) : usage === null ? (
        <Loading />
      ) : (
        <Card title="This month">
          <UsageView usage={usage} />
        </Card>
      )}
    </main>
  );
}
