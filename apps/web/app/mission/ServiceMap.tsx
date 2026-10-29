"use client";

import { useReducedMotion } from "motion/react";
import { useMemo, useRef } from "react";
import type { OrderDot } from "../components/ServiceMap";

const LANES = [70, 130, 190];
const LOCK_SKUS = [
  "axle",
  "brake-pad",
  "chain",
  "sprocket",
  "gasket",
  "piston",
  "alternator",
  "starter",
  "radiator",
  "muffler",
  "shock",
  "headlight",
];

/** At most ~6 dots/s: enforce 160 ms spacing between displayed dots. */
const MIN_DOT_GAP_MS = 160;
const MAX_DOTS = 12;

function laneFor(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  return LANES[hash % LANES.length];
}

function lockPos(sku: string): { x: number; y: number } {
  const i = Math.max(0, LOCK_SKUS.indexOf(sku));
  return { x: 350 + (i % 6) * 44, y: 60 + Math.floor(i / 6) * 120 };
}

/** Most co-occurring SKU pair across failed orders: the likely cycle. */
function deadlockPair(failed: OrderDot[]): [string, string] | null {
  const counts = new Map<string, number>();
  for (const order of failed) {
    const items = [...new Set(order.items)].sort();
    for (let a = 0; a < items.length; a++) {
      for (let b = a + 1; b < items.length; b++) {
        const key = `${items[a]}|${items[b]}`;
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
    }
  }
  let best: [string, string] | null = null;
  let bestCount = 0;
  for (const [key, count] of counts) {
    if (count > bestCount) {
      const [a, b] = key.split("|");
      best = [a, b];
      bestCount = count;
    }
  }
  return bestCount >= 2 ? best : null;
}

export default function ServiceMap({
  orders,
  errorRate,
  fixedAt,
}: {
  orders: OrderDot[];
  errorRate: number;
  /** Timestamp of the last shop fix, for the resolved (green) loop. */
  fixedAt: number | null;
}) {
  const reduce = useReducedMotion();
  const failed = useMemo(() => orders.filter((o) => o.status === "failed"), [orders]);
  const pair = useMemo(() => deadlockPair(failed), [failed]);
  const hot = useMemo(() => new Set(failed.flatMap((o) => o.items)), [failed]);
  const lastPair = useRef<[string, string] | null>(null);
  if (pair) lastPair.current = pair;

  const dots = useMemo(() => {
    const sorted = [...orders].sort((a, b) => a.born - b.born);
    const picked: OrderDot[] = [];
    for (const order of sorted) {
      const prev = picked[picked.length - 1];
      if (!prev || order.born - prev.born >= MIN_DOT_GAP_MS) picked.push(order);
    }
    return picked.slice(-MAX_DOTS);
  }, [orders]);

  const failing = failed.length > 0;
  const resolved =
    !failing && lastPair.current !== null && fixedAt !== null && Date.now() - fixedAt < 120000;
  const shown = pair ?? (resolved ? lastPair.current : null);
  const a = shown ? lockPos(shown[0]) : null;
  const b = shown ? lockPos(shown[1]) : null;
  const loopTone = failing ? "crit" : "ok";

  const health = failing || errorRate >= 0.2 ? "crit" : errorRate > 0 ? "warn" : "ok";
  const glow =
    health === "crit"
      ? "[filter:drop-shadow(0_0_6px_rgb(239_68_68/0.55))]"
      : health === "warn"
        ? "[filter:drop-shadow(0_0_6px_rgb(245_158_11/0.45))]"
        : "[filter:drop-shadow(0_0_5px_rgb(16_185_129/0.35))]";

  return (
    <svg viewBox="0 0 760 250" className="w-full" role="img" aria-label="Service map">
      {/* backbone */}
      <line x1="60" y1="130" x2="700" y2="130" className="stroke-border" strokeWidth={1.5} />
      {/* node cards */}
      {[
        { x: 60, label: "Shoppers" },
        { x: 200, label: "Shop API" },
        { x: 700, label: "Orders DB" },
      ].map((n) => (
        <g key={n.label} className={glow}>
          <rect x={n.x - 34} y={116} width="68" height="28" rx="7" className="fill-surface-2 stroke-border" />
          <circle cx={n.x} cy={130} r="4" className={health === "ok" ? "fill-ok" : health === "warn" ? "fill-warn" : "fill-crit"} />
          <text x={n.x} y={30} textAnchor="middle" className="fill-text-muted text-[11px]">
            {n.label}
          </text>
        </g>
      ))}
      <text x="458" y={30} textAnchor="middle" className="fill-text-muted text-[11px]">
        Inventory locks
      </text>
      {LOCK_SKUS.map((sku) => {
        const p = lockPos(sku);
        const isHot = hot.has(sku);
        return (
          <g key={sku}>
            <rect
              x={p.x - 20}
              y={p.y - 11}
              width="40"
              height="22"
              rx="4"
              className={isHot ? "fill-crit/15 stroke-crit/60" : "fill-surface-2 stroke-border"}
            />
            <text x={p.x} y={p.y + 4} textAnchor="middle" className={`text-[9px] ${isHot ? "fill-crit" : "fill-text-faint"}`}>
              {sku.slice(0, 7)}
            </text>
          </g>
        );
      })}
      {/* deadlock loop: crimson while failing, green after apply-fix */}
      {a && b && (
        <g>
          <line
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            className={loopTone === "crit" ? "stroke-crit" : "stroke-ok"}
            strokeWidth={2}
          />
          <line
            x1={b.x}
            y1={b.y - 5}
            x2={a.x}
            y2={a.y - 5}
            className={loopTone === "crit" ? "stroke-crit" : "stroke-ok"}
            strokeWidth={2}
          />
          <text
            x={(a.x + b.x) / 2}
            y={Math.min(a.y, b.y) - 12}
            textAnchor="middle"
            className={`text-[11px] font-medium ${loopTone === "crit" ? "fill-crit" : "fill-ok"}`}
          >
            {loopTone === "crit" ? "deadlock cycle" : "cycle resolved"}
          </text>
        </g>
      )}
      {/* traffic pulses: one dot per real order, sampled to ≤6/s */}
      {dots.map((order) => (
        <circle
          key={order.id}
          cx={reduce ? 700 : 60}
          cy={laneFor(order.id)}
          r="4"
          className={
            order.status === "failed"
              ? "fill-crit"
              : order.status === "waiting"
                ? "fill-warn"
                : "fill-ok"
          }
          style={reduce ? undefined : { animation: "mission-pulse-x 2.4s linear forwards" }}
        />
      ))}
    </svg>
  );
}
