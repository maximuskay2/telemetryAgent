"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Card } from "../ui";
import { ReviewSection } from "./ReviewTable";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Provenance = {
  source_doc?: string;
  page_or_region?: string;
  quote?: string;
  confidence?: number;
  confirmed_by?: string;
  confirmed_at?: string;
};

type Profile = {
  system_id: string;
  name: string;
  kind: string;
  appliance_type?: string | null;
  owner_contact?: string;
  environment?: Record<string, string>;
  normal_ranges?: Record<string, unknown>[];
  expected_behaviours?: Record<string, unknown>[];
  modes?: Record<string, unknown>[];
  failure_definitions?: Record<string, unknown>[];
  hard_limits?: Record<string, unknown>[];
  policy?: {
    allowed_actions?: string[];
    forbidden_actions?: string[];
    auto_fix_allowed?: boolean;
    countdown_s?: number;
    alert_contacts?: string[];
  };
  baseline?: { status?: string };
  status: string;
  version: number;
};

type Conflict = {
  field: string;
  key: string;
  values: { doc?: string; value?: unknown; quote?: string }[];
};

type FeedbackItem = {
  id: string;
  fingerprint: string;
  signature: string;
  rule?: string;
  created_by?: string;
};

type Step = "connect" | "teach" | "review" | "learn" | "policy" | "arm";
const STEPS: Step[] = ["connect", "teach", "review", "learn", "policy", "arm"];
const STEP_LABELS: Record<Step, string> = {
  connect: "Meet the business",
  teach: "Read the manuals",
  review: "Check what it learned",
  learn: "Watch normal",
  policy: "Permissions",
  arm: "Start watching",
};

const inputCls =
  "w-full rounded-lg border border-border bg-surface-2 px-2 py-1.5 text-sm text-text outline-none placeholder:text-text-faint focus:border-brand";

async function api(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${apiUrl}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `API returned ${response.status}`);
  }
  return response.json() as Promise<unknown>;
}

function Field({
  label,
  value,
  onChange,
  type,
  locked,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  locked?: boolean;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-xs text-text-muted">
        {locked && (
          <span role="img" aria-label="Human-only" title="Human-only — the agent never changes this">
            🔒{" "}
          </span>
        )}
        {label}
      </span>
      <input
        type={type ?? "text"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={inputCls}
      />
    </label>
  );
}

function ProgressRing({ pct }: { pct: number }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Learning progress"
      className="relative inline-flex"
    >
      <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90">
        <circle cx="32" cy="32" r={r} fill="none" strokeWidth="7" className="stroke-border" />
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.min(100, pct) / 100)}
          className="stroke-brand-cyan"
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-mono text-xs tabular-nums text-text">
        {Math.round(pct)}%
      </span>
    </div>
  );
}

