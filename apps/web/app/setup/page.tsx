"use client";

import { useEffect, useRef, useState } from "react";

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
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="wfield">
      <span>{label}</span>
      <input
        type={type ?? "text"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function Entries({
  title,
  rows,
  fields,
  onChange,
}: {
  title: string;
  rows: Record<string, unknown>[];
  fields: { key: string; label: string; type?: string }[];
  onChange: (rows: Record<string, unknown>[]) => void;
}) {
  function setCell(index: number, key: string, raw: string, type?: string) {
    const value = type === "number" ? Number(raw) : raw;
    onChange(
      rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)),
    );
  }
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <span className="counter">{rows.length}</span>
      </div>
      <div className="incident-body">
        {rows.length === 0 && <p className="mapempty">None yet.</p>}
        {rows.map((row, i) => {
          const provenance = (row.provenance ?? {}) as Provenance;
          return (
            <div className="wentry" key={i}>
              <div className="wgrid">
                {fields.map((field) => (
                  <Field
                    key={field.key}
                    label={field.label}
                    type={field.type}
                    value={String(row[field.key] ?? "")}
                    onChange={(value) =>
                      setCell(i, field.key, value, field.type)
                    }
                  />
                ))}
              </div>
              <p className="wquote">
                {provenance.source_doc ?? "manual"}
                {provenance.page_or_region
                  ? ` · ${provenance.page_or_region}`
                  : ""}
                {provenance.quote ? ` — “${provenance.quote}”` : ""}
                {provenance.confirmed_by
                  ? ` ✓ ${provenance.confirmed_by}`
                  : ""}
              </p>
              <button
                type="button"
                className="ghost small"
                onClick={() => onChange(rows.filter((_, j) => j !== i))}
              >
                Remove
              </button>
            </div>
          );
        })}
        <button
          type="button"
          className="ghost small"
          onClick={() => {
            const blank: Record<string, unknown> = {
              provenance: { source_doc: "manual" },
            };
            for (const field of fields) {
              blank[field.key] = field.type === "number" ? 0 : "";
            }
            onChange([...rows, blank]);
          }}
        >
          + Add row
        </button>
      </div>
    </section>
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
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">TELEMETRY AGENT / SETUP</p>
          <h1>Teach it normal</h1>
        </div>
        <div className="topbar-right">
          <a className="ghost small buttonlink" href="/">
            ← Dashboard
          </a>
        </div>
      </header>

      <nav className="wsteps" aria-label="Setup steps">
        {STEPS.map((s) => (
          <button
            key={s}
            type="button"
            className={s === step ? "wstep active" : "wstep"}
            onClick={() => setStep(s)}
          >
            {s}
          </button>
        ))}
      </nav>

      {systems.length > 0 && (
        <section className="panel map-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">SYSTEMS</p>
              <h2>Pick up where you left off</h2>
            </div>
          </div>
          <div className="controls scenario-controls">
            {systems.map((s) => (
              <button
                key={s.system_id}
                type="button"
                className={s.system_id === systemId ? "" : "ghost"}
                onClick={() =>
                  run(async () => {
                    setSystemId(s.system_id);
                    await loadProfile(s.system_id);
                    setStep("review");
                  })
                }
              >
                {s.name} · {s.status}
              </button>
            ))}
          </div>
        </section>
      )}

      {step === "connect" && (
        <section className="panel map-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">STEP 1 · CONNECT</p>
              <h2>What are we watching?</h2>
            </div>
          </div>
          <div className="incident-body">
            <div className="wgrid">
              <Field label="System name" value={name} onChange={setName} />
              <label className="wfield">
                <span>System type</span>
                <select
                  value={kind}
                  onChange={(event) => setKind(event.target.value)}
                >
                  <option value="software">Software service</option>
                  <option value="appliance">Cold-chain appliance</option>
                </select>
              </label>
              {kind === "appliance" && (
                <label className="wfield">
                  <span>Appliance</span>
                  <select
                    value={applianceType}
                    onChange={(event) => setApplianceType(event.target.value)}
                  >
                    <option value="fridge">Fridge</option>
                    <option value="freezer">Freezer</option>
                  </select>
                </label>
              )}
              <Field
                label="Owner contact"
                value={contact}
                onChange={setContact}
              />
            </div>
            <div className="controls">
              <button
                type="button"
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
              </button>
            </div>
          </div>
        </section>
      )}

      {step === "teach" && (
        <section className="panel map-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">STEP 2 · TEACH IT NORMAL</p>
              <h2>Upload docs for {current?.name ?? "…"}</h2>
            </div>
          </div>
          <div className="incident-body">
            <p className="mapempty" style={{ padding: 0 }}>
              Spec PDFs, rating-plate photos, ops docs — or paste text. The
              agent quotes every value it takes and never guesses numbers.
            </p>
            <div className="controls">
              <input
                ref={fileRef}
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg,.txt,.md"
                aria-label="Documents"
              />
              <button
                type="button"
                disabled={busy || !systemId}
                onClick={() =>
                  run(async () => {
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
                  })
                }
              >
                Upload & extract
              </button>
              <button
                type="button"
                className="ghost"
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
              </button>
            </div>
            <div className="wgrid">
              <Field
                label="Pasted note filename"
                value={pasteName}
                onChange={setPasteName}
              />
            </div>
            <textarea
              className="wtextarea"
              rows={5}
              placeholder="Or paste an owner note here…"
              value={pasteText}
              onChange={(event) => setPasteText(event.target.value)}
              aria-label="Pasted text"
            />
            {progress && <p className="notice">{progress}</p>}
          </div>
        </section>
      )}

      {step === "review" && profile && (
        <>
          {conflicts.length > 0 && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">REVIEW · CONFLICTS</p>
                  <h2>Pick the true value</h2>
                </div>
                <span className="counter">{conflicts.length}</span>
              </div>
              <div className="incident-body">
                {conflicts.map((conflict, i) => (
                  <div className="wentry" key={i}>
                    <p>
                      <strong>
                        {conflict.field}.{conflict.key}
                      </strong>
                    </p>
                    {conflict.values.map((option, j) => (
                      <label className="wpick" key={j}>
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
                        />
                        <span>
                          <code>
                            {JSON.stringify(option.value, null, 0)}
                          </code>{" "}
                          <span className="hint">
                            {option.doc}
                            {option.quote ? ` — “${option.quote}”` : ""}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            </section>
          )}
          {feedback.length > 0 && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">REVIEW · MARKED NORMAL</p>
                  <h2>Pending “this is normal” votes</h2>
                </div>
                <span className="counter">{feedback.length}</span>
              </div>
              <div className="incident-body">
                <p className="mapempty" style={{ padding: 0 }}>
                  Confirming adds the signature as an expected behaviour.
                  Hard limits can never be marked normal.
                </p>
                {feedback.map((item) => (
                  <div className="wentry" key={item.id}>
                    <p>
                      <code>{item.signature}</code>
                    </p>
                    <p className="hint">
                      {[item.rule, item.fingerprint, item.created_by]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <div className="controls">
                      <button
                        type="button"
                        className="ghost small"
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
                      </button>
                      <button
                        type="button"
                        className="ghost small"
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
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
          <Entries
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
          <Entries
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
          <Entries
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
          <Entries
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
          <Entries
            title="Hard limits (never suppressible)"
            rows={profile.hard_limits ?? []}
            fields={[
              { key: "metric", label: "Metric" },
              { key: "op", label: "Op" },
              { key: "threshold", label: "Threshold", type: "number" },
            ]}
            onChange={(rows) => updateSection("hard_limits", rows)}
          />
          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">REVIEW · CONFIRM</p>
                <h2>Save & confirm</h2>
              </div>
            </div>
            <div className="incident-body">
              <div className="wgrid">
                <Field
                  label="Confirmed by (your name)"
                  value={confirmedBy}
                  onChange={setConfirmedBy}
                />
              </div>
              {(profile.hard_limits ?? []).length === 0 && (
                <p className="notice">
                  No hard limits yet — they are optional, but recommended
                  as the safety floor the gate checks first. Add one above
                  with + Add row (e.g. error_rate over 0.5).
                </p>
              )}
              <div className="controls">
                <button
                  type="button"
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
                </button>
                <button
                  type="button"
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
                </button>
              </div>
            </div>
          </section>
        </>
      )}

      {step === "learn" && (
        <section className="panel map-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">STEP 4 · LEARN BASELINE</p>
              <h2>Watch normal for a while</h2>
            </div>
            <span className="counter">
              {profile?.baseline?.status ?? "none"}
            </span>
          </div>
          <div className="incident-body">
            <p className="mapempty" style={{ padding: 0 }}>
              Two accelerated minutes with normal traffic{profile?.kind === "appliance" ? " and one defrost" : ""}.
              Watchers observe but never act while learning.
            </p>
            <div className="controls">
              {learned ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => continueToPolicy()}
                >
                  Continue to policy →
                </button>
              ) : (
                <button
                  type="button"
                  disabled={busy || !systemId || learning}
                  onClick={() => startLearning()}
                >
                  {learning ? "Learning…" : "Start 2-minute learning"}
                </button>
              )}
              <button
                type="button"
                className="ghost"
                disabled={busy}
                onClick={() =>
                  learned ? startLearning() : continueToPolicy()
                }
              >
                {learned ? "Re-run learning" : "Skip for now"}
              </button>
            </div>
            {learnPct !== null && (
              <div>
                <div
                  className="learnbar"
                  role="progressbar"
                  aria-valuenow={Math.round(learnPct)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <span style={{ width: `${Math.min(100, learnPct)}%` }} />
                </div>
                <p className="notice">
                  {learnPct >= 100
                    ? `Baseline ready${learnPatterns !== null ? ` · ${learnPatterns} patterns` : ""}`
                    : `Learning… ${Math.round(learnPct)}%${learnPatterns !== null ? ` · ${learnPatterns} patterns` : ""}`}
                </p>
              </div>
            )}
          </div>
        </section>
      )}

      {step === "policy" && profile && (
        <section className="panel map-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">STEP 5 · POLICY</p>
              <h2>What may it do on its own?</h2>
            </div>
          </div>
          <div className="incident-body">
            <label className="wpick">
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
              />
              <span>Auto-fix allowed (otherwise every action needs Approve)</span>
            </label>
            <div className="wgrid">
              <Field
                label="Countdown seconds"
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
            </div>
            <div className="controls">
              <button
                type="button"
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
                        "Policy saved as a draft edit — confirm again to continue.",
                      );
                      setStep("review");
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
              </button>
            </div>
          </div>
        </section>
      )}

      {step === "arm" && profile && (
        <section className="panel map-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">STEP 6 · ARM</p>
              <h2>Ready to watch {profile.name}?</h2>
            </div>
            <span className="counter">{profile.status}</span>
          </div>
          <div className="incident-body">
            <p className="mapempty" style={{ padding: 0 }}>
              {(profile.normal_ranges ?? []).length} ranges ·{" "}
              {(profile.expected_behaviours ?? []).length} expected behaviours ·{" "}
              {(profile.hard_limits ?? []).length} hard limits · auto-fix{" "}
              {profile.policy?.auto_fix_allowed ? "on" : "off"} ·{" "}
              {profile.policy?.countdown_s ?? 20}s countdown.
            </p>
            <div className="controls">
              <button
                type="button"
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
                {profile.status === "armed" ? "Armed ✓" : "Arm system"}
              </button>
              {profile.status === "armed" && (
                <a className="ghost small buttonlink" href="/">
                  Open dashboard →
                </a>
              )}
            </div>
          </div>
        </section>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {progress && step !== "teach" && <p className="notice">{progress}</p>}

      <footer>
        <a href="/">← Dashboard</a> · Teach it normal before it watches.
      </footer>
    </main>
  );
}
