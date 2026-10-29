"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { apiUrl, responseDetail } from "../lib/api";
import type { IncidentState, LogEvent, StreamEvent, VetoAction } from "../types/api";
import { useActions } from "../hooks/useActions";
import { useAgentStream } from "../hooks/useAgentStream";
import { feedItem, FRIDGE_SENTENCES, useFeed, watcherFeed } from "../hooks/useFeed";
import { useGate, type GateCounts } from "../hooks/useGate";
import { useIncidentList, type IncidentEntry } from "../hooks/useIncidentList";
import { useIncidents, emptyIncident } from "../hooks/useIncidents";
import { useSimState } from "../hooks/useSimState";
import { useSystems } from "../hooks/useSystems";
import type { OrderDot } from "../components/ServiceMap";
import type { FridgeState } from "../components/VirtualFridge";
import type { GateDecision, ScenarioState, ShopMetrics, SystemSummary } from "../types/api";

const TOKEN_KEY = "mission.operatorToken";

function shortModel(model: string, step: string): string | null {
  if (step === "verify") return "Sandbox";
  if (model.includes("muse-spark")) return "Muse Spark";
  if (model.includes("muse-wonder")) return "Wonder";
  if (model.startsWith("baseten:") || model.startsWith("fireworks:")) return "Spark Open";
  return null;
}

export type Toast = { id: number; text: string; tone: "info" | "ok" | "subtle" };

export type MissionState = {
  connection: string;
  error: string;
  software: IncidentState;
  appliance: IncidentState;
  incidentList: IncidentEntry[];
  events: LogEvent[];
  orders: OrderDot[];
  shopMetrics: ShopMetrics | null;
  errorRates: number[];
  fridgeTemps: number[];
  fridgeDefrost: boolean[];
  fridge: FridgeState | null;
  scenario: ScenarioState;
  trafficUntil: number;
  deployUntil: number;
  now: number;
  decisions: GateDecision[];
  counts: GateCounts;
  vetoes: Record<string, VetoAction>;
  systems: SystemSummary[];
  systemsLoaded: boolean;
  baselinePct: Record<string, number>;
  warnFixMs: number | null;
  runningModels: string[];
  operatorToken: string;
  setOperatorToken: (token: string) => void;
  tokenOpen: boolean;
  setTokenOpen: (open: boolean) => void;
  selectedRunId: string | null;
  setSelectedRunId: (runId: string | null) => void;
  soundOn: boolean;
  setSoundOn: (on: boolean) => void;
  focusMode: boolean;
  setFocusMode: (on: boolean) => void;
  presenterMode: boolean;
  setPresenterMode: (on: boolean) => void;
  toasts: Toast[];
  pushToast: (text: string, tone?: Toast["tone"]) => void;
  dismissToast: (id: number) => void;
  authHeaders: () => Record<string, string>;
  playScenario: () => void;
  resetWorld: () => void;
  startTraffic: () => void;
  deployShop: () => void;
  fridgeControl: (path: "fault" | "action", body: { fault: string } | { action: string }) => void;
  fridgeBehaviour: (behaviour: string, body?: Record<string, unknown>) => void;
  injectSoftware: (logText: string, target: string) => void;
  injectAppliance: (applianceType: string, fault: string) => void;
  markNormal: (runId: string, domain: "software" | "appliance") => void;
  applyFix: (runId: string) => void;
  applyRunbook: (runId: string) => void;
};

export const MissionContext = createContext<MissionState | null>(null);

export function useMission(): MissionState {
  const state = useContext(MissionContext);
  if (!state) throw new Error("useMission must be used inside MissionProvider");
  return state;
}