export default function SetupPage() {
  const [step, setStep] = useState<Step>("connect");
  const [systems, setSystems] = useState<Profile[]>([]);
  const [systemId, setSystemId] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [picks, setPicks] = useState<Record<string, number>>({});
  const [progress, setProgress] = useState("");
  const [learnPct, setLearnPct] = useState<number | null>(null);
  const [learnPatterns, setLearnPatterns] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // connect form
  const [name, setName] = useState("");
  const [kind, setKind] = useState("software");
  const [applianceType, setApplianceType] = useState("fridge");
  const [contact, setContact] = useState("");
  // teach form
  const [pasteName, setPasteName] = useState("owner-note.md");
  const [pasteText, setPasteText] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  // review form
  const [confirmedBy, setConfirmedBy] = useState("");
  const socketRef = useRef<WebSocket | null>(null);

  async function refreshSystems() {
    try {
      const body = (await api("/api/systems")) as { systems?: Profile[] };
      setSystems(body.systems ?? []);
    } catch {
      // API down; the wizard shows the error on action.
    }
  }

  async function loadProfile(id: string) {
    const body = (await api(`/api/systems/${id}/profile`)) as {
      profile?: Profile;
      conflicts?: Conflict[];
      feedback?: FeedbackItem[];
    };
    if (body.profile) setProfile(body.profile);
    setConflicts(body.conflicts ?? []);
    setFeedback(body.feedback ?? []);
    setPicks({});
  }

  useEffect(() => {
    refreshSystems();
    const params = new URLSearchParams(window.location.search);
    const id = params.get("system");
    if (id) {
      setSystemId(id);
      loadProfile(id).catch((err: Error) => setError(err.message));
      setStep("review");
    }
    const socket = new WebSocket(`${apiUrl.replace(/^http/, "ws")}/api/ws`);
    socketRef.current = socket;
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as {
          kind?: string;
          payload?: {
            system_id?: string;
            stage?: string;
            doc?: string;
            conflicts?: number;
            percent?: number;
            reason?: string;
          };
        };
        if (data.kind === "setup_progress" && data.payload) {
          const { stage, doc, conflicts: n } = data.payload;
          setProgress(
            [`setup: ${stage ?? "?"}`, doc ?? "", n ? `${n} conflict(s)` : ""]
              .filter(Boolean)
              .join(" · "),
          );
        } else if (data.kind === "baseline_progress" && data.payload) {
          const pct = data.payload.percent;
          const patterns = (
            data.payload as { patterns?: number }
          ).patterns;
          if (data.payload.stage === "blocked") {
            setError(
              data.payload.reason ??
                "Learning blocked; fix the cause and restart learning.",
            );
            setLearnPct(null);
            setLearnPatterns(null);
          } else {
            if (typeof pct === "number") setLearnPct(pct);
            if (typeof patterns === "number") setLearnPatterns(patterns);
          }
          if (data.payload.stage === "finished" && data.payload.system_id) {
            loadProfile(data.payload.system_id).catch(() => {});
          }
        }
      } catch {
        // ignore malformed frames
      }
    };
    return () => socket.close();
  }, []);

  // Poll the learning session while the bar is active: the socket normally
  // drives it, but a dropped socket must not leave the bar stuck at 0%.
  useEffect(() => {
    if (
      step !== "learn" ||
      !systemId ||
      learnPct === null ||
      learnPct >= 100
    ) {
      return;
    }
    let cancelled = false;
    const id = systemId;
    const tick = async () => {
      try {
        const body = (await api(`/api/systems/${id}/baseline`)) as {
          status?: string;
          session?: {
            percent?: number;
            patterns?: number;
            blocked?: boolean;
          } | null;
        };
        if (cancelled) return;
        if (body.session) {
          if (body.session.blocked) {
            setError(
              "A hard limit was hit during learning; restart learning.",
            );
            setLearnPct(null);
            setLearnPatterns(null);
            return;
          }
          const pct = body.session.percent;
          const patterns = body.session.patterns;
          if (typeof pct === "number") {
            setLearnPct((prev) =>
              prev === null ? prev : Math.max(prev, pct),
            );
          }
          if (typeof patterns === "number") {
            setLearnPatterns((prev) =>
              prev === null ? prev : Math.max(prev, patterns),
            );
          }
        } else if (body.status && body.status !== "learning") {
          setLearnPct(100);
          loadProfile(id).catch(() => {});
        } else {
          // Status says learning but the server holds no session (a restart
          // or a crashed run): say so instead of hanging at 0%.
          setError("Learning stalled (no active session); restart learning.");
          setLearnPct(null);
          setLearnPatterns(null);
        }
      } catch {
        // API down; the wizard shows the error on action.
      }
    };
    const timer = setInterval(tick, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [step, systemId, learnPct]);

  async function run(action: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  function updateSection(section: string, rows: Record<string, unknown>[]) {
    setProfile((prev) =>
      prev ? ({ ...prev, [section]: rows } as Profile) : prev,
    );
  }

  async function uploadDocuments() {
    await run(async () => {
      const data = new FormData();
      const chosen = fileRef.current?.files;
      if (chosen) {
        for (const file of Array.from(chosen)) {
          data.append("files", file, file.name);
        }
      }
      if (pasteText.trim()) {
        data.append(
          "files",
          new File([pasteText], pasteName || "note.md", {
            type: "text/markdown",
          }),
        );
      }
      const body = (await api(
        `/api/systems/${systemId}/documents`,
        { method: "POST", body: data },
      )) as {
        profile?: Profile;
        conflicts?: Conflict[];
        rejected?: string[];
        needs_manual?: string[];
      };
      if (body.profile) setProfile(body.profile);
      setConflicts(body.conflicts ?? []);
      const rejected = body.rejected ?? [];
      const manual = body.needs_manual ?? [];
      if (rejected.length > 0 || manual.length > 0) {
        setProgress(
          [
            rejected.length > 0
              ? `${rejected.length} value(s) skipped: ${rejected
                  .slice(0, 3)
                  .join(" | ")}${rejected.length > 3 ? " …" : ""}`
              : "",
            manual.length > 0
              ? `needs manual entry: ${manual.join(", ")}`
              : "",
          ]
            .filter(Boolean)
            .join(" · "),
        );
      } else {
        setProgress("");
      }
      setStep("review");
    });
  }

  async function startLearning() {
    await run(async () => {
      await api(`/api/systems/${systemId}/baseline/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_s: 120 }),
      });
      // Only show the bar once learning actually started;
      // a rejected start must show the error, not a stuck 0%.
      setLearnPct(0);
      setLearnPatterns(0);
    });
  }

  async function continueToPolicy() {
    await run(async () => {
      if (systemId) await loadProfile(systemId);
      setStep("policy");
    });
  }

  const current = systems.find((s) => s.system_id === systemId) ?? profile;
  const learning = learnPct !== null && learnPct < 100;
  // While a run is active the bar wins; otherwise fall back to the stored
  // baseline so a re-run doesn't keep showing "Continue" mid-learning.
  const learned =
    learnPct !== null
      ? learnPct >= 100
      : profile?.baseline?.status === "ready";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-3 bg-bg p-4 text-text">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold tracking-wide text-text-faint uppercase">
            Telemetry Agent / Advanced setup
          </p>
          <h1 className="text-xl font-semibold">Teach it normal</h1>
        </div>
        <nav aria-label="Demo navigation" className="flex items-center gap-2">
          <a
            href="/welcome"
            className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[13px] font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            ← Home
          </a>
          <a
            href="/"
            className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[13px] font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            ← Mission Control
          </a>
          <a
            href="/start"
            className="rounded-lg border border-brand/50 bg-brand/10 px-3 py-1.5 text-[13px] font-medium text-brand-cyan outline-none hover:bg-brand/20 focus-visible:ring-2 focus-visible:ring-brand"
          >
            Guided demo
          </a>
        </nav>
      </header>

      <nav aria-label="Setup steps" className="flex flex-wrap items-center gap-1">
        {STEPS.map((s, i) => {
          const active = s === step;
          const past = STEPS.indexOf(step) > i;
          return (
            <button
              key={s}
              type="button"
              onClick={() => setStep(s)}
              aria-current={active ? "step" : undefined}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-brand ${
                active
                  ? "bg-surface-2 text-text"
                  : past
                    ? "text-ok"
                    : "text-text-muted hover:bg-surface-2/60 hover:text-text"
              }`}
            >
              <span
                className={`flex size-4 items-center justify-center rounded-full font-mono text-[10px] ${
                  active
                    ? "bg-brand text-[#0b1710]"
                    : past
                      ? "bg-ok/20 text-ok"
                      : "bg-surface-2 text-text-faint"
                }`}
              >
                {past ? "✓" : i + 1}
              </span>
              {STEP_LABELS[s]}
            </button>
          );
        })}
      </nav>

      {systems.length > 0 && (
        <Card title="Pick up where you left off">
          <div className="flex flex-col gap-2">
            {systems.map((s) => (
              <div
                key={s.system_id}
                className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface-2/50 p-2"
              >
                <Button
                  tone={s.system_id === systemId ? "primary" : "ghost"}
                  onClick={() =>
                    run(async () => {
                      setSystemId(s.system_id);
                      await loadProfile(s.system_id);
                      setStep("review");
                    })
                  }
                >
                  {s.name} ·{" "}
                  {s.status === "armed"
                    ? "Watching"
                    : s.status === "learning"
                      ? "Watching normal"
                      : s.status === "confirmed"
                        ? "Ready"
                        : s.status}
                </Button>
                {s.status === "armed" && (
                  <Button
                    tone="ghost"
                    disabled={busy}
                    title="Stop watching; setup can run again"
                    onClick={() =>
                      run(async () => {
                        const body = (await api(
                          `/api/systems/${s.system_id}/disarm`,
                          { method: "POST" },
                        )) as Profile;
                        if (body.system_id === systemId) setProfile(body);
                        await refreshSystems();
                        setProgress(
                          `${s.name} stopped watching — check, watch and start it again below.`,
                        );
                        setStep("review");
                      })
                    }
                  >
                    Stop watching
                  </Button>
                )}
                <Button
                  tone="ghost"
                  disabled={busy}
                  title="Delete this system and everything setup stored for it"
                  onClick={() => {
                    if (
                      !window.confirm(
                        `Delete ${s.name} and everything setup stored for it (profile, baseline, uploads)? This cannot be undone.`,
                      )
                    ) {
                      return;
                    }
                    run(async () => {
                      await api(`/api/systems/${s.system_id}`, {
                        method: "DELETE",
                      });
                      if (s.system_id === systemId) {
                        setSystemId("");
                        setProfile(null);
                        setStep("connect");
                      }
                      await refreshSystems();
                      setProgress(`${s.name} deleted.`);
                    });
                  }}
                >
                  Delete
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {step === "connect" && (
        <Card title="Step 1 · What are we watching?">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field label="System name" value={name} onChange={setName} />
            <label className="flex min-w-0 flex-col gap-1">
              <span className="text-xs text-text-muted">System type</span>
              <select
                value={kind}
                onChange={(event) => setKind(event.target.value)}
                className={inputCls}
              >
                <option value="software">Software service</option>
                <option value="appliance">Cold-chain appliance</option>
              </select>
            </label>
            {kind === "appliance" && (
              <label className="flex min-w-0 flex-col gap-1">
                <span className="text-xs text-text-muted">Appliance</span>
                <select
                  value={applianceType}
                  onChange={(event) => setApplianceType(event.target.value)}
                  className={inputCls}
                >
                  <option value="fridge">Fridge</option>
                  <option value="freezer">Freezer</option>
                </select>
              </label>
            )}
            <Field
              label="Owner contact"
              locked
              value={contact}
              onChange={setContact}
            />
          </div>
          <div className="mt-3">
            <Button
              tone="primary"
              disabled={busy || !name.trim()}
              onClick={() =>
                run(async () => {
                  const body = (await api("/api/systems", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      name: name.trim(),
                      kind,
                      appliance_type:
                        kind === "appliance" ? applianceType : null,
                      owner_contact: contact.trim(),
                    }),
                  })) as Profile;
                  setSystemId(body.system_id);
                  setProfile(body);
                  await refreshSystems();
                  setStep("teach");
                })
              }
            >
              Create system
            </Button>
          </div>
        </Card>
      )}

      {step === "teach" && (
        <Card title={`Step 2 · Upload docs for ${current?.name ?? "…"}`}>
          <p className="text-sm text-text-muted">
            Spec PDFs, rating-plate photos, ops docs — or paste text. The
            agent quotes every value it takes and never guesses numbers.
          </p>
          <div
            role="button"
            tabIndex={0}
            aria-label="Drop documents here or browse"
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              if (fileRef.current && event.dataTransfer.files.length > 0) {
                fileRef.current.files = event.dataTransfer.files;
              }
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                fileRef.current?.click();
              }
            }}
            className={`mt-2 rounded-lg border border-dashed p-4 text-center outline-none focus-visible:ring-2 focus-visible:ring-brand ${
              dragging ? "border-brand bg-brand/10" : "border-border"
            }`}
          >
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.txt,.md"
              aria-label="Documents"
              className="mx-auto block text-xs text-text-muted"
            />
            <p className="mt-1 text-xs text-text-faint">
              Drag files here or browse — .pdf .png .jpg .txt .md
            </p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              tone="primary"
              disabled={busy || !systemId}
              onClick={() => uploadDocuments()}
            >
              Upload & extract
            </Button>
            <Button
              disabled={busy || !systemId}
              onClick={() =>
                run(async () => {
                  const sample =
                    profile?.kind === "appliance" ? "coldchain" : "shop";
                  const body = (await api(
                    `/api/systems/${systemId}/profile/sample`,
                    {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ sample }),
                    },
                  )) as Profile;
                  setProfile(body);
                  setStep("review");
                })
              }
            >
              Load sample profile
            </Button>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field
              label="Pasted note filename"
              value={pasteName}
              onChange={setPasteName}
            />
          </div>
          <textarea
            rows={5}
            placeholder="Or paste an owner note here…"
            value={pasteText}
            onChange={(event) => setPasteText(event.target.value)}
            aria-label="Pasted text"
            className={`${inputCls} mt-2 font-mono text-xs`}
          />
          {progress && (
            <p className="mt-2 rounded-lg border border-brand/40 bg-brand/10 p-2 text-xs text-brand-cyan">
              {progress}
            </p>
          )}
        </Card>
      )}

      {step === "review" && profile && (
        <>
          {conflicts.length > 0 && (
            <Card
              title="Check · Pick the true value"
              action={
                <span className="rounded-full bg-warn/15 px-2 py-0.5 font-mono text-[11px] tabular-nums text-warn">
                  {conflicts.length}
                </span>
              }
            >
              <div className="flex flex-col gap-2">
                {conflicts.map((conflict, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-warn/50 bg-warn/5 p-2.5"
                  >
                    <p className="text-sm font-semibold text-text">
                      {conflict.field}.{conflict.key}
                    </p>
                    {conflict.values.map((option, j) => (
                      <label
                        key={j}
                        className="mt-1.5 flex cursor-pointer items-start gap-2 rounded-md p-1 hover:bg-surface-2/60"
                      >
                        <input
                          type="radio"
                          name={`conflict-${i}`}
                          checked={
                            picks[`${conflict.field}:${conflict.key}`] === j
                          }
                          onChange={() =>
                            setPicks((prev) => ({
                              ...prev,
                              [`${conflict.field}:${conflict.key}`]: j,
                            }))
                          }
                          className="mt-1 accent-[#f3cf7e]"
                        />
                        <span className="text-xs">
                          <code className="rounded bg-surface-2 px-1 font-mono text-text">
                            {JSON.stringify(option.value, null, 0)}
                          </code>{" "}
                          <span className="text-text-faint">
                            {option.doc}
                            {option.quote ? ` — “${option.quote}”` : ""}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            </Card>
          )}
          {feedback.length > 0 && (
            <Card
              title="Check · Pending “this is normal” votes"
              action={
                <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[11px] tabular-nums text-text-muted">
                  {feedback.length}
                </span>
              }
            >
              <p className="text-xs text-text-muted">
                Confirming adds the signature as an expected behaviour.
                Hard limits can never be marked normal.
              </p>
              <div className="mt-2 flex flex-col gap-2">
                {feedback.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-lg border border-border bg-surface-2/50 p-2.5"
                  >
                    <p>
                      <code className="font-mono text-xs text-text">
                        {item.signature}
                      </code>
                    </p>
                    <p className="mt-0.5 text-xs text-text-faint">
                      {[item.rule, item.fingerprint, item.created_by]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <div className="mt-1.5 flex gap-2">
                      <Button
                        tone="ghost"
                        disabled={busy}
                        onClick={() =>
                          run(async () => {
                            const body = (await api(
                              `/api/systems/${systemId}/feedback/${item.id}/confirm`,
                              { method: "POST" },
                            )) as Profile;
                            setProfile(body);
                            setFeedback((prev) =>
                              prev.filter((entry) => entry.id !== item.id),
                            );
                          })
                        }
                      >
                        Confirm
                      </Button>
                      <Button
                        tone="ghost"
                        disabled={busy}
                        onClick={() =>
                          run(async () => {
                            await api(
                              `/api/systems/${systemId}/feedback/${item.id}`,
                              { method: "DELETE" },
                            );
                            setFeedback((prev) =>
                              prev.filter((entry) => entry.id !== item.id),
                            );
                          })
                        }
                      >
                        Reject
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          <ReviewSection
            title="Normal ranges"
            rows={profile.normal_ranges ?? []}
            fields={[
              { key: "metric", label: "Metric" },
              { key: "min", label: "Min", type: "number" },
              { key: "max", label: "Max", type: "number" },
              { key: "unit", label: "Unit" },
            ]}
            onChange={(rows) => updateSection("normal_ranges", rows)}
          />
          <ReviewSection
            title="Expected behaviours"
            rows={profile.expected_behaviours ?? []}
            fields={[
              { key: "name", label: "Name" },
              { key: "signature", label: "Signature" },
              { key: "schedule", label: "Schedule" },
              {
                key: "max_duration_s",
                label: "Max s",
                type: "number",
              },
              { key: "allowed_effect", label: "Allowed effect" },
            ]}
            onChange={(rows) => updateSection("expected_behaviours", rows)}
          />
          <ReviewSection
            title="Modes"
            rows={profile.modes ?? []}
            fields={[
              { key: "mode", label: "Mode" },
              {
                key: "max_duration_s",
                label: "Max s",
                type: "number",
              },
            ]}
            onChange={(rows) => updateSection("modes", rows)}
          />
          <ReviewSection
            title="Failure definitions"
            rows={profile.failure_definitions ?? []}
            fields={[
              { key: "name", label: "Name" },
              { key: "metric", label: "Metric" },
              { key: "op", label: "Op" },
              { key: "threshold", label: "Threshold", type: "number" },
              {
                key: "duration_s",
                label: "For s",
                type: "number",
              },
            ]}
            onChange={(rows) => updateSection("failure_definitions", rows)}
          />
          <ReviewSection
            title="Hard limits (never suppressible)"
            rows={profile.hard_limits ?? []}
            fields={[
              { key: "metric", label: "Metric" },
              { key: "op", label: "Op" },
              { key: "threshold", label: "Threshold", type: "number" },
            ]}
            onChange={(rows) => updateSection("hard_limits", rows)}
          />
          <Card title="Check · Save & confirm">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Field
                label="Confirmed by (your name)"
                locked
                value={confirmedBy}
                onChange={setConfirmedBy}
              />
            </div>
            {(profile.hard_limits ?? []).length === 0 && (
              <p className="mt-2 rounded-lg border border-warn/40 bg-warn/10 p-2 text-xs text-warn">
                No hard limits yet — they are optional, but recommended
                as the safety floor the gate checks first. Add one above
                with + Add row (e.g. error_rate over 0.5).
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const body = (await api(
                      `/api/systems/${systemId}/profile`,
                      {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(profile),
                      },
                    )) as Profile;
                    setProfile(body);
                  })
                }
              >
                Save draft
              </Button>
              <Button
                tone="primary"
                disabled={busy || !confirmedBy.trim()}
                onClick={() =>
                  run(async () => {
                    const saved = (await api(
                      `/api/systems/${systemId}/profile`,
                      {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(profile),
                      },
                    )) as Profile;
                    setProfile(saved);
                    const resolve = conflicts.map((conflict) => ({
                      field: conflict.field,
                      key: conflict.key,
                      pick:
                        picks[`${conflict.field}:${conflict.key}`] ?? 0,
                    }));
                    const body = (await api(
                      `/api/systems/${systemId}/profile/confirm`,
                      {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          confirmed_by: confirmedBy.trim(),
                          resolve,
                        }),
                      },
                    )) as Profile;
                    setProfile(body);
                    setConflicts([]);
                    await refreshSystems();
                    setStep("learn");
                  })
                }
              >
                Confirm profile
              </Button>
            </div>
          </Card>
        </>
      )}

      {step === "learn" && (
        <Card
          title="Step 4 · Watch normal for a while"
          action={
            <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[11px] tabular-nums text-text-muted">
              {profile?.baseline?.status ?? "none"}
            </span>
          }
        >
          <p className="text-sm text-text-muted">
            Two accelerated minutes with normal traffic{profile?.kind === "appliance" ? " and one defrost" : ""}.
            Watchers observe but never act while learning.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {learned ? (
              <Button
                tone="primary"
                disabled={busy}
                onClick={() => continueToPolicy()}
              >
                Continue to policy →
              </Button>
            ) : (
              <Button
                tone="primary"
                disabled={busy || !systemId || learning}
                onClick={() => startLearning()}
              >
                {learning ? "Learning…" : "Start 2-minute learning"}
              </Button>
            )}
            <Button
              disabled={busy}
              onClick={() =>
                learned ? startLearning() : continueToPolicy()
              }
            >
              {learned ? "Re-run learning" : "Skip for now"}
            </Button>
          </div>
          {learnPct !== null && (
            <div className="mt-3 flex items-center gap-3">
              <ProgressRing pct={learnPct} />
              <p className="text-xs text-text-muted">
                {learnPct >= 100
                  ? `Baseline ready${learnPatterns !== null ? ` · ${learnPatterns} patterns` : ""}`
                  : `Learning… ${Math.round(learnPct)}%${learnPatterns !== null ? ` · ${learnPatterns} patterns` : ""}`}
              </p>
            </div>
          )}
        </Card>
      )}

      {step === "policy" && profile && (
        <Card title="Step 5 · What may it do on its own?">
          <label className="flex cursor-pointer items-start gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={profile.policy?.auto_fix_allowed ?? false}
              onChange={(event) =>
                setProfile({
                  ...profile,
                  policy: {
                    ...profile.policy,
                    auto_fix_allowed: event.target.checked,
                  },
                })
              }
              className="mt-1 accent-[#a5efc0]"
            />
            <span>
              <span role="img" aria-label="Human-only" title="Human-only — the agent never changes this">
                🔒{" "}
              </span>
              Auto-fix allowed (otherwise every action waits for Do it now)
            </span>
          </label>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field
              label="Cancel window (seconds)"
              locked
              type="number"
              value={String(profile.policy?.countdown_s ?? 20)}
              onChange={(value) =>
                setProfile({
                  ...profile,
                  policy: { ...profile.policy, countdown_s: Number(value) },
                })
              }
            />
            <Field
              label="Alert contacts (comma separated)"
              locked
              value={(profile.policy?.alert_contacts ?? []).join(", ")}
              onChange={(value) =>
                setProfile({
                  ...profile,
                  policy: {
                    ...profile.policy,
                    alert_contacts: value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  },
                })
              }
            />
            <Field
              label="Confirmed by (your name)"
              locked
              value={confirmedBy}
              onChange={setConfirmedBy}
            />
          </div>
          <div className="mt-3">
            <Button
              tone="primary"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const body = (await api(
                    `/api/systems/${systemId}/profile`,
                    {
                      method: "PUT",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify(profile),
                    },
                  )) as Profile;
                  setProfile(body);
                  if (!confirmedBy.trim()) {
                    setError(
                      "Policy saved — add your name above, then save again to confirm.",
                    );
                    return;
                  }
                  const confirmed = (await api(
                    `/api/systems/${systemId}/profile/confirm`,
                    {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        confirmed_by: confirmedBy.trim(),
                        resolve: [],
                      }),
                    },
                  )) as Profile;
                  setProfile(confirmed);
                  await refreshSystems();
                  setStep("arm");
                })
              }
            >
              Save policy & continue
            </Button>
          </div>
        </Card>
      )}

      {step === "arm" && profile && (
        <Card
          title={`Step 6 · Ready to watch ${profile.name}?`}
          action={
            <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[11px] tabular-nums text-text-muted">
              {profile.status}
            </span>
          }
        >
          <p className="text-sm text-text-muted">
            {(profile.normal_ranges ?? []).length} ranges ·{" "}
            {(profile.expected_behaviours ?? []).length} expected behaviours ·{" "}
            {(profile.hard_limits ?? []).length} hard limits · auto-fix{" "}
            {profile.policy?.auto_fix_allowed ? "on" : "off"} ·{" "}
            {profile.policy?.countdown_s ?? 20}s countdown.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              tone="primary"
              disabled={busy || profile.status === "armed"}
              onClick={() =>
                run(async () => {
                  const body = (await api(
                    `/api/systems/${systemId}/arm`,
                    { method: "POST" },
                  )) as Profile;
                  setProfile(body);
                  await refreshSystems();
                })
              }
            >
              {profile.status === "armed" ? "Watching ✓" : "Start watching"}
            </Button>
            {profile.status === "armed" && (
              <>
                <Button
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const body = (await api(
                        `/api/systems/${systemId}/disarm`,
                        { method: "POST" },
                      )) as Profile;
                      setProfile(body);
                      await refreshSystems();
                      setStep("review");
                    })
                  }
                >
                  Stop watching
                </Button>
                <a
                  href="/"
                  className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[13px] font-medium text-text-muted hover:text-text"
                >
                  Open Mission Control →
                </a>
              </>
            )}
          </div>
        </Card>
      )}

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-crit/50 bg-crit/10 p-2.5 text-sm text-crit"
        >
          {error}
        </p>
      )}
      {progress && step !== "teach" && (
        <p className="rounded-lg border border-brand/40 bg-brand/10 p-2 text-xs text-brand-cyan">
          {progress}
        </p>
      )}

      <footer className="mt-2 text-xs text-text-faint">
        <a href="/" className="hover:underline">
          ← Dashboard
        </a>{" "}
        · Teach it normal before it watches.
      </footer>
    </main>
  );
}

