// /connect evidence steps: logs, repo, hosting, device (N-R4).
"use client";

import { useState } from "react";
import { apiUrl } from "../lib/api";
import { Card, StatusDot } from "../ui";
import { createConnection, testConnection } from "./api";
import type { ConnectionTest, ProdConnection } from "../types/production";
import { useConnectionLive } from "./useConnectionLive";
import {
  CodeBlock,
  ErrorLine,
  Field,
  KeyOnce,
  StepNav,
  WaitRow,
  inputCls,
} from "./ui";

function TestResult({ result }: { result: ConnectionTest | null }) {
  if (!result) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-[13px]">
      <StatusDot tone={result.ok ? "ok" : "crit"} label="test result" />
      <span className={result.ok ? "text-text" : "text-crit"}>
        {result.ok ? "✓" : "✗"} {result.detail || (result.ok ? "ok" : "failed")}
      </span>
      {result.permissions && (
        <span className="text-xs text-text-muted">
          read {result.permissions.read ? "✓" : "✗"} · pull requests{" "}
          {result.permissions.pull_requests ? "✓" : "✗"}
        </span>
      )}
    </div>
  );
}

export function StepLogs({
  num,
  systemId,
  onDone,
  onBack,
}: {
  num: number;
  systemId: string;
  onDone: (logsId: string | null, sentryId: string | null) => void;
  onBack: () => void;
}) {
  const [service, setService] = useState("api");
  const [logs, setLogs] = useState<ProdConnection | null>(null);
  const [logsKey, setLogsKey] = useState<string | null>(null);
  const [sentry, setSentry] = useState<ProdConnection | null>(null);
  const [sentryKey, setSentryKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { flips, live, recheck } = useConnectionLive(systemId);
  const firstLog = Boolean(
    (logs && flips[logs.id]?.status === "ok") ||
      (sentry && flips[sentry.id]?.status === "ok"),
  );

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const created = await createConnection({
        system_id: systemId,
        kind: "logs",
        config: { service },
      });
      setLogs(created.connection);
      setLogsKey(created.key ?? null);
      const sentryCreated = await createConnection({
        system_id: systemId,
        kind: "sentry",
        config: {},
      });
      setSentry(sentryCreated.connection);
      setSentryKey(sentryCreated.key ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect.");
    } finally {
      setBusy(false);
    }
  }

  const oneLiner =
    logsKey == null
      ? ""
      : `curl -sSL ${apiUrl}/forwarder.py -o ta_forward.py && python3 ta_forward.py --api ${apiUrl} --key ${logsKey} --file /var/log/myapp/app.log --service ${service}`;
  const curlExample =
    logsKey == null
      ? ""
      : `curl -X POST ${apiUrl}/api/ingest/logs -H "Authorization: Bearer ${logsKey}" -H "Content-Type: application/json" -d '{"service":"${service}","lines":[{"message":"Traceback (most recent call last): ..."}]}'`;

  return (
    <Card title={`Step ${num} · Logs`}>
      <div className="space-y-3">
        <Field label="Service name" hint="Tags every ingested line.">
          <input
            className={inputCls}
            value={service}
            disabled={logs != null || busy}
            onChange={(e) => setService(e.target.value)}
          />
        </Field>
        {logs == null ? (
          <StepNav
            onBack={onBack}
            onNext={connect}
            nextLabel={busy ? "Connecting…" : "Connect logs"}
            nextDisabled={busy || service.trim() === ""}
          />
        ) : (
          <>
            <KeyOnce value={logsKey} />
            <CodeBlock text={oneLiner} label="Forwarder one-liner" />
            <CodeBlock text={curlExample} label="…or a single error via curl" />
            {sentryKey && (
              <CodeBlock
                text={`${apiUrl}/api/ingest/sentry/${sentryKey}`}
                label="Sentry issue-alert webhook URL"
              />
            )}
            <WaitRow
              waitingLabel="Waiting for the first log…"
              doneLabel="first log"
              done={firstLog}
              detail=""
              live={live}
              onRecheck={recheck}
              onSkip={() => onDone(logs.id, sentry?.id ?? null)}
            />
            <StepNav
              onBack={onBack}
              onNext={() => onDone(logs.id, sentry?.id ?? null)}
            />
          </>
        )}
        <ErrorLine message={error} />
      </div>
    </Card>
  );
}

