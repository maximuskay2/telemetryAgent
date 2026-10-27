"use client";

import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";

type AgentStepEvent = {
  step: string;
  attempt: number;
  model: string;
  status: string;
  message: string;
  duration_ms: number;
  run_id: string;
  domain: string;
  detail: string;
  source: string;
  suggestions: string[];
};

type LogEvent = {
  id: string;
  timestamp: string;
  source: string;
  message: string;
  level: string;
};

type IncidentState = {
  runId: string;
  status: string;
  source: string;
  startedAt: number;
  elapsedMs: number;
  telemetry: string;
  diagnosis: string;
  diagnosisMeta: string;
  suggestions: string[];
  fix: string;
  fixMeta: string;
  verification: string;
  verificationMeta: string;
  final: string;
  finalMeta: string;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const DEADLOCK_SAMPLE = [
  "2026-10-26T14:21:03.410Z ERROR transaction=tx-8841 service=orders",
  "Deadlock detected while acquiring lock on inventory_items; transaction rolled back.",
  "2026-10-26T14:21:03.414Z WARNING retry=1 transaction=tx-8841 backoff_ms=250",
].join("\n");

const MAX_LOG_CHARS = 200_000;
const TRIMMED_LINES = 1500;
const DISPLAY_CHARS = 4000;

const APPLIANCE_TYPES = ["fridge", "freezer"];
const FAULTS = [
  "door_open",
  "condenser_fouling",
  "power_surge",
  "rapid_restart",
  "none",
];

const emptyIncident = (): IncidentState => ({
  runId: "",
  status: "idle",
  source: "",
  startedAt: 0,
  elapsedMs: 0,
  telemetry: "",
  diagnosis: "",
  diagnosisMeta: "",
  suggestions: [],
  fix: "",
  fixMeta: "",
  verification: "",
  verificationMeta: "",
  final: "",
  finalMeta: "",
});

function stageMeta(model: string, ms: number): string {
  const parts: string[] = [];
  if (model) parts.push(model);
  if (ms > 0) parts.push(`${Math.round(ms)}ms`);
  return parts.join(" · ");
}

async function responseDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    // fall through to the status-based message
  }
  return `API returned ${response.status}`;
}

function trimLogToLimit(text: string): { text: string; trimmed: boolean } {
  if (text.length <= MAX_LOG_CHARS) return { text, trimmed: false };
  const kept = text.split("\n").slice(-TRIMMED_LINES).join("\n");
  return {
    text: kept.length <= MAX_LOG_CHARS ? kept : kept.slice(-MAX_LOG_CHARS),
    trimmed: true,
  };
}

function displayCap(text: string): string {
  if (text.length <= DISPLAY_CHARS) return text;
  return `${text.slice(0, DISPLAY_CHARS)}\n… (${text.length - DISPLAY_CHARS} more characters)`;
}

function applyStep(prev: IncidentState, msg: AgentStepEvent): IncidentState {
  let base = prev;
  if (msg.run_id && msg.run_id !== prev.runId) {
    // A run this panel never started (e.g. from the log watcher): adopt it
    // only when the panel is idle, otherwise a newer click owns the panel.
    if (prev.status === "running") return prev;
    base = {
      ...emptyIncident(),
      status: "running",
      runId: msg.run_id,
      telemetry: `Live incident · run ${msg.run_id}`,
      source: msg.source || "",
      startedAt: Date.now(),
    };
  }
  const next: IncidentState = { ...base, runId: msg.run_id || base.runId };
  if (!next.startedAt) next.startedAt = Date.now();
  if (!next.source && msg.source) next.source = msg.source;
  if (msg.step === "diagnose") {
    next.diagnosis = msg.detail;
    next.diagnosisMeta = stageMeta(msg.model, msg.duration_ms);
    next.suggestions = Array.isArray(msg.suggestions)
      ? msg.suggestions.filter((s): s is string => typeof s === "string")
      : [];
  } else if (msg.step === "generate") {
    const tag = msg.attempt > 0 ? `attempt ${msg.attempt}: ` : "";
    next.fix = `${tag}${msg.detail}`;
    next.fixMeta = stageMeta(msg.model, msg.duration_ms);
  } else if (msg.step === "verify") {
    const tag = msg.attempt > 0 ? `[${msg.status} attempt ${msg.attempt}] ` : "";
    next.verification = `${tag}${msg.detail}`;
    next.verificationMeta = stageMeta(msg.model, msg.duration_ms);
  } else if (msg.step === "done") {
    next.status = msg.status || "done";
    next.final = msg.message;
    next.finalMeta = stageMeta(msg.model, 0);
    next.elapsedMs = Date.now() - (next.startedAt || Date.now());
  }
  return next;
}

