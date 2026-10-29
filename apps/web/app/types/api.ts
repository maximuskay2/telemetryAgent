// Typed API + socket contracts (S3). Hand-written from the Pydantic models;
// keep in sync with core/schemas/* and the SimEvent kinds in apps/api/main.py.

export type AgentStepEvent = {
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

export type LogEvent = {
  id: string;
  timestamp: string;
  source: string;
  message: string;
  level: string;
  tag?: string;
};

export type VetoAction = {
  runId: string;
  domain: string;
  summary: string;
  deadlineMs: number;
  secondsLeft: number;
  state: string;
  decidedBy: string;
  detail: string;
};

export type IncidentState = {
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

export type ShopMetrics = {
  ordersPerMin: number;
  errorRate: number;
  p95Ms: number;
  seenAt: number;
};

export type ScenarioState = {
  playing: boolean;
  done: number;
  total: number;
  current: string;
};

export type SystemSummary = {
  system_id: string;
  name: string;
  status: string;
  kind: string;
};

export type OrderStatus = "ok" | "waiting" | "failed";

export type GateCheck = {
  name: string;
  result: string;
  detail: string;
};

export type GateDecision = {
  decision: string;
  reason: string;
  citation: string;
  checks: GateCheck[];
  system_id: string;
  fingerprint: string;
  rule: string;
  signature: string;
  recheck_in_s: number;
  ts: number;
};

export type PendingAction = {
  run_id: string;
  domain: string;
  action: string;
  opened_at: number;
  deadline: number;
  state: string;
  decided_by: string | null;
  resolved_at: number | null;
  detail: string;
  auto_apply: boolean;
};

export type VerifySide = { passed: boolean; output: string };

export type RunVerification = {
  target: string;
  original_code: string | null;
  test_code: string | null;
  original: VerifySide | null;
  patched: VerifySide | null;
  runner: string | null;
};

export type RunDetail = {
  run_id: string;
  domain: string;
  result: Record<string, unknown>;
  steps: Record<string, unknown>[];
  decision: Record<string, unknown> | null;
  gate: Record<string, unknown> | null;
  verification: RunVerification | null;
};

/** Every socket frame, validated once at the socket boundary. */
export type StreamEvent =
  | { type: "step"; event: AgentStepEvent }
  | { type: "log"; event: LogEvent }
  | {
      type: "shop_order";
      payload: { order_id: string; status: string; items: string[] };
    }
  | {
      type: "shop_metrics";
      payload: { orders_per_min: number; error_rate: number; p95_ms: number };
    }
  | {
      type: "fridge_reading";
      payload: {
        temperature_c: number;
        current_a: number;
        vibration_g: number;
        door_open: boolean;
        compressor_on: boolean;
        condenser_dirty: boolean;
        surge_active: boolean;
        short_cycling: boolean;
        defrost_active: boolean;
      };
    }
  | {
      type: "scenario_step";
      payload: { done: number; total: number; action: string };
    }
  | {
      type: "watcher_trigger";
      payload: {
        rule: string;
        level: string;
        domain: string;
        resource: string;
        matched_lines: string[];
      };
    }
  | { type: "action_pending"; payload: Record<string, unknown> }
  | { type: "action_tick"; payload: Record<string, unknown> }
  | { type: "action_resolved"; payload: Record<string, unknown> }
  | { type: "fix_applied"; payload: { domain: string } }
  | { type: "gate_decision"; payload: GateDecision }
  | {
      type: "setup_progress";
      payload: {
        stage: string;
        system_id: string;
        doc: string;
        fallback: boolean;
      };
    }
  | {
      type: "baseline_progress";
      payload: {
        system_id: string;
        percent: number;
        patterns: number;
        stage: string;
        reason: string;
      };
    };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" ? value : fallback;
}

function strArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}

export function toGateDecision(input: unknown): GateDecision | null {
  if (!isRecord(input) || typeof input.decision !== "string") return null;
  const checks = Array.isArray(input.checks)
    ? input.checks
        .filter((c): c is Record<string, unknown> => isRecord(c))
        .map((c) => ({
          name: str(c.name),
          result: str(c.result),
          detail: str(c.detail),
        }))
    : [];
  return {
    decision: input.decision,
    reason: str(input.reason),
    citation: str(input.citation),
    checks,
    system_id: str(input.system_id),
    fingerprint: str(input.fingerprint),
    rule: str(input.rule),
    signature: str(input.signature),
    recheck_in_s: num(input.recheck_in_s),
    ts: typeof input.ts === "number" ? input.ts : Date.now() / 1000,
  };
}