export function StepRepo({
  num,
  systemId,
  onDone,
  onBack,
}: {
  num: number;
  systemId: string;
  onDone: (
    repoId: string,
    perms: { read: boolean; pull_requests: boolean } | null,
  ) => void;
  onBack: () => void;
}) {
  const [repo, setRepo] = useState("");
  const [baseBranch, setBaseBranch] = useState("");
  const [token, setToken] = useState("");
  const [conn, setConn] = useState<ProdConnection | null>(null);
  const [result, setResult] = useState<ConnectionTest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connectAndTest() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const created = await createConnection({
        system_id: systemId,
        kind: "github",
        config: { repo: repo.trim(), base_branch: baseBranch.trim() },
        secret: token,
      });
      setConn(created.connection);
      const tested = await testConnection(created.connection.id);
      setResult(tested);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect.");
    } finally {
      setBusy(false);
    }
  }

  async function retest() {
    if (!conn) return;
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

  return (
    <Card title={`Step ${num} · Repo`}>
      <div className="space-y-3">
        <Field label="Repository" hint="owner/name on GitHub.">
          <input
            className={inputCls}
            value={repo}
            disabled={conn != null || busy}
            placeholder="acme/api"
            onChange={(e) => setRepo(e.target.value)}
          />
        </Field>
        <Field label="Base branch" hint="Empty means the default branch.">
          <input
            className={inputCls}
            value={baseBranch}
            disabled={conn != null || busy}
            placeholder="main"
            onChange={(e) => setBaseBranch(e.target.value)}
          />
        </Field>
        <Field label="GitHub token" hint="Needs contents:read; PRs need more.">
          <input
            className={inputCls}
            type="password"
            autoComplete="off"
            value={token}
            disabled={conn != null || busy}
            onChange={(e) => setToken(e.target.value)}
          />
        </Field>
        {conn == null ? (
          <StepNav
            onBack={onBack}
            onNext={connectAndTest}
            nextLabel={busy ? "Connecting…" : "Connect + Test"}
            nextDisabled={busy || repo.trim() === "" || token === ""}
          />
        ) : (
          <>
            <TestResult result={result} />
            <div className="flex items-center gap-2">
              <StepNav
                onBack={onBack}
                onNext={() =>
                  onDone(conn.id, result?.permissions ?? null)
                }
              />
              <button
                type="button"
                onClick={retest}
                disabled={busy}
                className="cursor-pointer text-[13px] font-medium text-brand hover:underline disabled:opacity-50"
              >
                Re-test
              </button>
            </div>
          </>
        )}
        <ErrorLine message={error} />
      </div>
    </Card>
  );
}

