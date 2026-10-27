"use client";

import { useMemo } from "react";

export type OrderDot = {
  id: string;
  status: "ok" | "failed" | "waiting";
  items: string[];
  born: number;
};

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

export default function ServiceMap({ orders }: { orders: OrderDot[] }) {
  const failed = useMemo(() => orders.filter((o) => o.status === "failed"), [orders]);
  const pair = useMemo(() => deadlockPair(failed), [failed]);
  const hot = useMemo(() => new Set(failed.flatMap((o) => o.items)), [failed]);

  const a = pair ? lockPos(pair[0]) : null;
  const b = pair ? lockPos(pair[1]) : null;

  return (
    <svg className="servicemap" viewBox="0 0 760 250" role="img" aria-label="Service map">
      {/* backbone */}
      <line x1="60" y1="130" x2="700" y2="130" className="backbone" />
      <text x="40" y="30" className="maplabel">Shoppers</text>
      <circle cx="60" cy="130" r="10" className="node" />
      <text x="180" y="30" className="maplabel">Shop API</text>
      <circle cx="200" cy="130" r="10" className="node" />
      <text x="330" y="30" className="maplabel">Inventory locks</text>
      <text x="668" y="30" className="maplabel">Orders DB</text>
      <circle cx="700" cy="130" r="10" className="node" />

      {LOCK_SKUS.map((sku) => {
        const p = lockPos(sku);
        return (
          <g key={sku}>
            <rect
              x={p.x - 20}
              y={p.y - 11}
              width="40"
              height="22"
              rx="4"
              className={hot.has(sku) ? "lock hot" : "lock"}
            />
            <text x={p.x} y={p.y + 4} className="locklabel">
              {sku.slice(0, 7)}
            </text>
          </g>
        );
      })}

      {a && b && (
        <g className="cycle">
          <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="cycle-edge" />
          <line x1={b.x} y1={b.y - 5} x2={a.x} y2={a.y - 5} className="cycle-edge" />
          <text x={(a.x + b.x) / 2} y={Math.min(a.y, b.y) - 12} className="cyclelabel">
            deadlock cycle
          </text>
        </g>
      )}

      {orders.map((order) => (
        <circle
          key={order.id}
          cx="60"
          cy={laneFor(order.id)}
          r="4"
          className={`orderdot ${order.status}`}
        />
      ))}
    </svg>
  );
}
