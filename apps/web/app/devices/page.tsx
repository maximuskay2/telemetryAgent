// Your devices (C-N3): pair phones with a code, revoke them here.
"use client";

import { useCallback, useEffect, useState } from "react";
import { Device, PairCode } from "../lib/commerce";
import { useSession } from "../lib/session";
import { Card } from "../ui";
import AccountChrome from "../commerce/AccountChrome";
import RequireAuth from "../commerce/RequireAuth";
import {
  ApiErrorView,
  DeviceList,
  Loading,
  PairCodeView,
} from "../commerce/components";

export default function DevicesPage() {
  return (
    <RequireAuth>
      <AccountChrome>
        <DevicesInner />
      </AccountChrome>
    </RequireAuth>
  );
}

function DevicesInner() {
  const { activeOrg, role, api } = useSession();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [label, setLabel] = useState("");
  const [pair, setPair] = useState<PairCode | null>(null);

  const reload = useCallback(async () => {
    if (!activeOrg) return;
    setError(null);
    try {
      const out = await api.listDevices(activeOrg.id);
      setDevices(out.devices);
    } catch (err) {
      setError(err);
    }
  }, [api, activeOrg]);

  useEffect(() => {
    setDevices(null);
    setPair(null);
    void reload();
  }, [reload]);

  if (!activeOrg) {
    return (
      <main className="mx-auto w-full max-w-2xl px-4 py-8">
        <p className="text-sm text-text-muted">Creating your organization…</p>
      </main>
    );
  }

  const canManage = role === "owner" || role === "admin";

  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 px-4 py-8">
      <div>
        <h1 className="mb-1 text-xl font-semibold text-text">Your devices</h1>
        <p className="text-sm text-text-muted">
          Phones paired for {activeOrg.name}. Revoking stops approvals now.
        </p>
      </div>
      {notice && <p className="text-sm text-ok">{notice}</p>}
      {error ? (
        <ApiErrorView error={error} />
      ) : devices === null ? (
        <Loading />
      ) : (
        <Card title="Paired phones">
          <DeviceList
            devices={devices}
            canManage={canManage}
            onRevoke={(deviceId) => {
              setNotice("");
              api
                .revokeDevice(activeOrg.id, deviceId)
                .then(() => {
                  setNotice("Phone revoked. Its approvals stop now.");
                  void reload();
                })
                .catch((err: unknown) => setError(err));
            }}
          />
        </Card>
      )}
      <Card title="Pair a phone">
        {pair ? (
          <div className="space-y-3">
            <PairCodeView code={pair.code} expiresIn="10 minutes" />
            <button
              type="button"
              onClick={() => setPair(null)}
              className="cursor-pointer text-sm text-brand-cyan outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              Pair another
            </button>
          </div>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setNotice("");
              api
                .pairDevice(activeOrg.id, label)
                .then((out) => {
                  setPair(out);
                  setLabel("");
                  void reload();
                })
                .catch((err: unknown) => setError(err));
            }}
            className="flex flex-wrap items-end gap-2"
          >
            <label className="flex flex-col gap-1 text-xs text-text-muted">
              Phone label
              <input
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="Ada's Pixel"
                className="w-56 rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-[13px] text-text outline-none focus-visible:ring-2 focus-visible:ring-brand"
              />
            </label>
            <button
              type="submit"
              className="cursor-pointer rounded-lg bg-brand px-3 py-1.5 text-[13px] font-medium text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
            >
              Get pairing code
            </button>
          </form>
        )}
      </Card>
    </main>
  );
}
