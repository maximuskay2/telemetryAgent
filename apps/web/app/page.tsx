"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, ReactElement } from "react";
import ServiceMap, { type OrderDot } from "./components/ServiceMap";
import PipelineLane from "./components/PipelineLane";
import VirtualFridge, { type FridgeState } from "./components/VirtualFridge";
import { QRCodeSVG } from "qrcode.react";
import Sparkline from "./components/Sparkline";

type ShopMetrics = {
  ordersPerMin: number;
  errorRate: number;
  p95Ms: number;
  seenAt: number;
};

// The shop publishes metrics every second; no metrics for this long means it is down.
const SHOP_STALE_MS = 5000;
const TRAFFIC = { shoppers: 8, rate: 20, duration: 60 };

function errorTone(rate: number): string {
  if (rate >= 0.2) return "bad";
  if (rate > 0) return "warn";
  return "good";
}

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
  tag?: string;
};

function feedItem(
  source: string,
  message: string,
  level: string,
  tag?: string,
): LogEvent {
  return {
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: new Date().toISOString(),
    source,
    message,
    level,
    tag,
  };
}

function firstLine(text: string, max: number): string {
  const line = text.split("\n")[0].trim();
  return line.length > max ? `${line.slice(0, max)}…` : line;
}

function watcherSentence(payload: {
  rule?: unknown;
  level?: unknown;
  domain?: unknown;
  resource?: unknown;
  matched_lines?: unknown;
}): { message: string; level: string; source: string } | null {
  if (typeof payload.rule !== "string") return null;
  const on =
    typeof payload.resource === "string" && payload.resource
      ? ` on ${payload.resource}`
      : "";
  const detail = Array.isArray(payload.matched_lines)
    ? payload.matched_lines.find((l): l is string => typeof l === "string")
    : undefined;
  const level = payload.level === "error" ? "ERROR" : "WARNING";
  const source = payload.domain === "appliance" ? "sensor-watcher" : "watcher";
  switch (payload.rule) {
    case "retry-cluster":
      return { message: `Watcher caught a retry storm${on}`, level, source };
    case "deadlock":
      return { message: `Watcher caught a deadlock${on}`, level, source };
    case "traceback":
      return { message: `Watcher caught a traceback${on}`, level, source };
    case "error":
      return { message: `Watcher caught an error${on}`, level, source };
    case "temp-warning":
    case "temp-critical":
    case "current-warning":
    case "current-spike":
      return {
        message: `Sensor watcher caught ${payload.rule}${detail ? `: ${detail}` : ""}`,
        level,
        source,
      };
    default:
      return { message: `Watcher caught ${payload.rule}${on}`, level, source };
  }
}

function stepSentence(msg: AgentStepEvent): LogEvent | null {
  const tag = msg.model || undefined;
  if (msg.step === "diagnose") {
    return feedItem(
      "agent",
      `Diagnosed: ${firstLine(msg.detail || msg.message, 140)}`,
      "INFO",
      tag,
    );
  }
  if (msg.step === "generate") {
    return feedItem(
      "agent",
      `Wrote a fix (attempt ${msg.attempt})`,
      "INFO",
      tag,
    );
  }
  if (msg.step === "verify") {
    const failed = msg.status === "FAIL" || msg.status === "error";
    return feedItem(
      "agent",
      `Sandbox verification: ${msg.status || "ran"}`,
      failed ? "ERROR" : "INFO",
      tag,
    );
  }
  if (msg.step === "done") {
    const failed = msg.status === "FAIL" || msg.status === "error";
    const tail = msg.message ? ` — ${firstLine(msg.message, 120)}` : "";
    return feedItem(
      "agent",
      failed
        ? `Run finished: ${msg.status || "error"}${tail}`
        : `Run finished: verified fix${tail}`,
      failed ? "ERROR" : "INFO",
      tag,
    );
  }
  return null;
}

type VetoAction = {
  runId: string;
  domain: string;
  summary: string;
  deadlineMs: number;
  secondsLeft: number;
  state: string;
  decidedBy: string;
  detail: string;
};