export function StepHosting({
  num,
  systemId,
  onDone,
  onBack,
}: {
  num: number;
  systemId: string;
  onDone: (hostingId: string, kind: string) => void;
  onBack: () => void;
}) {
  const [choice, setChoice] = useState<"railway" | "webhook">("railway");
  const [token, setToken] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [conn, setConn] = useState<ProdConnection | null>(null);
  const [result, setResult] = useState<ConnectionTest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready =
    choice === "railway"
      ? token !== "" && serviceId.trim() !== ""
      : url.trim() !== "" && secret !== "";

  async function connectAndTest() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const created = await createConnection({
        system_id: systemId,
        kind: choice,
        config:
          choice === "webhook"
            ? { url: url.trim() }
            : { service_id: serviceId.trim() },
        secret: choice === "railway" ? token : secret,
      });
      setConn(created.connection);
      setResult(await testConnection(created.connection.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title={`Step ${num} · Hosting`}>
      <div className="space-y-3">
        <div className="flex gap-4 text-sm text-text">
          {(["railway", "webhook"] as const).map((kind) => (
            <label key={kind} className="inline-flex items-center gap-1.5">
              <input
                type="radio"
                name="hosting"
                checked={choice === kind}
                disabled={conn != null || busy}
                onChange={() => setChoice(kind)}
              />
              {kind === "railway" ? "Railway" : "Webhook"}
            </label>
          ))}
        </div>
        {choice === "railway" ? (
          <>
            <Field
              label="Railway API token"
              hint="Account or workspace token from railway.com/account/tokens."
            >
              <input
                className={inputCls}
                type="password"
                autoComplete="off"
                value={token}
                disabled={conn != null || busy}
                onChange={(e) => setToken(e.target.value)}
              />
            </Field>
            <Field
              label="Railway service ID"
              hint="The service to roll back: service → Settings, or `railway status --json`."
            >
              <input
                className={inputCls}
                value={serviceId}
                disabled={conn != null || busy}
                placeholder="778a4768-…"
                onChange={(e) => setServiceId(e.target.value)}
              />
            </Field>
          </>
        ) : (
          <>
            <Field label="Deploy webhook URL">
              <input
                className={inputCls}
                value={url}
                disabled={conn != null || busy}
                placeholder="https://…/deploy"
                onChange={(e) => setUrl(e.target.value)}
              />
            </Field>
            <Field label="Webhook secret" hint="Sent as the auth header.">
              <input
                className={inputCls}
                type="password"
                autoComplete="off"
                value={secret}
                disabled={conn != null || busy}
                onChange={(e) => setSecret(e.target.value)}
              />
            </Field>
          </>
        )}
        {conn == null ? (
          <StepNav
            onBack={onBack}
            onNext={connectAndTest}
            nextLabel={busy ? "Testing…" : "Connect + Test ping"}
            nextDisabled={busy || !ready}
          />
        ) : (
          <>
            <TestResult result={result} />
            <StepNav
              onBack={onBack}
              onNext={() => onDone(conn.id, choice)}
            />
          </>
        )}
        <ErrorLine message={error} />
      </div>
    </Card>
  );
}

export function StepDevice({
  num,
  systemId,
  onDone,
  onBack,
}: {
  num: number;
  systemId: string;
  onDone: (deviceId: string, connId: string) => void;
  onBack: () => void;
}) {
  const [deviceId, setDeviceId] = useState("");
  const [conn, setConn] = useState<ProdConnection | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { flips, live, recheck } = useConnectionLive(systemId);
  const firstReading = conn != null && flips[conn.id]?.status === "ok";

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const created = await createConnection({
        system_id: systemId,
        kind: "device",
        config: { device_id: deviceId.trim() },
      });
      setConn(created.connection);
      setKey(created.key ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect.");
    } finally {
      setBusy(false);
    }
  }

  const snippet =
    key == null
      ? ""
      : `#define API_BASE "${apiUrl}"\n#define DEVICE_ID "${deviceId.trim()}"\n#define DEVICE_KEY "${key}"`;
  const simLine =
    key == null
      ? ""
      : `python3 hardware/sim_device.py --api ${apiUrl} --device ${deviceId.trim()} --key ${key} --fault door_open`;
  const curlExample =
    key == null
      ? ""
      : `curl -X POST ${apiUrl}/api/devices/${deviceId.trim()}/readings -H "Authorization: Bearer ${key}" -H "Content-Type: application/json" -d '{"appliance_type":"fridge","temperature_c":3.5,"current_a":1.2,"vibration_g":0.02,"door_open":false}'`;

  return (
    <Card title={`Step ${num} · Device`}>
      <div className="space-y-3">
        <Field label="Device id" hint="Must match DEVICE_ID in the firmware.">
          <input
            className={inputCls}
            value={deviceId}
            disabled={conn != null || busy}
            placeholder="fridge-01"
            onChange={(e) => setDeviceId(e.target.value)}
          />
        </Field>
        {conn == null ? (
          <StepNav
            onBack={onBack}
            onNext={connect}
            nextLabel={busy ? "Connecting…" : "Create device key"}
            nextDisabled={busy || deviceId.trim() === ""}
          />
        ) : (
          <>
            <KeyOnce value={key} />
            <CodeBlock text={snippet} label="Firmware snippet (sketch.ino)" />
            <CodeBlock text={simLine} label="…or prove it with the simulator" />
            <CodeBlock text={curlExample} label="…or a single reading via curl" />
            <WaitRow
              waitingLabel="Waiting for the first reading…"
              doneLabel="first reading"
              done={firstReading}
              detail=""
              live={live}
              onRecheck={recheck}
              onSkip={() => onDone(deviceId.trim(), conn.id)}
            />
            <StepNav
              onBack={onBack}
              onNext={() => onDone(deviceId.trim(), conn.id)}
            />
          </>
        )}
        <ErrorLine message={error} />
      </div>
    </Card>
  );
}