type StepState = "done" | "active" | "todo" | "failed";

function stepStates(incident: IncidentState): StepState[] {
  const reached = [
    incident.telemetry !== "",
    incident.runId !== "" || incident.status === "running",
    incident.diagnosis !== "",
    incident.fix !== "",
    incident.verification !== "",
    incident.final !== "",
  ];
  const failed = incident.status === "error" || incident.status === "FAIL";
  return reached.map((done, i) => {
    if (done) return failed && i === reached.length - 1 ? "failed" : "done";
    const prevDone = i === 0 || reached[i - 1];
    if (prevDone && (incident.status === "running" || failed)) {
      return failed ? "failed" : "active";
    }
    return "todo";
  });
}

function ProgressBar({ labels, states }: { labels: string[]; states: StepState[] }) {
  return (
    <ol className="progress" aria-label="Pipeline progress">
      {labels.map((label, i) => (
        <li
          key={label}
          className={`pstep ${states[i]}`}
          aria-current={states[i] === "active" ? "step" : undefined}
        >
          <span className="dot">{i + 1}</span>
          <span className="plabel">{label}</span>
        </li>
      ))}
    </ol>
  );
}

function Stage({
  label,
  value,
  meta,
}: {
  label: string;
  value: string;
  meta: string;
}) {
  return (
    <div className="stage">
      <div className="stage-head">
        <span>{label}</span>
        {meta && <span className="meta">{meta}</span>}
      </div>
      <pre>{value || "—"}</pre>
    </div>
  );
}

