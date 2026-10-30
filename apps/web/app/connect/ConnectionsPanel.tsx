// Connections panel: /connect?system=… (N-R4). Last seen, test, rotate
// key, disconnect per connection.
"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, EmptyState } from "../ui";
import {
  deleteConnection,
  listConnections,
  rotateConnection,
  testConnection,
} from "./api";
import type { ConnectionTest, ProdConnection } from "../types/production";
import { useConnectionLive } from "./useConnectionLive";
import { ErrorLine, inputCls } from "./ui";

const PASTED_SECRET_KINDS = ["github", "railway", "webhook"];

function lastSeen(ts: number): string {
  if (!ts) return "never";
  return new Date(ts * 1000).toLocaleString();
}

function statusTone(status: string): "ok" | "warn" | "crit" {
  if (status === "ok") return "ok";
  if (status === "error") return "crit";
  return "warn";
}

function Row({
  conn,
  liveStatus,
  onChanged,
}: {
  conn: ProdConnection;
  liveStatus: string | null;
  onChanged: () => void;
}) {
  const [result, setResult] = useState<ConnectionTest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<"rotate" | "delete" | null>(
    null,
  );
  const [secret, setSecret] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const needsSecret = PASTED_SECRET_KINDS.includes(conn.kind);
  const status = liveStatus ?? conn.status;

  async function test() {
    setBusy(true);
    setError(null);
    try {
      setResult(await testConnection(conn.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed.");
    } finally {
      setBusy(false);
    }
  }

  async function rotate() {
    if (needsSecret && secret.trim() === "") {
      setError("Paste the secret again to rotate.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await rotateConnection(
        conn,
        needsSecret ? secret : undefined,
      );
      setNewKey(created.key ?? null);
      setConfirming(null);
      setSecret("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rotate failed.");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    setError(null);
    try {
      await deleteConnection(conn.id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Disconnect failed.");
    } finally {
      setBusy(false);
      setConfirming(null);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-border bg-surface-2 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="font-mono text-[13px] font-medium text-text">
          {conn.kind}
        </span>
        <Badge tone={statusTone(status)}>{status}</Badge>
        <span className="font-mono text-xs text-text-faint">
          {conn.secret_hint || "no key"}
        </span>
        <span className="text-xs text-text-muted">
          last seen {lastSeen(conn.last_seen)}
        </span>
        {conn.detail && (
          <span className="text-xs text-text-faint">{conn.detail}</span>
        )}
      </div>
      {result && (
        <p
          className={`text-[13px] ${result.ok ? "text-text" : "text-crit"}`}
        >
          {result.ok ? "✓" : "✗"} {result.detail || "done"}
        </p>
      )}
      {newKey && (
        <p className="font-mono text-xs break-all text-text">
          New key (shown once): {newKey}
        </p>
      )}
      <ErrorLine message={error} />
      {confirming == null ? (
        <div className="flex flex-wrap gap-2">
          <Button tone="secondary" disabled={busy} onClick={test}>
            Test
          </Button>
          <Button
            tone="secondary"
            disabled={busy}
            onClick={() => setConfirming("rotate")}
          >
            Rotate key
          </Button>
          <Button
            tone="danger"
            disabled={busy}
            onClick={() => setConfirming("delete")}
          >
            Disconnect
          </Button>
        </div>
      ) : confirming === "delete" ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] text-text">
            Delete this connection? Its key dies at once.
          </span>
          <Button tone="danger" disabled={busy} onClick={disconnect}>
            {busy ? "…" : "Yes, disconnect"}
          </Button>
          <Button
            tone="ghost"
            disabled={busy}
            onClick={() => setConfirming(null)}
          >
            Keep
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {needsSecret ? (
            <input
              className={inputCls + " mt-0 max-w-64"}
              type="password"
              autoComplete="off"
              placeholder="Paste the secret again"
              value={secret}
              disabled={busy}
              onChange={(e) => setSecret(e.target.value)}
            />
          ) : (
            <span className="text-[13px] text-text">
              Issue a new key? The old one dies at once.
            </span>
          )}
          <Button tone="primary" disabled={busy} onClick={rotate}>
            {busy ? "…" : "Rotate"}
          </Button>
          <Button
            tone="ghost"
            disabled={busy}
            onClick={() => {
              setConfirming(null);
              setSecret("");
            }}
          >
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}

export default function ConnectionsPanel({ systemId }: { systemId: string }) {
  const [conns, setConns] = useState<ProdConnection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { flips, live } = useConnectionLive(systemId);

  const refresh = useCallback(async () => {
    try {
      setConns(await listConnections(systemId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load.");
    }
  }, [systemId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold text-text">Connections</h2>
        <span className="font-mono text-xs text-text-faint">{systemId}</span>
        <span className="text-xs text-text-faint">
          {live ? "· live" : "· socket down"}
        </span>
        <Link
          href="/connect"
          className="text-[13px] font-medium text-brand hover:underline"
        >
          + Connect another system
        </Link>
      </div>
      {error && (
        <Card>
          <p className="text-[13px] text-crit">{error}</p>
        </Card>
      )}
      {conns == null ? (
        <p className="text-sm text-text-muted">Loading…</p>
      ) : conns.length === 0 ? (
        <EmptyState
          title="No connections yet"
          hint="Run the wizard to connect logs, repo, hosting, or a device."
        />
      ) : (
        <div className="space-y-2.5">
          {conns.map((conn) => (
            <Row
              key={conn.id}
              conn={conn}
              liveStatus={flips[conn.id]?.status ?? null}
              onChanged={refresh}
            />
          ))}
        </div>
      )}
    </div>
  );
}
