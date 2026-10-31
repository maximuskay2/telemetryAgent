// Usage (C-N5): usage vs free allowance, no prices or billing.
"use client";

import { useCallback, useEffect, useState } from "react";
import { Usage } from "../lib/commerce";
import { useSession } from "../lib/session";
import { Card } from "../ui";
import AccountChrome from "../commerce/AccountChrome";
import RequireAuth from "../commerce/RequireAuth";
import { ApiErrorView, Loading, UsageView } from "../commerce/components";

export default function UsagePage() {
  return (
    <RequireAuth>
      <AccountChrome>
        <UsageInner />
      </AccountChrome>
    </RequireAuth>
  );
}

function UsageInner() {
  const { activeOrg, api } = useSession();
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

  if (!activeOrg) {
    return (
      <main className="mx-auto w-full max-w-2xl px-4 py-8">
        <p className="text-sm text-text-muted">Creating your organization…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 px-4 py-8">
      <div>
        <h1 className="mb-1 text-xl font-semibold text-text">Usage</h1>
        <p className="text-sm text-text-muted">
          What {activeOrg.name} used against the free allowance.
        </p>
      </div>
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