// Same outcome titles as the phone (M3 parity).
function vetoCopy(
  veto: VetoAction,
  left: number,
): { text: string; tone: string } {
  switch (veto.state) {
    case "pending":
      return {
        text: `⏳ ${veto.summary} — auto-apply in ${left}s (veto from phone)`,
        tone: "running",
      };
    case "approved":
      return { text: `Approved ✓ ${veto.detail}`, tone: "pass" };
    case "auto_applied":
      return { text: "Auto-applied ✓ at 0s", tone: "pass" };
    case "disapproved":
      return {
        text: `Disapproved — left for a human (${veto.decidedBy})`,
        tone: "",
      };
    case "failed":
      return { text: `Apply failed: ${veto.detail}`, tone: "fail" };
    default:
      return { text: `Window ${veto.state}`, tone: "" };
  }
}

function vetoFor(
  vetoes: Record<string, VetoAction>,
  domain: string,
  runId: string,
): VetoAction | null {
  if (runId && vetoes[runId]) return vetoes[runId];
  const same = Object.values(vetoes).filter((v) => v.domain === domain);
  if (same.length === 0) return null;
  return same.sort((a, b) => b.deadlineMs - a.deadlineMs)[0];
}

function VetoStrip({
  veto,
  now,
}: {
  veto: VetoAction | null;
  now: number;
}): ReactElement | null {
  if (!veto) return null;
  const fromDeadline = Math.max(
    0,
    Math.ceil((veto.deadlineMs - now) / 1000),
  );
  const left =
    veto.state === "pending"
      ? Math.min(veto.secondsLeft, fromDeadline)
      : 0;
  const copy = vetoCopy(veto, left);
  return (
    <p className="veto">
      <span className={`chip ${copy.tone}`}>veto</span> {copy.text}
    </p>
  );
}