export function MissionProvider({ children }: { children: ReactNode }) {
  const incidents = useIncidents();
  const incidentList = useIncidentList();
  const feed = useFeed();
  const sim = useSimState();
  const gate = useGate();
  const actions = useActions();
  const systems = useSystems();
  const [error, setError] = useState("");
  const [baselinePct, setBaselinePct] = useState<Record<string, number>>({});
  const [warnFixMs, setWarnFixMs] = useState<number | null>(null);
  const [runningModels, setRunningModels] = useState<string[]>([]);
  const warnTs = useRef<number | null>(null);
  const activeModels = useRef<Map<string, Set<string>>>(new Map());
  const [operatorToken, setOperatorTokenState] = useState("");
  const [tokenOpen, setTokenOpen] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [soundOn, setSoundOn] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [presenterMode, setPresenterMode] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);
  const lastErrorRate = useRef(0);

  useEffect(() => {
    try {
      setOperatorTokenState(window.sessionStorage.getItem(TOKEN_KEY) ?? "");
    } catch {
      // Private mode: token just won't persist.
    }
  }, []);

  // Preconnect the API host once per load.
  useEffect(() => {
    if (document.querySelector('link[data-mission-preconnect]')) return;
    const link = document.createElement("link");
    link.rel = "preconnect";
    link.href = apiUrl;
    link.setAttribute("data-mission-preconnect", "1");
    document.head.appendChild(link);
  }, []);

  const setOperatorToken = useCallback((token: string) => {
    setOperatorTokenState(token);
    try {
      if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
      else window.sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      // ignore persistence failures
    }
  }, []);

  const authHeaders = useCallback(
    (): Record<string, string> =>
      operatorToken ? { "X-Mobile-Token": operatorToken } : {},
    [operatorToken],
  );

  const pushToast = useCallback((text: string, tone: Toast["tone"] = "info") => {
    toastId.current += 1;
    const id = toastId.current;
    setToasts((current) => [...current.slice(-3), { id, text, tone }]);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const noteStepModel = useCallback((runId: string, model: string, step: string) => {
    if (step === "done") {
      activeModels.current.delete(runId || step);
    } else {
      const label = shortModel(model, step);
      if (label) {
        const key = runId || step;
        const set = activeModels.current.get(key) ?? new Set<string>();
        set.add(label);
        activeModels.current.set(key, set);
      }
    }
    const union = new Set<string>();
    for (const set of activeModels.current.values()) {
      for (const label of set) union.add(label);
    }
    setRunningModels([...union]);
  }, []);

  const handleEvent = useCallback(
    (event: StreamEvent) => {
      switch (event.type) {
        case "step": {
          feed.push(incidents.applyAgentStep(event.event));
          incidentList.applyListStep(event.event);
          noteStepModel(event.event.run_id, event.event.model, event.event.step);
          if (
            event.event.step === "verify" &&
            (event.event.status === "ok" || event.event.status === "PASS")
          ) {
            pushToast(`Verified ✓ ${event.event.run_id.slice(0, 8)}`, "ok");
          }
          if (
            event.event.step === "done" &&
            (event.event.status === "PASS" || event.event.status === "NO_ACTION") &&
            warnTs.current !== null
          ) {
            setWarnFixMs(Date.now() - warnTs.current);
          }
          if (
            event.event.step === "done" &&
            event.event.status === "PASS" &&
            event.event.message.includes("http")
          ) {
            pushToast("PR opened ↗", "ok");
          }
          break;
        }
        case "shop_order":
          sim.applyShopOrder(event.payload);
          break;
        case "shop_metrics": {
          sim.applyShopMetrics(event.payload);
          const rate = event.payload.error_rate;
          if (lastErrorRate.current > 0.05 && rate === 0) {
            pushToast("Shop recovered ✓", "ok");
          }
          lastErrorRate.current = rate;
          break;
        }
        case "fridge_reading":
          sim.applyFridgeReading(event.payload);
          break;
        case "scenario_step":
          feed.push(sim.applyScenarioStep(event.payload));
          break;
        case "watcher_trigger":
          feed.push(watcherFeed(event.payload));
          warnTs.current = Date.now();
          pushToast(`Incident grabbed: ${event.payload.rule || "watcher"}`, "info");
          break;
        case "action_pending":
          actions.applyActionPayload(event.payload);
          break;
        case "action_tick":
          actions.applyActionTick(event.payload);
          break;
        case "action_resolved":
          feed.push(actions.applyActionResolved(event.payload));
          break;
        case "fix_applied":
          feed.push(
            feedItem(
              "fix",
              event.payload.domain === "appliance"
                ? "Runbook applied to fridge"
                : "Fix applied to shop (merge and deploy)",
              "INFO",
            ),
          );
          if (warnTs.current !== null) {
            setWarnFixMs(Date.now() - warnTs.current);
            warnTs.current = null;
          }
          break;
        case "gate_decision":
          feed.push(gate.applyGateDecision(event.payload));
          if (event.payload.decision === "suppress") {
            pushToast(`Ignored: ${event.payload.rule || "gate"}`, "subtle");
          }
          break;
        case "setup_progress":
          if (
            event.payload.stage === "confirmed" ||
            event.payload.stage === "armed" ||
            event.payload.stage === "disarmed" ||
            event.payload.stage === "deleted"
          ) {
            systems.refreshSystems();
          }
          break;
        case "baseline_progress":
          if (event.payload.system_id) {
            const pct = Math.round(event.payload.percent);
            setBaselinePct((current) =>
              current[event.payload.system_id] === pct
                ? current
                : { ...current, [event.payload.system_id]: pct },
            );
          }
          break;
        case "log":
          feed.push(event.event);
          break;
      }
    },
    [incidents, incidentList, feed, sim, gate, actions, systems, noteStepModel, pushToast],
  );

  const { connection } = useAgentStream({ onEvent: handleEvent, onError: setError });

  const playScenario = useCallback(async () => {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/scenario/play`, { method: "POST" });
      if (!response.ok) throw new Error(await responseDetail(response));
      const body = (await response.json()) as { steps?: unknown };
      sim.setScenario({
        playing: true,
        done: 0,
        total: typeof body.steps === "number" ? body.steps : 0,
        current: "starting",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not play scenario.");
    }
  }, [sim]);

  const startTraffic = useCallback(async () => {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/shop/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shoppers: 8, rate: 20, duration: 60 }),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      sim.setTrafficUntil(Date.now() + 60000);
      feed.push(feedItem("shop", "Traffic started: 8 shoppers for 60s", "INFO"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start traffic.");
    }
  }, [sim, feed]);

  const deployShop = useCallback(async () => {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/shop/deploy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_s: 20 }),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      sim.setDeployUntil(Date.now() + 20000);
      feed.push(feedItem("sim", "Shop deploy started (drain retries expected)", "INFO"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deploy failed.");
    }
  }, [sim, feed]);

  const fridgeControl = useCallback(
    async (path: "fault" | "action", body: { fault: string } | { action: string }) => {
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
          defrost_active?: unknown;
        };
        sim.setFridge((prev) => ({
          temp_c: typeof snap.temp_c === "number" ? snap.temp_c : (prev?.temp_c ?? 0),
          current_a: prev?.current_a ?? 0,
          vibration_g: prev?.vibration_g ?? 0,
          door_open: snap.door_open === true,
          compressor_on: snap.compressor_on === true,
          condenser_dirty: snap.condenser_dirty === true,
          surge_active: snap.surge_active === true,
          short_cycling: snap.short_cycling === true,
          defrost_active: snap.defrost_active === true,
        }));
        const name = "fault" in body ? body.fault : body.action;
        const sentence = FRIDGE_SENTENCES[name];
        if (sentence) feed.push(feedItem("sim", sentence, "INFO"));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Fridge control failed.");
      }
    },
    [sim, feed],
  );

  const fridgeBehaviour = useCallback(
    async (behaviour: string, body?: Record<string, unknown>) => {
      setError("");
      try {
        const payload =
          body ??
          (behaviour === "restock" ? { ticks: 1 } : { duration_ticks: 20 });
        const response = await fetch(`${apiUrl}/api/sim/fridge/${behaviour}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error(await responseDetail(response));
        feed.push(
          feedItem(
            "sim",
            behaviour === "restock"
              ? "Fridge door opened for restocking"
              : behaviour === "ambient"
                ? `Ambient heat ${payload.hot === false ? "off" : "on"}`
                : "Fridge defrost cycle started",
            "INFO",
          ),
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Behaviour failed.");
      }
    },
    [feed],
  );

  const injectSoftware = useCallback(
    async (logText: string, target: string) => {
      const text = logText.trim();
      if (!text) {
        setError("Paste or upload a log first.");
        return;
      }
      const seeded: IncidentEntry = {
        ...emptyIncident(),
        runId: `pending-${Date.now().toString(36)}`,
        domain: "software",
        status: "running",
        telemetry: text.slice(0, 500),
        source: "upload",
        startedAt: Date.now(),
        activity: "Submitting log…",
      };
      incidentList.seed(seeded);
      incidents.setSoftware({ ...seeded });
      setError("");
      try {
        const clean = target.trim();
        const response = await fetch(`${apiUrl}/api/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            log_text: text,
            source: "upload",
            ...(clean ? { target_path: clean } : {}),
          }),
        });
        if (!response.ok) throw new Error(await responseDetail(response));
        const result = (await response.json()) as {
          status?: unknown;
          run_id?: unknown;
          pr_url?: unknown;
          stderr?: unknown;
          model_used?: unknown;
        };
        const runId = typeof result.run_id === "string" ? result.run_id : seeded.runId;
        incidentList.patch(seeded.runId, {
          runId,
          status: typeof result.status === "string" ? result.status : "running",
          activity: "Diagnosing…",
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Could not inject incident.";
        setError(message);
        incidentList.patch(seeded.runId, { status: "error", final: message });
      }
    },
    [incidentList, incidents],
  );

  const injectAppliance = useCallback(
    async (applianceType: string, fault: string) => {
      const telemetry = `${applianceType} · fault=${fault} · 30 synthetic readings`;
      const seeded: IncidentEntry = {
        ...emptyIncident(),
        runId: `pending-${Date.now().toString(36)}`,
        domain: "appliance",
        status: "running",
        telemetry,
        source: "upload",
        startedAt: Date.now(),
        activity: "Submitting readings…",
      };
      incidentList.seed(seeded);
      incidents.setAppliance({ ...seeded });
      setError("");
      try {
        const response = await fetch(`${apiUrl}/api/run/appliance`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ appliance_type: applianceType, fault, source: "upload" }),
        });
        if (!response.ok) throw new Error(await responseDetail(response));
        const result = (await response.json()) as { status?: unknown; run_id?: unknown };
        incidentList.patch(seeded.runId, {
          runId: typeof result.run_id === "string" ? result.run_id : seeded.runId,
          status: typeof result.status === "string" ? result.status : "running",
          activity: "Diagnosing…",
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Could not inject incident.";
        setError(message);
        incidentList.patch(seeded.runId, { status: "error", final: message });
      }
    },
    [incidentList, incidents],
  );

  const markNormal = useCallback(
    async (runId: string, _domain: "software" | "appliance") => {
      void _domain;
      if (!runId || runId.startsWith("pending-")) return;
      setError("");
      try {
        const detail = await fetch(`${apiUrl}/api/runs/${runId}`);
        if (!detail.ok) throw new Error(await responseDetail(detail));
        const body = (await detail.json()) as {
          gate?: {
            system_id?: string;
            fingerprint?: string;
            signature?: string;
            rule?: string;
          };
        };
        const gateCtx = body.gate;
        if (!gateCtx?.system_id || !gateCtx.fingerprint || !gateCtx.signature) {
          throw new Error("This run has no gate context to mark normal.");
        }
        const response = await fetch(`${apiUrl}/api/systems/${gateCtx.system_id}/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            fingerprint: gateCtx.fingerprint,
            signature: gateCtx.signature,
            rule: gateCtx.rule ?? "",
            created_by: "dashboard",
          }),
        });
        if (!response.ok) throw new Error(await responseDetail(response));
        incidentList.patch(runId, {
          final: "Parked as “normal” — confirm it in setup review.",
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Mark-normal failed.");
      }
    },
    [incidentList],
  );

  const applyFix = useCallback(
    async (runId: string) => {
      if (!runId || runId.startsWith("pending-")) return;
      setError("");
      try {
        const response = await fetch(`${apiUrl}/api/sim/shop/apply-fix`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ run_id: runId }),
        });
        if (!response.ok) throw new Error(await responseDetail(response));
        incidentList.patch(runId, {
          final: "Deployed to shop; watch the error rate fall.",
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Deploy failed.");
      }
    },
    [authHeaders, incidentList],
  );

  const applyRunbook = useCallback(
    async (runId: string) => {
      if (!runId || runId.startsWith("pending-")) return;
      setError("");
      try {
        const response = await fetch(`${apiUrl}/api/sim/fridge/apply-runbook`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ run_id: runId }),
        });
        if (!response.ok) throw new Error(await responseDetail(response));
        const body = (await response.json()) as { applied?: unknown[]; skipped?: unknown[] };
        const done = Array.isArray(body.applied) ? body.applied.length : 0;
        const skipped = Array.isArray(body.skipped) ? body.skipped.length : 0;
        incidentList.patch(runId, {
          final: `Runbook applied (${done} steps, ${skipped} skipped); temperature recovering.`,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Runbook apply failed.");
      }
    },
    [authHeaders, incidentList],
  );

  const resetWorld = useCallback(async () => {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/reset`, { method: "POST" });
      if (!response.ok) throw new Error(await responseDetail(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset.");
      return;
    }
    incidents.reset();
    incidentList.reset();
    actions.reset();
    sim.reset();
    gate.reset();
    feed.reset();
    warnTs.current = null;
    activeModels.current.clear();
    setWarnFixMs(null);
    setRunningModels([]);
    setBaselinePct({});
    setSelectedRunId(null);
    setToasts([]);
    lastErrorRate.current = 0;
  }, [incidents, incidentList, actions, sim, gate, feed]);

  const value = useMemo<MissionState>(
    () => ({
      connection,
      error,
      software: incidents.software,
      appliance: incidents.appliance,
      incidentList: incidentList.entries,
      events: feed.events,
      orders: sim.orders,
      shopMetrics: sim.shopMetrics,
      errorRates: sim.errorRates,
      fridgeTemps: sim.fridgeTemps,
      fridgeDefrost: sim.fridgeDefrost,
      fridge: sim.fridge,
      scenario: sim.scenario,
      trafficUntil: sim.trafficUntil,
      deployUntil: sim.deployUntil,
      now: sim.now,
      decisions: gate.decisions,
      counts: gate.counts,
      vetoes: actions.vetoes,
      systems: systems.systems,
      systemsLoaded: systems.systemsLoaded,
      baselinePct,
      warnFixMs,
      runningModels,
      operatorToken,
      setOperatorToken,
      tokenOpen,
      setTokenOpen,
      selectedRunId,
      setSelectedRunId,
      soundOn,
      setSoundOn,
      focusMode,
      setFocusMode,
      presenterMode,
      setPresenterMode,
      toasts,
      pushToast,
      dismissToast,
      authHeaders,
      playScenario,
      resetWorld,
      startTraffic,
      deployShop,
      fridgeControl,
      fridgeBehaviour,
      injectSoftware,
      injectAppliance,
      markNormal,
      applyFix,
      applyRunbook,
    }),
    [
      connection, error, incidents, incidentList.entries, feed.events, sim, gate, actions.vetoes,
      systems, baselinePct, warnFixMs, runningModels, operatorToken,
      setOperatorToken, tokenOpen, selectedRunId, soundOn, focusMode, presenterMode,
      toasts, pushToast, dismissToast, authHeaders, playScenario, resetWorld,
      startTraffic, deployShop, fridgeControl, fridgeBehaviour,
      injectSoftware, injectAppliance, markNormal, applyFix, applyRunbook,
    ],
  );

  return <MissionContext.Provider value={value}>{children}</MissionContext.Provider>;
}
