"use client";

import { useCallback, useEffect, useState } from "react";
import type { ChangeEvent, ReactElement } from "react";
import ServiceMap from "../components/ServiceMap";
import PipelineLane from "../components/PipelineLane";
import VirtualFridge from "../components/VirtualFridge";
import { QRCodeSVG } from "qrcode.react";
import Sparkline from "../components/Sparkline";
import { apiUrl, responseDetail } from "../lib/api";
import type { StreamEvent, VetoAction } from "../types/api";
import { useActions } from "../hooks/useActions";
import { useAgentStream } from "../hooks/useAgentStream";
import { feedItem, FRIDGE_SENTENCES, useFeed, watcherFeed } from "../hooks/useFeed";
import { emptyIncident, laneProps, useIncidents } from "../hooks/useIncidents";
import { useGate } from "../hooks/useGate";
import { useSimState } from "../hooks/useSimState";
import { useSystems } from "../hooks/useSystems";

// The shop publishes metrics every second; no metrics for this long means it is down.
const SHOP_STALE_MS = 5000;
const TRAFFIC = { shoppers: 8, rate: 20, duration: 60 };

function errorTone(rate: number): string {
  if (rate >= 0.2) return "bad";
  if (rate > 0) return "warn";
  return "good";
}

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

export default function ClassicDashboard() {
  const { software, appliance, setSoftware, setAppliance, applyAgentStep, reset: resetIncidents } =
    useIncidents();
  const { events, push } = useFeed();
  const {
    orders,
    fridgeTemps,
    fridge,
    setFridge,
    scenario,
    setScenario,
    shopMetrics,
    errorRates,
    trafficUntil,
    setTrafficUntil,
    deployUntil,
    setDeployUntil,
    now,
    mountedAt,
    applyShopOrder,
    applyShopMetrics,
    applyFridgeReading,
    applyScenarioStep,
    reset: resetSim,
  } = useSimState();
  const { vetoes, applyActionPayload, applyActionTick, applyActionResolved, reset: resetActions } =
    useActions();
  const { applyGateDecision } = useGate();
  const { systems, systemsLoaded, refreshSystems } = useSystems();

  const [applianceType, setApplianceType] = useState("fridge");
  const [fault, setFault] = useState("door_open");
  const [logText, setLogText] = useState(DEADLOCK_SAMPLE);
  const [targetFile, setTargetFile] = useState("inventory.py");
  const [trimNotice, setTrimNotice] = useState("");
  const [pairUrl, setPairUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  const handleEvent = useCallback(
    (event: StreamEvent) => {
      switch (event.type) {
        case "step":
          push(applyAgentStep(event.event));
          break;
        case "shop_order":
          applyShopOrder(event.payload);
          break;
        case "shop_metrics":
          applyShopMetrics(event.payload);
          break;
        case "fridge_reading":
          applyFridgeReading(event.payload);
          break;
        case "scenario_step":
          push(applyScenarioStep(event.payload));
          break;
        case "watcher_trigger":
          push(watcherFeed(event.payload));
          break;
        case "action_pending":
          applyActionPayload(event.payload);
          break;
        case "action_tick":
          applyActionTick(event.payload);
          break;
        case "action_resolved":
          push(applyActionResolved(event.payload));
          break;
        case "fix_applied":
          push(
            feedItem(
              "fix",
              event.payload.domain === "appliance"
                ? "Runbook applied to fridge"
                : "Fix applied to shop (merge and deploy)",
              "INFO",
            ),
          );
          break;
        case "gate_decision":
          push(applyGateDecision(event.payload));
          break;
        case "setup_progress":
          if (event.payload.stage === "confirmed" || event.payload.stage === "armed") {
            refreshSystems();
          }
          break;
        case "baseline_progress":
          break;
        case "log":
          push(event.event);
          break;
      }
    },
    [
      applyAgentStep,
      applyShopOrder,
      applyShopMetrics,
      applyFridgeReading,
      applyScenarioStep,
      applyActionPayload,
      applyActionTick,
      applyActionResolved,
      applyGateDecision,
      refreshSystems,
      push,
    ],
  );

  const { connection } = useAgentStream({
    onEvent: handleEvent,
    onError: setError,
  });

  // Fresh installs open on the Setup wizard; nothing auto-fixes until armed.
  useEffect(() => {
    if (systemsLoaded && systems.length === 0) {
      window.location.replace("/setup");
    }
  }, [systemsLoaded, systems]);

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
    resetIncidents();
    resetActions();
    resetSim();
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
      push(
        feedItem(
          "shop",
          `Traffic started: ${TRAFFIC.shoppers} shoppers for ${TRAFFIC.duration}s`,
          "INFO",
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start traffic.");
    }
  }

  async function markNormal(runId: string, domain: "software" | "appliance") {
    if (!runId) return;
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
      const gate = body.gate;
      if (!gate?.system_id || !gate.fingerprint || !gate.signature) {
        throw new Error("This run has no gate context to mark normal.");
      }
      const response = await fetch(
        `${apiUrl}/api/systems/${gate.system_id}/feedback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            fingerprint: gate.fingerprint,
            signature: gate.signature,
            rule: gate.rule ?? "",
            created_by: "dashboard",
          }),
        },
      );
      if (!response.ok) throw new Error(await responseDetail(response));
      const note = "Parked as “normal” — confirm it in setup review.";
      if (domain === "software") {
        setSoftware((prev) => ({ ...prev, final: `${prev.final}\n${note}` }));
      } else {
        setAppliance((prev) => ({ ...prev, final: `${prev.final}\n${note}` }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mark-normal failed.");
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
        defrost_active?: unknown;
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
        defrost_active: snap.defrost_active === true,
      }));
      const name =
        "fault" in body ? body.fault : body.action;
      const sentence = FRIDGE_SENTENCES[name];
      if (sentence) {
        push(feedItem("sim", sentence, "INFO"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fridge control failed.");
    }
  }

  async function fridgeBehaviour(behaviour: string) {
    setError("");
    try {
      const body =
        behaviour === "restock" ? { ticks: 1 } : { duration_ticks: 20 };
      const response = await fetch(
        `${apiUrl}/api/sim/fridge/${behaviour}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (!response.ok) throw new Error(await responseDetail(response));
      push(
        feedItem(
          "sim",
          behaviour === "restock"
            ? "Fridge door opened for restocking"
            : "Fridge defrost cycle started",
          "INFO",
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Behaviour failed.");
    }
  }

  async function deployShop() {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/sim/shop/deploy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_s: 20 }),
      });
      if (!response.ok) throw new Error(await responseDetail(response));
      setDeployUntil(Date.now() + 20000);
      push(
        feedItem("sim", "Shop deploy started (drain retries expected)", "INFO"),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deploy failed.");
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
    <div className="legacy">
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AUTONOMOUS SRE / LIVE INCIDENTS</p>
          <h1>Telemetry Agent</h1>
        </div>
        <div className="topbar-right">
          {systems.map((system) => (
            <a
              key={system.system_id}
              className={`syschip ${system.status}`}
              href={`/setup?system=${system.system_id}`}
              title={`${system.name} · ${system.status} (edit profile)`}
            >
              {system.name} · {system.status}
            </a>
          ))}
          <a className="ghost small buttonlink" href="/setup">
            + System
          </a>
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

      {systemsLoaded && !systems.some((s) => s.status === "armed") && (
        <div className="setupbanner" role="alert">
          <span>Setup needed — no system is armed, watchers are watch-only.</span>
          <a className="ghost small buttonlink" href="/setup">
            Teach it normal →
          </a>
        </div>
      )}

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
          {now < deployUntil && <span className="chip running">deploying</span>}
        </div>
        <div className="controls map-controls">
          <button
            type="button"
            onClick={startTraffic}
            disabled={!shopOnline || trafficLeft > 0}
          >
            {trafficLeft > 0 ? `Traffic running · ${trafficLeft}s` : "Start traffic"}
          </button>
          <button type="button" className="ghost" onClick={deployShop}>
            Deploy shop
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
          onBehaviour={(behaviour) => void fridgeBehaviour(behaviour)}
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
              <button
                type="button"
                className="ghost"
                onClick={() => void markNormal(software.runId, "software")}
                disabled={!software.runId}
                title="Park this incident as normal (pending setup review)"
              >
                This is normal
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
              <button
                type="button"
                className="ghost"
                onClick={() => void markNormal(appliance.runId, "appliance")}
                disabled={!appliance.runId}
                title="Park this incident as normal (pending setup review)"
              >
                This is normal
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
    </div>
  );
}
