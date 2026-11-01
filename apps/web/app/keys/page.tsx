// /keys: every secret in one place. Old values can't be displayed
// (the server keeps hashes only), so each row shows its ****last4 hint
// and rotates to a new key, shown once.
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import RequireAuth from "../commerce/RequireAuth";
import AccountChrome from "../commerce/AccountChrome";
import {
  listConnections,
  rotateConnection,
} from "../connect/api";
import { KeyOnce } from "../connect/ui";
import { useSystems } from "../hooks/useSystems";
import { useSession } from "../lib/session";
import { setSessionAuthProvider } from "../lib/sessionAuth";
import type { ProdConnection } from "../types/production";
import { Button, Card, EmptyState } from "../ui";

const MINTED_KINDS = new Set(["logs", "sentry"]);

function kindLabel(conn: ProdConnection): string {
  if (conn.kind === "logs") {
    const service = conn.config["service"];
    return typeof service === "string" && service
      ? `Logs · ${service}`
      : "Logs";
  }
  if (conn.kind === "sentry") return "Sentry webhook";
  if (conn.kind === "github") return "GitHub";
  if (conn.kind === "railway") return "Railway";
  if (conn.kind === "webhook") return "Deploy webhook";
  return conn.kind;
}

function lastSeenLabel(epochSeconds: number): string {
  if (!epochSeconds) return "never seen";
  return new Date(epochSeconds * 1000).toLocaleString();
}

function KeyRow({
  conn,
  onRotated,
}: {
  conn: ProdConnection;
  onRotated: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const mintable = MINTED_KINDS.has(conn.kind);

  async function rotate() {
    setBusy(true);
    setError(null);
    try {
      const created = await rotateConnection(conn);
      setNewKey(created.key ?? null);
      setConfirming(false);
      onRotated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rotate failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-lg border border-border bg-surface-2 px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-sm font-medium text-text">
          {kindLabel(conn)}
        </span>
        <span className="font-mono text-xs text-text-faint">
          {conn.secret_hint || "no key stored"}
        </span>
        <span className="text-xs text-text-muted">
          · {conn.status} · {lastSeenLabel(conn.last_seen)}
        </span>
        <span className="inline-flex gap-2">
          {mintable ? (
            confirming ? (
              <>
                <Button tone="primary" disabled={busy} onClick={rotate}>
                  {busy ? "Rotating…" : "Confirm rotate"}
                </Button>
                <Button tone="ghost" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              </>
            ) : (
              <Button tone="primary" onClick={() => setConfirming(true)}>
                Rotate key
              </Button>
            )
          ) : (
            <Link
              href={`/connect?system=${encodeURIComponent(conn.system_id)}`}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
            >
              Manage in Connections
            </Link>
          )}
        </span>
      </div>
      {mintable && confirming && !newKey && (
        <p className="mt-1 text-xs text-warn">
          The old key dies at once — update your forwarders after rotating.
        </p>
      )}
      {error && (
        <p className="mt-1 text-xs text-crit" role="alert">
          {error}
        </p>
      )}
      {newKey && (
        <div className="mt-2">
          <KeyOnce value={newKey} />
        </div>
      )}
    </li>
  );
}

export default function KeysPage() {
  const { getSessionAuth, status } = useSession();
  const { systems, systemsLoaded } = useSystems();
  const [conns, setConns] = useState<Record<string, ProdConnection[]>>({});
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setSessionAuthProvider(getSessionAuth);
  }, [getSessionAuth]);

  useEffect(() => {
    if (status !== "signed-in" || !systemsLoaded) return;
    let cancelled = false;
    (async () => {
      try {
        const entries = await Promise.all(
          systems.map(async (system) => {
            const list = await listConnections(system.system_id);
            return [system.system_id, list] as const;
          }),
        );
        if (!cancelled) setConns(Object.fromEntries(entries));
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, systemsLoaded, systems]);

  async function refreshSystem(systemId: string) {
    try {
      const list = await listConnections(systemId);
      setConns((prev) => ({ ...prev, [systemId]: list }));
    } catch {
      // The new key already shows; the list refreshes next visit.
    }
  }

  return (
    <RequireAuth>
      <AccountChrome>
        <main className="mx-auto flex w-full max-w-3xl flex-col gap-3 px-4 py-8">
          <div>
            <h1 className="text-xl font-semibold text-text">Keys</h1>
            <p className="mt-1 text-sm text-text-muted">
              Keys are shown once when created — old values can&apos;t be
              displayed again. Match yours by the ****last4 hint, or
              rotate for a new key.
            </p>
          </div>

          {!systemsLoaded ? (
            <p className="text-sm text-text-muted">Loading…</p>
          ) : failed ? (
            <p className="text-sm text-text-muted">
              Couldn&apos;t load keys — the API may be waking up.
            </p>
          ) : systems.length === 0 ? (
            <EmptyState
              title="No systems yet"
              hint="Connect a system first — its keys land here."
            />
          ) : (
            systems.map((system) => {
              const list = (conns[system.system_id] ?? []).filter(
                (c) => c.kind !== "device",
              );
              return (
                <Card key={system.system_id} title={system.name}>
                  {list.length === 0 ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm text-text-muted">
                        No keys on this system yet.
                      </p>
                      <Link
                        href={`/connect?resume=${encodeURIComponent(system.system_id)}`}
                        className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
                      >
                        Connect logs
                      </Link>
                    </div>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {list.map((conn) => (
                        <KeyRow
                          key={conn.id}
                          conn={conn}
                          onRotated={() => refreshSystem(system.system_id)}
                        />
                      ))}
                    </ul>
                  )}
                </Card>
              );
            })
          )}
        </main>
      </AccountChrome>
    </RequireAuth>
  );
}