function asStep(data: Record<string, unknown>): AgentStepEvent | null {
  if (
    typeof data.step !== "string" ||
    (data.domain !== "software" && data.domain !== "appliance")
  ) {
    return null;
  }
  return {
    step: data.step,
    attempt: num(data.attempt),
    model: str(data.model),
    status: str(data.status),
    message: str(data.message),
    duration_ms: num(data.duration_ms),
    run_id: str(data.run_id),
    domain: data.domain,
    detail: str(data.detail),
    source: str(data.source),
    suggestions: strArray(data.suggestions),
  };
}

/** Validate one socket frame. Returns null for unknown-but-valid frames. */
export function parseEvent(data: unknown): StreamEvent | null {
  if (!isRecord(data)) return null;
  const step = asStep(data);
  if (step) return { type: "step", event: step };
  const kind = data.kind;
  const payload = isRecord(data.payload) ? data.payload : null;
  switch (kind) {
    case "shop_order": {
      if (!payload || typeof payload.order_id !== "string") return null;
      const status = str(payload.status);
      return {
        type: "shop_order",
        payload: {
          order_id: payload.order_id,
          status: status === "failed" || status === "waiting" ? status : "ok",
          items: strArray(payload.items),
        },
      };
    }
    case "shop_metrics": {
      if (
        !payload ||
        typeof payload.orders_per_min !== "number" ||
        typeof payload.error_rate !== "number" ||
        typeof payload.p95_ms !== "number"
      ) {
        return null;
      }
      return {
        type: "shop_metrics",
        payload: {
          orders_per_min: payload.orders_per_min,
          error_rate: payload.error_rate,
          p95_ms: payload.p95_ms,
        },
      };
    }
    case "fridge_reading": {
      const reading = payload && isRecord(payload.reading) ? payload.reading : null;
      const st = payload && isRecord(payload.state) ? payload.state : null;
      if (
        !reading ||
        typeof reading.temperature_c !== "number" ||
        typeof reading.current_a !== "number" ||
        typeof reading.vibration_g !== "number"
      ) {
        return null;
      }
      return {
        type: "fridge_reading",
        payload: {
          temperature_c: reading.temperature_c,
          current_a: reading.current_a,
          vibration_g: reading.vibration_g,
          door_open: st?.door_open === true,
          compressor_on: st?.compressor_on === true,
          condenser_dirty: st?.condenser_dirty === true,
          surge_active: st?.surge_active === true,
          short_cycling: st?.short_cycling === true,
          defrost_active: st?.defrost_active === true,
        },
      };
    }
    case "scenario_step": {
      if (
        !payload ||
        typeof payload.done !== "number" ||
        typeof payload.total !== "number"
      ) {
        return null;
      }
      return {
        type: "scenario_step",
        payload: { done: payload.done, total: payload.total, action: str(payload.action) },
      };
    }
    case "watcher_trigger": {
      if (!payload || typeof payload.rule !== "string") return null;
      return {
        type: "watcher_trigger",
        payload: {
          rule: payload.rule,
          level: str(payload.level),
          domain: str(payload.domain),
          resource: str(payload.resource),
          matched_lines: strArray(payload.matched_lines),
        },
      };
    }
    case "action_pending":
    case "action_tick":
    case "action_resolved": {
      if (!payload) return null;
      return { type: kind, payload };
    }
    case "fix_applied":
      return { type: "fix_applied", payload: { domain: payload ? str(payload.domain) : "" } };
    case "gate_decision": {
      const decision = toGateDecision(payload);
      if (!decision) return null;
      return { type: "gate_decision", payload: decision };
    }
    case "setup_progress":
      return {
        type: "setup_progress",
        payload: {
          stage: payload ? str(payload.stage) : "",
          system_id: payload ? str(payload.system_id) : "",
          doc: payload ? str(payload.doc) : "",
          fallback: payload ? payload.fallback === true : false,
        },
      };
    case "baseline_progress": {
      if (!payload) return null;
      return {
        type: "baseline_progress",
        payload: {
          system_id: str(payload.system_id),
          percent: num(payload.percent),
          patterns: num(payload.patterns),
          stage: str(payload.stage),
          reason: str(payload.reason),
        },
      };
    }
    default:
      break;
  }
  if (typeof data.message === "string") {
    return {
      type: "log",
      event: {
        id: str(data.id, `${Date.now().toString(36)}-rx`),
        timestamp: str(data.timestamp, new Date().toISOString()),
        source: str(data.source, "log"),
        message: data.message,
        level: str(data.level, "INFO"),
        tag: typeof data.tag === "string" ? data.tag : undefined,
      },
    };
  }
  return null;
}