const FRIDGE_SENTENCES: Record<string, string> = {
  door_open: "Fridge door opened",
  condenser_fouling: "Condenser dirtied",
  power_surge: "Power surge injected",
  rapid_restart: "Rapid restart injected",
  close_door: "Fridge door closed",
  clean_condenser: "Condenser cleaned",
  reset: "Fridge reset",
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

function laneProps(incident: IncidentState) {
  return {
    reached: [
      incident.telemetry !== "",
      incident.runId !== "" || incident.status === "running",
      incident.diagnosis !== "",
      incident.verification !== "",
      incident.final !== "",
    ],
    running: incident.status === "running",
    failed: incident.status === "error" || incident.status === "FAIL",
  };
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
  const [orders, setOrders] = useState<OrderDot[]>([]);
  const [fridgeTemps, setFridgeTemps] = useState<number[]>([]);
  const [fridge, setFridge] = useState<FridgeState | null>(null);
  const [scenario, setScenario] = useState({
    playing: false,
    done: 0,
    total: 0,
    current: "",
  });
  const [pairUrl, setPairUrl] = useState<string | null>(null);
  const [connection, setConnection] = useState("connecting");
  const [reconnectKey, setReconnectKey] = useState(0);
  const [error, setError] = useState("");
  const [shopMetrics, setShopMetrics] = useState<ShopMetrics | null>(null);
  const [errorRates, setErrorRates] = useState<number[]>([]);
  const [trafficUntil, setTrafficUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [mountedAt] = useState(() => Date.now());
  const [vetoes, setVetoes] = useState<Record<string, VetoAction>>({});
  const fetchedRuns = useRef<Set<string>>(new Set());
  const knownRuns = useRef<Set<string>>(new Set());

  function applyActionPayload(payload: {
    run_id?: unknown;
    domain?: unknown;
    action?: unknown;
    deadline?: unknown;
    seconds_left?: unknown;
    seconds?: unknown;
    state?: unknown;
    decided_by?: unknown;
    detail?: unknown;
  }) {
    if (typeof payload.run_id !== "string" || !payload.run_id) return;
    const runId = payload.run_id;
    knownRuns.current.add(runId);
    setVetoes((current) => {
      const prev = current[runId];
      const merged: VetoAction = {
        runId,
        domain:
          typeof payload.domain === "string"
            ? payload.domain
            : (prev?.domain ?? ""),
        summary:
          typeof payload.action === "string"
            ? payload.action
            : (prev?.summary ?? ""),
        deadlineMs:
          typeof payload.deadline === "number"
            ? payload.deadline * 1000
            : (prev?.deadlineMs ?? 0),
        secondsLeft:
          typeof payload.seconds_left === "number"
            ? payload.seconds_left
            : typeof payload.seconds === "number"
              ? Math.ceil(payload.seconds)
              : (prev?.secondsLeft ?? 0),
        state:
          typeof payload.state === "string"
            ? payload.state
            : (prev?.state ?? "pending"),
        decidedBy:
          typeof payload.decided_by === "string"
            ? payload.decided_by
            : (prev?.decidedBy ?? ""),
        detail:
          typeof payload.detail === "string"
            ? payload.detail
            : (prev?.detail ?? ""),
      };
      return { ...current, [runId]: merged };
    });
  }

  // Late joiners only see ticks; fetch the full window once per run.
  async function fetchRunDecision(runId: string) {
    if (fetchedRuns.current.has(runId)) return;
    fetchedRuns.current.add(runId);
    try {
      const response = await fetch(`${apiUrl}/api/runs/${runId}`);
      if (!response.ok) return;
      const body = (await response.json()) as { decision?: unknown };
      if (body.decision && typeof body.decision === "object") {
        applyActionPayload(body.decision as Record<string, unknown>);
      }
    } catch {
      fetchedRuns.current.delete(runId);
    }
  }

  useEffect(() => {
    const timer = window.setInterval(() => {
      setOrders((current) => current.filter((o) => Date.now() - o.born < 6000));
    }, 2000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let disposed = false;
    let retry: number | undefined;
    const socket = new WebSocket(`${apiUrl.replace(/^http/, "ws")}/api/ws`);
    socket.onopen = () => setConnection("connected");
    socket.onclose = () => {
      setConnection("disconnected");
      if (!disposed) {
        retry = window.setTimeout(() => setReconnectKey((key) => key + 1), 2000);
      }
    };
    socket.onerror = () => socket.close();
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
          const milestone = stepSentence(data);
          if (milestone) {
            setEvents((current) => [...current.slice(-49), milestone]);
          }
        } else if (
          (data as unknown as { kind?: string }).kind === "shop_order"
        ) {
          const payload = (
            data as unknown as {
              payload?: { order_id?: unknown; status?: unknown; items?: unknown };
            }
          ).payload;
          if (payload && typeof payload.order_id === "string") {
            const status =
              payload.status === "failed"
                ? "failed"
                : payload.status === "waiting"
                  ? "waiting"
                  : "ok";
            const items = Array.isArray(payload.items)
              ? payload.items.filter((s): s is string => typeof s === "string")
              : [];
            const order: OrderDot = {
              id: payload.order_id,
              status,
              items,
              born: Date.now(),
            };
            setOrders((current) =>
              [...current.filter((o) => Date.now() - o.born < 6000), order].slice(-24),
            );
          }
        } else if (
          (data as unknown as { kind?: string }).kind === "shop_metrics"
        ) {
          const payload = (
            data as unknown as {
              payload?: {
                orders_per_min?: unknown;
                error_rate?: unknown;
                p95_ms?: unknown;
              };
            }
          ).payload;
          if (
            payload &&
            typeof payload.orders_per_min === "number" &&
            typeof payload.error_rate === "number" &&
            typeof payload.p95_ms === "number"
          ) {
            const rate = payload.error_rate;
            setShopMetrics({
              ordersPerMin: payload.orders_per_min,
              errorRate: rate,
              p95Ms: payload.p95_ms,
              seenAt: Date.now(),
            });
            setErrorRates((current) => [...current, rate].slice(-60));
          }
        } else if (
          (data as unknown as { kind?: string }).kind === "fridge_reading"
        ) {
          const payload = (
            data as unknown as {
              payload?: {
                reading?: {
                  temperature_c?: unknown;
                  current_a?: unknown;
                  vibration_g?: unknown;
                };
                state?: {
                  temp_c?: unknown;
                  door_open?: unknown;
                  compressor_on?: unknown;
                  condenser_dirty?: unknown;
                  surge_active?: unknown;
                  short_cycling?: unknown;
                };
              };
            }
          ).payload;
          const reading = payload?.reading;
          const st = payload?.state;
          if (
            reading &&
            typeof reading.temperature_c === "number" &&
            typeof reading.current_a === "number" &&
            typeof reading.vibration_g === "number"
          ) {
            setFridgeTemps((current) =>
              [...current, reading.temperature_c as number].slice(-60),
            );
            setFridge({
              temp_c: reading.temperature_c,
              current_a: reading.current_a,
              vibration_g: reading.vibration_g,
              door_open: st?.door_open === true,
              compressor_on: st?.compressor_on === true,
              condenser_dirty: st?.condenser_dirty === true,
              surge_active: st?.surge_active === true,
              short_cycling: st?.short_cycling === true,
            });
          }
        } else if (
          (data as unknown as { kind?: string }).kind === "scenario_step"
        ) {
          const payload = (
            data as unknown as {
              payload?: { done?: unknown; total?: unknown; action?: unknown };
            }
          ).payload;
          if (
            payload &&
            typeof payload.done === "number" &&
            typeof payload.total === "number"
          ) {
            setScenario({
              playing: payload.done < payload.total,
              done: payload.done,
              total: payload.total,
              current:
                typeof payload.action === "string" ? payload.action : "",
            });
            const action =
              typeof payload.action === "string" ? payload.action : "step";
            setEvents((current) => [
              ...current.slice(-49),
              feedItem(
                "scenario",
                `Scenario step ${payload.done}/${payload.total}: ${action}`,
                "INFO",
              ),
            ]);
          }
        } else if (
          (data as unknown as { kind?: string }).kind === "watcher_trigger"
        ) {
          const payload = (data as unknown as { payload?: object }).payload;
          const sentence =
            payload && typeof payload === "object"
              ? watcherSentence(payload)
              : null;
          if (sentence) {
            setEvents((current) => [
              ...current.slice(-49),
              feedItem(sentence.source, sentence.message, sentence.level),
            ]);
          }
        } else if (
          (data as unknown as { kind?: string }).kind === "action_pending"
        ) {
          const payload = (
            data as unknown as { payload?: Record<string, unknown> }
          ).payload;
          if (payload) applyActionPayload(payload);
        } else if (
          (data as unknown as { kind?: string }).kind === "action_tick"
        ) {
          const payload = (
            data as unknown as { payload?: Record<string, unknown> }
          ).payload;
          if (payload) {
            const runId = payload.run_id;
            const unknown =
              typeof runId === "string" &&
              runId !== "" &&
              !knownRuns.current.has(runId);
            applyActionPayload(payload);
            if (unknown) void fetchRunDecision(runId);
          }
        } else if (
          (data as unknown as { kind?: string }).kind === "action_resolved"
        ) {
          const payload = (
            data as unknown as { payload?: Record<string, unknown> }
          ).payload;
          if (payload) {
            applyActionPayload(payload);
            const state = payload.state;
            if (typeof state === "string" && state !== "pending") {
              const summary =
                typeof payload.action === "string" ? payload.action : "action";
              setEvents((current) => [
                ...current.slice(-49),
                feedItem(
                  "veto",
                  state === "auto_applied"
                    ? `Auto-applied ✓ at 0s: ${summary}`
                    : state === "approved"
                      ? `Approved ✓: ${summary}`
                      : state === "disapproved"
                        ? `Disapproved — left for a human: ${summary}`
                        : `Veto window ${state}: ${summary}`,
                  state === "failed" ? "ERROR" : "INFO",
                ),
              ]);
            }
          }
        } else if (
          (data as unknown as { kind?: string }).kind === "fix_applied"
        ) {
          const domain = (
            data as unknown as { payload?: { domain?: unknown } }
          ).payload?.domain;
          const message =
            domain === "appliance"
              ? "Runbook applied to fridge"
              : "Fix applied to shop (merge and deploy)";
          setEvents((current) => [
            ...current.slice(-49),
            feedItem("fix", message, "INFO"),
          ]);
        } else if (typeof data.message === "string") {
          setEvents((current) => [...current.slice(-49), data]);
        }
      } catch {
        setError("Received an invalid event from the API.");
      }
    };
    return () => {
      disposed = true;
      window.clearTimeout(retry);
      socket.close();
    };
  }, [reconnectKey]);

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

  async function togglePairing() {
    if (pairUrl) {
      setPairUrl(null);
      return;
    }
    try {
      const response = await fetch(`${apiUrl}/api/pairing`);
      if (!response.ok) throw new Error(await responseDetail(response));
      const body = (await response.json()) as { api_url?: unknown };
      if (typeof body.api_url !== "string") {
        throw new Error("Pairing URL unavailable.");
      }
      setPairUrl(body.api_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pairing failed.");
    }
  }

  async function playScenario() {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/scenario/play`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      const body = (await response.json()) as { steps?: unknown };
      setScenario({
        playing: true,
        done: 0,
        total: typeof body.steps === "number" ? body.steps : 0,
        current: "starting",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not play scenario.");
    }
  }

  async function resetWorld() {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/reset`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(await responseDetail(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset.");
      return;
    }
    setSoftware(emptyIncident());
    setAppliance(emptyIncident());
    setVetoes({});
    fetchedRuns.current.clear();
    knownRuns.current.clear();
    setOrders([]);
    setErrorRates([]);
    setTrafficUntil(0);
    setFridgeTemps([]);
    setFridge(null);
    setScenario({ playing: false, done: 0, total: 0, current: "" });
  }

  async function startTraffic() {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/shop/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(TRAFFIC),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      setTrafficUntil(Date.now() + TRAFFIC.duration * 1000);
      setEvents((current) => [
        ...current.slice(-49),
        feedItem(
          "shop",
          `Traffic started: ${TRAFFIC.shoppers} shoppers for ${TRAFFIC.duration}s`,
          "INFO",
        ),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start traffic.");
    }
  }

  async function deployFix() {
    if (!software.runId) return;
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/shop/apply-fix`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: software.runId }),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      setSoftware((prev) => ({
        ...prev,
        final: `${prev.final}\nDeployed to shop; watch the error rate fall.`,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deploy failed.");
    }
  }

  async function applyRunbook() {
    if (!appliance.runId) return;
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/fridge/apply-runbook`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: appliance.runId }),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      const body = (await response.json()) as {
        applied?: unknown[];
        skipped?: unknown[];
      };
      const done = Array.isArray(body.applied) ? body.applied.length : 0;
      const skipped = Array.isArray(body.skipped) ? body.skipped.length : 0;
      setAppliance((prev) => ({
        ...prev,
        final: `${prev.final}\nRunbook applied (${done} steps, ${skipped} skipped); temperature recovering.`,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Runbook apply failed.");
    }
  }

  async function fridgeControl(
    path: "fault" | "action",
    body: { fault: string } | { action: string },
  ) {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/fridge/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      const snap = (await response.json()) as {
        temp_c?: unknown;
        door_open?: unknown;
        compressor_on?: unknown;
        condenser_dirty?: unknown;
        surge_active?: unknown;
        short_cycling?: unknown;
      };
      setFridge((prev) => ({
        temp_c: typeof snap.temp_c === "number" ? snap.temp_c : (prev?.temp_c ?? 0),
        current_a: prev?.current_a ?? 0,
        vibration_g: prev?.vibration_g ?? 0,
        door_open: snap.door_open === true,
        compressor_on: snap.compressor_on === true,
        condenser_dirty: snap.condenser_dirty === true,
        surge_active: snap.surge_active === true,
        short_cycling: snap.short_cycling === true,
      }));
      const name =
        "fault" in body ? body.fault : body.action;
      const sentence = FRIDGE_SENTENCES[name];
      if (sentence) {
        setEvents((current) => [
          ...current.slice(-49),
          feedItem("sim", sentence, "INFO"),
        ]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fridge control failed.");
    }
  }

  const shopOnline =
    shopMetrics !== null && now - shopMetrics.seenAt < SHOP_STALE_MS;
  const trafficLeft = Math.max(0, Math.ceil((trafficUntil - now) / 1000));
  const trafficSeen = errorRates.some((r) => r > 0) || (shopMetrics?.ordersPerMin ?? 0) > 0;
  const shopChecking = shopMetrics === null && now - mountedAt < SHOP_STALE_MS;
  const errorRate = shopMetrics?.errorRate ?? 0;
  const shopChip = shopChecking
    ? { tone: "", label: "checking shop" }
    : !shopOnline
      ? { tone: "fail", label: shopMetrics ? "shop offline" : "shop not seen" }
      : errorRate >= 0.2
        ? { tone: "fail", label: "orders failing" }
        : errorRate > 0
          ? { tone: "running", label: "degraded" }
          : { tone: "pass", label: `${orders.length} recent orders` };

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AUTONOMOUS SRE / LIVE INCIDENTS</p>
          <h1>Telemetry Agent</h1>
        </div>
        <div className="topbar-right">
          <button
            type="button"
            className="ghost small"
            onClick={() => void togglePairing()}
            title="Show a QR code to pair the mobile app"
          >
            Pair phone
          </button>
          <div className={`status ${connection}`}>
            <span className="status-dot" />
            {connection}
          </div>
        </div>
      </header>

      {pairUrl ? (
        <section className="panel map-panel pair-panel">
          <div className="pair-qr">
            <QRCodeSVG value={JSON.stringify({ api: pairUrl })} size={140} />
            <div>
              <p className="eyebrow">MOBILE PAIRING</p>
              <p className="mono">{pairUrl}</p>
              <p className="mapempty">
                Same Wi-Fi as this machine (API_HOST=0.0.0.0), then type the
                mobile token from .env into the app.
              </p>
            </div>
          </div>
        </section>
      ) : null}

      <section className="panel map-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">SCENARIO</p>
            <h2>One-click demo</h2>
          </div>
          <span className="counter">
            {scenario.playing
              ? `step ${scenario.done}/${scenario.total} · ${scenario.current}`
              : scenario.total > 0
                ? `done ${scenario.done}/${scenario.total}`
                : "idle"}
          </span>
        </div>
        <div className="controls scenario-controls">
          <button
            type="button"
            onClick={playScenario}
            disabled={scenario.playing}
          >
            Play scenario
          </button>
          <button type="button" className="ghost" onClick={resetWorld}>
            Reset
          </button>
        </div>
      </section>

      <section className="panel map-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">WORLD</p>
            <h2>Service map</h2>
          </div>
          <span className={`chip ${shopChip.tone}`}>{shopChip.label}</span>
        </div>
        <div className="controls map-controls">
          <button
            type="button"
            onClick={startTraffic}
            disabled={!shopOnline || trafficLeft > 0}
          >
            {trafficLeft > 0 ? `Traffic running · ${trafficLeft}s` : "Start traffic"}
          </button>
          <span className="hint">
            {TRAFFIC.shoppers} shoppers · {TRAFFIC.rate} orders/s · {TRAFFIC.duration}s
          </span>
        </div>
        {shopMetrics && shopOnline && (
          <div className="shop-metrics">
            <div>
              <span>Orders / min</span>
              <strong>{Math.round(shopMetrics.ordersPerMin)}</strong>
            </div>
            <div className={errorTone(shopMetrics.errorRate)}>
              <span>Error rate</span>
              <strong>{Math.round(shopMetrics.errorRate * 100)}%</strong>
            </div>
            <div>
              <span>p95 latency</span>
              <strong>{Math.round(shopMetrics.p95Ms)} ms</strong>
            </div>
            <div className="spark-cell">
              <span>Error rate, last 60s</span>
              <Sparkline values={errorRates} />
            </div>
          </div>
        )}
        {shopChecking ? (
          <p className="mapempty">Checking the shop…</p>
        ) : !shopOnline ? (
          <p className="mapempty">
            Shop is not running. Start everything with <code>./scripts/demo.sh</code>.
          </p>
        ) : orders.length === 0 && !trafficSeen ? (
          <p className="mapempty">
            No traffic yet. Press Start traffic, or Play scenario above.
          </p>
        ) : (
          <ServiceMap orders={orders} />
        )}
      </section>

      <section className="panel map-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">WORLD</p>
            <h2>Virtual fridge</h2>
          </div>
          <span className="counter">
            {fridge ? `${fridge.temp_c.toFixed(1)}°C` : "stream idle"}
          </span>
        </div>
        <VirtualFridge
          temps={fridgeTemps}
          state={fridge}
          onFault={(fault) => void fridgeControl("fault", { fault })}
          onAction={(action) => void fridgeControl("action", { action })}
        />
      </section>

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
            <div className="controls">
              <button
                type="button"
                onClick={deployFix}
                disabled={software.status !== "PASS" || !software.runId}
                title="Deploy the verified patch to the demo shop"
              >
                Deploy verified fix
              </button>
            </div>
            <PipelineLane
              labels={["Crash", "Grab", "Suggest", "Verify", "Fix"]}
              {...laneProps(software)}
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
            <VetoStrip veto={vetoFor(vetoes, "software", software.runId)} now={now} />
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
            <div className="controls">
              <button
                type="button"
                onClick={applyRunbook}
                disabled={appliance.status !== "PASS" || !appliance.runId}
                title="Technician applies the validated runbook to the fridge"
              >
                Technician applies runbook
              </button>
            </div>
            <PipelineLane
              labels={["Crash", "Grab", "Suggest", "Safety", "Fix"]}
              {...laneProps(appliance)}
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
            <VetoStrip veto={vetoFor(vetoes, "appliance", appliance.runId)} now={now} />
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
                <p>
                  {item.tag ? <span className="tag">{item.tag}</span> : null}
                  {item.message}
                </p>
              </article>
            ))
          )}
        </div>
      </section>

      <footer>
        <a href="/shop">Shop demo →</a> · Local-first telemetry · API {apiUrl}
      </footer>
    </main>
  );
}
