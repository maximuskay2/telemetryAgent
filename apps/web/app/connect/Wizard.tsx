// /connect guided wizard (N-R4). Software and appliance paths share the
// shell; each path numbers its own steps sequentially.
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import {
  armSystem,
  confirmProfile,
  getProfile,
  putProfile,
  type SetupProfile,
} from "../lib/setupApi";
import { Card } from "../ui";
import { createSystem, pairingUrl } from "./api";
import { StepDevice, StepHosting, StepLogs, StepRepo } from "./ConnSteps";
import {
  ErrorLine,
  Field,
  StepNav,
  inputCls,
} from "./ui";

type Kind = "software" | "appliance";

type WizardData = {
  systemId: string;
  kind: Kind;
  name: string;
  repoPerms: { read: boolean; pull_requests: boolean } | null;
  hostingKind: string | null;
};

function StepName({
  num,
  onCreated,
}: {
  num: number;
  onCreated: (systemId: string, kind: Kind, name: string) => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Kind>("software");
  const [applianceType, setApplianceType] = useState<"fridge" | "freezer">(
    "fridge",
  );
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const system = await createSystem({
        name: name.trim(),
        kind,
        appliance_type: kind === "appliance" ? applianceType : undefined,
        owner_contact: contact.trim() || undefined,
      });
      // Production systems carry environment.mode = "production"; the demo
      // path never sets it, so the two can never mix (R-3).
      const { profile } = await getProfile(system.system_id);
      await putProfile(system.system_id, {
        ...profile,
        environment: { ...(profile.environment ?? {}), mode: "production" },
      });
      onCreated(system.system_id, kind, name.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title={`Step ${num} · Your system`}>
      <div className="space-y-3">
        <Field label="Name" hint="e.g. Shop API, Cold store B.">
          <input
            className={inputCls}
            value={name}
            disabled={busy}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <div className="flex gap-4 text-sm text-text">
          {(["software", "appliance"] as const).map((k) => (
            <label key={k} className="inline-flex items-center gap-1.5">
              <input
                type="radio"
                name="kind"
                checked={kind === k}
                disabled={busy}
                onChange={() => setKind(k)}
              />
              {k === "software" ? "Software" : "Appliance"}
            </label>
          ))}
        </div>
        {kind === "appliance" && (
          <div className="flex gap-4 text-sm text-text">
            {(["fridge", "freezer"] as const).map((t) => (
              <label key={t} className="inline-flex items-center gap-1.5">
                <input
                  type="radio"
                  name="appliance_type"
                  checked={applianceType === t}
                  disabled={busy}
                  onChange={() => setApplianceType(t)}
                />
                {t === "fridge" ? "Fridge" : "Freezer"}
              </label>
            ))}
          </div>
        )}
        <Field label="Owner contact" hint="Who gets the alert. Optional.">
          <input
            className={inputCls}
            value={contact}
            disabled={busy}
            placeholder="+15550001111"
            onChange={(e) => setContact(e.target.value)}
          />
        </Field>
        <StepNav
          onNext={create}
          nextLabel={busy ? "Creating…" : "Create system"}
          nextDisabled={busy || name.trim() === ""}
        />
        <ErrorLine message={error} />
      </div>
    </Card>
  );
}

type LimitRow = { metric: string; op: string; threshold: string };

function StepTeach({
  num,
  systemId,
  onDone,
  onBack,
}: {
  num: number;
  systemId: string;
  onDone: () => void;
  onBack: () => void;
}) {
  const [profile, setProfile] = useState<SetupProfile | null>(null);
  const [contact, setContact] = useState("");
  const [rows, setRows] = useState<LimitRow[]>([]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getProfile(systemId).then(
      (envelope) => {
        if (cancelled) return;
        const p = envelope.profile;
        setProfile(p);
        setContact(p.owner_contact ?? "");
        setRows(
          (p.hard_limits ?? []).map((l) => ({
            metric: String(l["metric"] ?? ""),
            op: String(l["op"] ?? ">"),
            threshold: String(l["threshold"] ?? ""),
          })),
        );
        setStatus(p.status);
      },
      (err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load.");
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [systemId]);

  async function save() {
    if (!profile) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await putProfile(systemId, {
        ...profile,
        owner_contact: contact,
        hard_limits: rows
          .filter((r) => r.metric.trim() !== "" && r.threshold.trim() !== "")
          .map((r) => ({
            metric: r.metric.trim(),
            op: r.op,
            threshold: Number(r.threshold),
            provenance: { source_doc: "manual" },
          })),
      });
      setProfile(saved);
      setStatus(saved.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmAndArm() {
    setBusy(true);
    setError(null);
    try {
      await confirmProfile(systemId, contact.trim() || "owner", []);
      const armed = await armSystem(systemId);
      setStatus(armed.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not arm.");
    } finally {
      setBusy(false);
    }
  }

  function patchRow(index: number, patch: Partial<LimitRow>) {
    setRows((prev) =>
      prev.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  }

  return (
    <Card title={`Step ${num} · Teach normal`}>
      <div className="space-y-3">
        <p className="text-[13px] text-text-muted">
          Status: <span className="font-medium text-text">{status || "…"}</span>
        </p>
        <Field label="Owner contact">
          <input
            className={inputCls}
            value={contact}
            disabled={busy || !profile}
            onChange={(e) => setContact(e.target.value)}
          />
        </Field>
        <div className="space-y-2">
          <p className="text-[13px] font-medium text-text">Hard limits</p>
          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                className={inputCls + " mt-0"}
                placeholder="temp_c"
                value={row.metric}
                disabled={busy}
                onChange={(e) => patchRow(i, { metric: e.target.value })}
              />
              <select
                className={inputCls + " mt-0 max-w-20"}
                value={row.op}
                disabled={busy}
                onChange={(e) => patchRow(i, { op: e.target.value })}
              >
                {[">", "<", ">=", "<=", "=="].map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>
              <input
                className={inputCls + " mt-0"}
                placeholder="8"
                inputMode="decimal"
                value={row.threshold}
                disabled={busy}
                onChange={(e) => patchRow(i, { threshold: e.target.value })}
              />
              <button
                type="button"
                disabled={busy}
                onClick={() => setRows((prev) => prev.filter((_, j) => j !== i))}
                className="cursor-pointer px-1 text-text-faint hover:text-crit disabled:opacity-50"
                aria-label="Remove limit"
              >
                ✕
              </button>
            </div>
          ))}
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              setRows((prev) => [...prev, { metric: "", op: ">", threshold: "" }])
            }
            className="cursor-pointer text-[13px] font-medium text-brand hover:underline disabled:opacity-50"
          >
            + Add limit
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StepNav onBack={onBack} onNext={onDone} />
          <button
            type="button"
            disabled={busy || !profile}
            onClick={save}
            className="cursor-pointer rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[13px] font-medium text-text hover:bg-surface-2/70 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            disabled={busy || !profile}
            onClick={confirmAndArm}
            className="cursor-pointer rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[13px] font-medium text-text hover:bg-surface-2/70 disabled:opacity-50"
          >
            {busy ? "Arming…" : "Confirm + Arm"}
          </button>
        </div>
        <ErrorLine message={error} />
      </div>
    </Card>
  );
}

const PROMISE: string[] = [
  "Local fix first — software bugs are patched in a sandbox, never live.",
  "Fail → pass, not maybe — a fix only ships when the new test fails without it and passes with it, and the suite reports no new failures.",
  "No blast radius — the rollback/restart allowlist is exactly rollback and restart; nothing else can ever run.",
  "Cooldown and confirmation — at most one rollback per customer per 12 h (a second needs human approval); a rollback only fires when the same error repeats 3 times in 10 minutes; a proposed rollback shows Cancel for 20 s and can be taken back while the window is open.",
  "Your normal, your veto — the agent learned normal from your documents, you approved the setup before anything armed; while learning, observability only, no mitigations.",
  "Pause in one tap — the app and the web show a Paused banner; paused → nothing runs.",
  "Humans for the risky rest — PRs open for review instead of merging; hardware offers safe remote options and turns the rest into technician work orders.",
  "Never the demo — production and demo code paths never mix; the demo is untouched.",
];

function StepPromise({
  num,
  grants,
  onDone,
  onBack,
}: {
  num: number;
  grants: string[];
  onDone: () => void;
  onBack: () => void;
}) {
  const [understood, setUnderstood] = useState(false);
  return (
    <Card title={`Step ${num} · The uptime promise`}>
      <div className="space-y-3">
        {grants.length > 0 && (
          <div>
            <p className="text-[13px] font-medium text-text">
              Connected with
            </p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[13px] text-text-muted">
              {grants.map((grant) => (
                <li key={grant}>{grant}</li>
              ))}
            </ul>
          </div>
        )}
        <ul className="list-disc space-y-1.5 pl-5 text-[13px] text-text">
          {PROMISE.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <label className="flex items-center gap-2 text-sm text-text">
          <input
            type="checkbox"
            checked={understood}
            onChange={(e) => setUnderstood(e.target.checked)}
          />
          I understand — watch my production.
        </label>
        <StepNav
          onBack={onBack}
          onNext={onDone}
          nextDisabled={!understood}
        />
      </div>
    </Card>
  );
}

function StepPair({
  num,
  onDone,
  onBack,
}: {
  num: number;
  onDone: () => void;
  onBack: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    pairingUrl().then(
      (value) => {
        if (!cancelled) setUrl(value);
      },
      (err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Pairing failed.");
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card title={`Step ${num} · Pair your phone`}>
      <div className="space-y-3">
        {url ? (
          <>
            <QRCodeSVG value={JSON.stringify({ api: url })} size={160} />
            <p className="font-mono text-xs break-all text-text-muted">{url}</p>
            <p className="text-[13px] text-text-muted">
              Same Wi-Fi, then type the mobile token from .env into the app.
            </p>
          </>
        ) : (
          <p className="text-[13px] text-text-muted">
            {error ?? "Preparing the pairing code…"}
          </p>
        )}
        <ErrorLine message={error} />
        <StepNav onBack={onBack} onNext={onDone} nextLabel="Start watching" />
      </div>
    </Card>
  );
}

function StepDone({ data }: { data: WizardData }) {
  return (
    <Card title="Watching ✓">
      <div className="space-y-3">
        <p className="text-sm text-text">
          <span className="font-mono">{data.name}</span> ({data.systemId}) is
          connected. Incidents will page the paired phone and open here.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/mission"
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-[#0b1710] hover:bg-brand/90"
          >
            Open Mission Control →
          </Link>
          <Link
            href={`/connect?system=${encodeURIComponent(data.systemId)}`}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-text hover:bg-surface-2/70"
          >
            Review connections
          </Link>
        </div>
      </div>
    </Card>
  );
}

const SOFTWARE_TITLES = [
  "System",
  "Logs",
  "Repo",
  "Hosting",
  "Teach",
  "Promise",
  "Pair",
  "Start",
];

const APPLIANCE_TITLES = ["System", "Device", "Teach", "Promise", "Pair", "Start"];

export default function Wizard() {
  const [index, setIndex] = useState(0);
  const [data, setData] = useState<WizardData | null>(null);
  const kind = data?.kind ?? "software";
  const titles = kind === "software" ? SOFTWARE_TITLES : APPLIANCE_TITLES;
  const num = index + 1;
  const back = () => setIndex((i) => Math.max(0, i - 1));
  const next = () => setIndex((i) => Math.min(titles.length - 1, i + 1));

  function grants(): string[] {
    const list: string[] = [];
    if (data?.repoPerms) {
      list.push(
        `GitHub repo (read ${data.repoPerms.read ? "✓" : "✗"}, pull requests ${
          data.repoPerms.pull_requests ? "✓" : "✗"
        })`,
      );
    }
    if (data?.hostingKind) list.push(`Hosting: ${data.hostingKind}`);
    return list;
  }

  return (
    <div className="space-y-4">
      <ol className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {titles.map((title, i) => (
          <li
            key={title}
            className={
              i === index
                ? "font-semibold text-text"
                : i < index
                  ? "text-text-muted"
                  : "text-text-faint"
            }
          >
            {i + 1}. {title}
          </li>
        ))}
      </ol>
      {index === 0 && (
        <StepName
          num={num}
          onCreated={(systemId, createdKind, name) => {
            setData({
              systemId,
              kind: createdKind,
              name,
              repoPerms: null,
              hostingKind: null,
            });
            next();
          }}
        />
      )}
      {data != null && kind === "software" && index === 1 && (
        <StepLogs
          num={num}
          systemId={data.systemId}
          onBack={back}
          onDone={() => next()}
        />
      )}
      {data != null && kind === "software" && index === 2 && (
        <StepRepo
          num={num}
          systemId={data.systemId}
          onBack={back}
          onDone={(_repoId, perms) => {
            setData({ ...data, repoPerms: perms });
            next();
          }}
        />
      )}
      {data != null && kind === "software" && index === 3 && (
        <StepHosting
          num={num}
          systemId={data.systemId}
          onBack={back}
          onDone={(_hostingId, hostingKind) => {
            setData({ ...data, hostingKind });
            next();
          }}
        />
      )}
      {data != null && kind === "appliance" && index === 1 && (
        <StepDevice
          num={num}
          systemId={data.systemId}
          onBack={back}
          onDone={() => next()}
        />
      )}
      {data != null &&
        index === titles.indexOf("Teach") && (
          <StepTeach
            num={num}
            systemId={data.systemId}
            onBack={back}
            onDone={next}
          />
        )}
      {data != null && index === titles.indexOf("Promise") && (
        <StepPromise num={num} grants={grants()} onBack={back} onDone={next} />
      )}
      {data != null && index === titles.indexOf("Pair") && (
        <StepPair num={num} onBack={back} onDone={next} />
      )}
      {data != null && index === titles.indexOf("Start") && (
        <StepDone data={data} />
      )}
    </div>
  );
}