export default function Home() {
  const [software, setSoftware] = useState<IncidentState>(emptyIncident);
  const [appliance, setAppliance] = useState<IncidentState>(emptyIncident);
  const [applianceType, setApplianceType] = useState("fridge");
  const [fault, setFault] = useState("door_open");
  const [logText, setLogText] = useState(DEADLOCK_SAMPLE);
  const [targetFile, setTargetFile] = useState("inventory.py");
  const [trimNotice, setTrimNotice] = useState("");
  const [events, setEvents] = useState<LogEvent[]>([]);
  const [connection, setConnection] = useState("connecting");
  const [error, setError] = useState("");

  useEffect(() => {
    const socket = new WebSocket(`${apiUrl.replace(/^http/, "ws")}/api/ws`);
    socket.onopen = () => setConnection("connected");
    socket.onclose = () => setConnection("disconnected");
    socket.onerror = () => setConnection("disconnected");
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as AgentStepEvent & LogEvent;
        if (
          typeof data.step === "string" &&
          (data.domain === "software" || data.domain === "appliance")
        ) {
          const update =
            data.domain === "software" ? setSoftware : setAppliance;
          update((prev) => applyStep(prev, data));
        } else if (typeof data.message === "string") {
          setEvents((current) => [...current.slice(-49), data]);
        }
      } catch {
        setError("Received an invalid event from the API.");
      }
    };
    return () => socket.close();
  }, []);

  async function loadSample() {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/samples/deadlock`);
      if (!response.ok) throw new Error(await responseDetail(response));
      const body = (await response.json()) as { log_text?: unknown };
      if (typeof body.log_text !== "string" || !body.log_text) {
        throw new Error("Sample came back empty.");
      }
      setLogText(body.log_text);
      setTrimNotice("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load sample.");
    }
  }

  function readLogFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    const reader = new FileReader();
    reader.onload = () => {
      const raw = typeof reader.result === "string" ? reader.result : "";
      const { text, trimmed } = trimLogToLimit(raw);
      setLogText(text);
      setTrimNotice(
        trimmed
          ? `File exceeded ${MAX_LOG_CHARS / 1000} KB; kept the last ${TRIMMED_LINES} lines.`
          : "",
      );
    };
    reader.onerror = () => setError("Could not read that file.");
    reader.readAsText(file);
  }

  async function injectSoftware() {
    const text = logText.trim();
    if (!text) {
      setError("Paste or upload a log first.");
      return;
    }
    setSoftware({
      ...emptyIncident(),
      status: "running",
      telemetry: displayCap(text),
      source: "upload",
      startedAt: Date.now(),
    });
    setError("");
    try {
      const target = targetFile.trim();
      const response = await fetch(`${apiUrl}/api/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          log_text: text,
          source: "upload",
          ...(target ? { target_path: target } : {}),
        }),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      const result = await response.json();
      setSoftware((prev) =>
        prev.final
          ? prev
          : {
              ...prev,
              status: result.status,
              final: result.pr_url ?? result.stderr ?? "",
              finalMeta: result.model_used ?? "",
            },
      );
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not inject incident.";
      setError(message);
      setSoftware((prev) =>
        prev.final ? prev : { ...prev, status: "error", final: message },
      );
    }
  }

  async function injectAppliance() {
    const telemetry = `${applianceType} · fault=${fault} · 30 synthetic readings`;
    setAppliance({
      ...emptyIncident(),
      status: "running",
      telemetry,
      source: "upload",
      startedAt: Date.now(),
    });
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/run/appliance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          appliance_type: applianceType,
          fault,
          source: "upload",
        }),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      const result = await response.json();
      setAppliance((prev) => {
        if (prev.final) return prev;
        const final = result.alert
          ? `${result.alert.alert_id} · ${result.alert.work_order_id}`
          : (result.feedback ?? "");
        return {
          ...prev,
          status: result.status,
          final,
          finalMeta: result.model_used ?? "",
        };
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not inject incident.";
      setError(message);
      setAppliance((prev) =>
        prev.final ? prev : { ...prev, status: "error", final: message },
      );
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AUTONOMOUS SRE / LIVE INCIDENTS</p>
          <h1>Telemetry Agent</h1>
        </div>
        <div className={`status ${connection}`}>
          <span className="status-dot" />
          {connection}
        </div>
      </header>

      <div className="grid">
        <section className="panel incident">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">SOFTWARE</p>
              <h2>Crash log incident</h2>
            </div>
            <span className={`chip ${software.status.toLowerCase()}`}>
              {software.status}
            </span>
          </div>
          <div className="incident-body">
            <div className="log-input">
              <textarea
                value={logText}
                onChange={(event) => setLogText(event.target.value)}
                placeholder="Paste a traceback or log…"
                rows={6}
                maxLength={MAX_LOG_CHARS}
                aria-label="Log text"
              />
              <div className="controls">
                <label htmlFor="log-file">File</label>
                <input
                  id="log-file"
                  type="file"
                  accept=".log,.txt"
                  onChange={readLogFile}
                />
                <button type="button" onClick={loadSample}>
                  Load sample
                </button>
                <label htmlFor="target">Target</label>
                <input
                  id="target"
                  value={targetFile}
                  onChange={(event) => setTargetFile(event.target.value)}
                  placeholder="inventory.py"
                  maxLength={200}
                />
                <button
                  type="button"
                  onClick={injectSoftware}
                  disabled={software.status === "running"}
                >
                  Inject log
                </button>
              </div>
              {trimNotice && <p className="notice">{trimNotice}</p>}
              <div className="run-meta">
                <span className="hint">Diagnose → patch → sandbox → PR</span>
                {software.source && software.source !== "upload" && (
                  <span className="via">Detected by {software.source}</span>
                )}
                {software.elapsedMs > 0 && (
                  <span className="hint">
                    warning → verified fix: {(software.elapsedMs / 1000).toFixed(1)}s
                  </span>
                )}
              </div>
            </div>
            <ProgressBar
              labels={["Grab logs", "Inject", "Diagnosis", "Generated fix", "Verification", "Final action"]}
              states={stepStates(software)}
            />
            <Stage label="Incoming telemetry" value={software.telemetry} meta="" />
            <Stage
              label="Diagnosis"
              value={software.diagnosis}
              meta={software.diagnosisMeta}
            />
            <Stage
              label="Suggestions"
              value={software.suggestions.map((s) => `• ${s}`).join("\n")}
              meta=""
            />
            <Stage
              label="Generated fix"
              value={software.fix}
              meta={software.fixMeta}
            />
            <Stage
              label="Verification"
              value={software.verification}
              meta={software.verificationMeta}
            />
            <Stage
              label="Final action"
              value={software.final}
              meta={software.finalMeta}
            />
          </div>
        </section>

        <section className="panel incident">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">APPLIANCE</p>
              <h2>Fridge incident</h2>
            </div>
            <span className={`chip ${appliance.status.toLowerCase()}`}>
              {appliance.status}
            </span>
          </div>
          <div className="incident-body">
            <div className="controls">
              <label htmlFor="appliance-type">Unit</label>
              <select
                id="appliance-type"
                value={applianceType}
                onChange={(event) => setApplianceType(event.target.value)}
              >
                {APPLIANCE_TYPES.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <label htmlFor="fault">Fault</label>
              <select
                id="fault"
                value={fault}
                onChange={(event) => setFault(event.target.value)}
              >
                {FAULTS.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={injectAppliance}
                disabled={appliance.status === "running"}
              >
                Inject fault
              </button>
            </div>
            <div className="run-meta">
              {appliance.source && appliance.source !== "upload" && (
                <span className="via">Detected by {appliance.source}</span>
              )}
              {appliance.elapsedMs > 0 && (
                <span className="hint">
                  warning → verified fix: {(appliance.elapsedMs / 1000).toFixed(1)}s
                </span>
              )}
            </div>
            <ProgressBar
              labels={["Grab telemetry", "Inject", "Diagnosis", "Runbook", "Safety check", "Final action"]}
              states={stepStates(appliance)}
            />
            <Stage label="Incoming telemetry" value={appliance.telemetry} meta="" />
            <Stage
              label="Diagnosis"
              value={appliance.diagnosis}
              meta={appliance.diagnosisMeta}
            />
            <Stage
              label="Suggestions"
              value={appliance.suggestions.map((s) => `• ${s}`).join("\n")}
              meta=""
            />
            <Stage
              label="Generated fix"
              value={appliance.fix}
              meta={appliance.fixMeta}
            />
            <Stage
              label="Verification"
              value={appliance.verification}
              meta={appliance.verificationMeta}
            />
            <Stage
              label="Final action"
              value={appliance.final}
              meta={appliance.finalMeta}
            />
          </div>
        </section>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">STREAM</p>
            <h2>Log events</h2>
          </div>
          <span className="counter">{events.length} events</span>
        </div>
        <div className="event-list feed-list" aria-live="polite">
          {events.length === 0 ? (
            <div className="empty">
              <span className="prompt-mark">&gt;_</span>
              <p>Waiting for telemetry</p>
              <span>POST to /api/logs or inject an incident above.</span>
            </div>
          ) : (
            events.map((item) => (
              <article className="event" key={item.id}>
                <time>{new Date(item.timestamp).toLocaleTimeString()}</time>
                <span className={`level ${item.level.toLowerCase()}`}>
                  {item.level}
                </span>
                <span className="source">{item.source}</span>
                <p>{item.message}</p>
              </article>
            ))
          )}
        </div>
      </section>

      <footer>Local-first telemetry · API {apiUrl}</footer>
    </main>
  );
}
