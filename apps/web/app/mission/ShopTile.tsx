"use client";

import { useEffect, useState } from "react";
import Metric, { Sparkline } from "../ui/Metric";
import ServiceMap from "./ServiceMap";
import { useMission } from "./state";
import TileStatus from "./TileStatus";

export default function ShopTile({ systemId }: { systemId: string | null }) {
  const {
    orders,
    shopMetrics,
    errorRates,
    trafficUntil,
    deployUntil,
    now,
    startTraffic,
    deployShop,
    events,
  } = useMission();
  const [fixedAt, setFixedAt] = useState<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const applied = events.find((e) => e.source === "fix" && e.message.includes("shop"));
    if (applied) setFixedAt(Date.now());
  }, [events]);

  const errorRate = shopMetrics?.errorRate ?? 0;
  const trafficLeft = Math.max(0, Math.ceil((trafficUntil - now) / 1000));
  const deployLeft = Math.max(0, Math.ceil((deployUntil - now) / 1000));
  const markerAt =
    fixedAt !== null && errorRates.length > 1 ? errorRates.length - 1 : null;

  return (
    <section id="tour-shop" aria-label="Shop topology" className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-text">Shop topology</h2>
        <div className="flex items-center gap-2">
          <TileStatus domain="software" systemId={systemId} />
          <div className="relative">
            <button
              type="button"
              aria-label="Shop controls"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(!menuOpen)}
              className="rounded-md border border-border bg-surface-2 px-2 py-0.5 text-xs text-text hover:border-text-faint"
            >
              ⋯
            </button>
            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 top-full z-10 mt-1 w-44 rounded-md border border-border bg-surface-2 py-1 shadow-lg"
              >
                <button
                  type="button"
                  role="menuitem"
                  disabled={deployLeft > 0}
                  onClick={() => {
                    deployShop();
                    setMenuOpen(false);
                  }}
                  className="block w-full px-3 py-1.5 text-left text-xs text-text hover:bg-surface disabled:opacity-50"
                >
                  {deployLeft > 0 ? `Deploying… ${deployLeft}s` : "Deploy shop (20s)"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-2">
        <ServiceMap orders={orders} errorRate={errorRate} fixedAt={fixedAt} />
      </div>

      <dl className="mt-2 grid grid-cols-3 gap-2">
        <Metric
          label="Orders/min"
          value={shopMetrics ? String(shopMetrics.ordersPerMin) : "—"}
        />
        <Metric
          label="Error rate"
          value={shopMetrics ? `${Math.round(errorRate * 100)}%` : "—"}
          tone={errorRate >= 0.2 ? "crit" : errorRate > 0 ? "warn" : "ok"}
        />
        <Metric
          label="p95"
          value={shopMetrics ? `${Math.round(shopMetrics.p95Ms)}ms` : "—"}
        />
      </dl>

      <div className="mt-2 flex items-center gap-3">
        <div className="min-w-0 flex-1">
          {errorRates.length > 1 ? (
            <span className={errorRate >= 0.2 ? "text-crit" : "text-text-muted"}>
              <Sparkline points={errorRates} {...(markerAt !== null ? { markerAt } : {})} />
            </span>
          ) : (
            <span className="text-xs text-text-faint">waiting for metrics…</span>
          )}
        </div>
        {trafficLeft > 0 ? (
          <span className="text-xs tabular-nums text-text-muted">
            Traffic {trafficLeft}s
          </span>
        ) : (
          <button
            type="button"
            onClick={startTraffic}
            className="shrink-0 rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-text hover:border-text-faint"
          >
            Start traffic
          </button>
        )}
      </div>
    </section>
  );
}
