// /connect: guided wizard, or the connections panel with ?system=… (N-R4).
"use client";

import { Suspense, useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import AccountChrome from "../commerce/AccountChrome";
import RequireAuth from "../commerce/RequireAuth";
import { useSession } from "../lib/session";
import { Card } from "../ui";
import { checkAccessCode, getAccessCode, getConnectDoor } from "./api";
import ConnectionsPanel from "./ConnectionsPanel";
import { ErrorLine, Field, StepNav, inputCls } from "./ui";
import Wizard from "./Wizard";

type Door = "loading" | "off" | "code" | "open";

function AccessCodeForm({ onOpen }: { onOpen: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (await checkAccessCode(code.trim())) onOpen();
      else setError("That code didn't work.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not check.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Access code">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <p className="text-[13px] text-text-muted">
          Connecting real systems on this instance needs an access code. Ask
          the team running it. The live demo doesn&apos;t need one.
        </p>
        <Field label="Code">
          <input
            className={inputCls}
            type="password"
            autoComplete="off"
            value={code}
            disabled={busy}
            onChange={(e) => setCode(e.target.value)}
          />
        </Field>
        <StepNav
          onNext={submit}
          nextLabel={busy ? "Checking…" : "Continue"}
          nextDisabled={busy || code.trim() === ""}
        />
        <ErrorLine message={error} />
      </form>
    </Card>
  );
}

function ConnectDoor({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const [door, setDoor] = useState<Door>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const state = await getConnectDoor();
        if (!state.enabled) return "off" as Door;
        // Signed-in accounts skip the extra access-code door.
        if (status === "signed-in" || !state.codeRequired) return "open" as Door;
        const stored = getAccessCode();
        if (stored && (await checkAccessCode(stored))) return "open" as Door;
        return "code" as Door;
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "API unreachable.");
        }
        return "loading" as Door;
      }
    })().then((next) => {
      if (!cancelled) setDoor(next);
    });
    return () => {
      cancelled = true;
    };
  }, [status]);

  if (door === "off") {
    return (
      <Card title="Connecting is switched off">
        <p className="text-[13px] text-text-muted">
          This instance doesn&apos;t accept new connections right now. The live
          demo still works.
        </p>
      </Card>
    );
  }
  if (door === "code") return <AccessCodeForm onOpen={() => setDoor("open")} />;
  if (door === "loading") {
    return error ? (
      <ErrorLine message={error} />
    ) : (
      <p className="text-sm text-text-muted">Loading…</p>
    );
  }
  return <>{children}</>;
}

function ConnectInner() {
  const systemId = useSearchParams().get("system");
  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-8">
      <h1 className="mb-1 text-xl font-semibold text-text">
        {systemId ? "Connections" : "Connect your production"}
      </h1>
      <p className="mb-5 text-sm text-text-muted">
        {systemId
          ? "Keys stay server-side; secrets are never shown again."
          : "Eight steps, about ten minutes. Nothing arms until you say so."}
      </p>
      <ConnectDoor>
        {systemId ? <ConnectionsPanel systemId={systemId} /> : <Wizard />}
      </ConnectDoor>
    </main>
  );
}

export default function ConnectPage() {
  return (
    <RequireAuth>
      <AccountChrome>
        <Suspense
          fallback={
            <main className="mx-auto w-full max-w-2xl px-4 py-8">
              <p className="text-sm text-text-muted">Loading…</p>
            </main>
          }
        >
          <ConnectInner />
        </Suspense>
      </AccountChrome>
    </RequireAuth>
  );
}
