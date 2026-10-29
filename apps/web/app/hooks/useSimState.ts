"use client";

import { useCallback, useEffect, useState } from "react";
import type { OrderDot } from "../components/ServiceMap";
import type { FridgeState } from "../components/VirtualFridge";
import type { LogEvent, ScenarioState, ShopMetrics } from "../types/api";
import { feedItem } from "./useFeed";

export function useSimState() {
  const [orders, setOrders] = useState<OrderDot[]>([]);
  const [fridgeTemps, setFridgeTemps] = useState<number[]>([]);
  const [fridgeDefrost, setFridgeDefrost] = useState<boolean[]>([]);
  const [fridge, setFridge] = useState<FridgeState | null>(null);
  const [scenario, setScenario] = useState<ScenarioState>({
    playing: false,
    done: 0,
    total: 0,
    current: "",
  });
  const [shopMetrics, setShopMetrics] = useState<ShopMetrics | null>(null);
  const [errorRates, setErrorRates] = useState<number[]>([]);
  const [trafficUntil, setTrafficUntil] = useState(0);
  const [deployUntil, setDeployUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [mountedAt] = useState(() => Date.now());

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

  const applyShopOrder = useCallback(
    (payload: { order_id: string; status: string; items: string[] }) => {
      const status =
        payload.status === "failed"
          ? "failed"
          : payload.status === "waiting"
            ? "waiting"
            : "ok";
      const order: OrderDot = {
        id: payload.order_id,
        status,
        items: payload.items,
        born: Date.now(),
      };
      setOrders((current) =>
        [...current.filter((o) => Date.now() - o.born < 6000), order].slice(-24),
      );
    },
    [],
  );

  const applyShopMetrics = useCallback(
    (payload: { orders_per_min: number; error_rate: number; p95_ms: number }) => {
      setShopMetrics({
        ordersPerMin: payload.orders_per_min,
        errorRate: payload.error_rate,
        p95Ms: payload.p95_ms,
        seenAt: Date.now(),
      });
      setErrorRates((current) => [...current, payload.error_rate].slice(-60));
    },
    [],
  );

  const applyFridgeReading = useCallback(
    (payload: {
      temperature_c: number;
      current_a: number;
      vibration_g: number;
      door_open: boolean;
      compressor_on: boolean;
      condenser_dirty: boolean;
      surge_active: boolean;
      short_cycling: boolean;
      defrost_active: boolean;
    }) => {
      setFridgeTemps((current) => [...current, payload.temperature_c].slice(-60));
      setFridgeDefrost((current) => [...current, payload.defrost_active].slice(-60));
      setFridge({
        temp_c: payload.temperature_c,
        current_a: payload.current_a,
        vibration_g: payload.vibration_g,
        door_open: payload.door_open,
        compressor_on: payload.compressor_on,
        condenser_dirty: payload.condenser_dirty,
        surge_active: payload.surge_active,
        short_cycling: payload.short_cycling,
        defrost_active: payload.defrost_active,
      });
    },
    [],
  );

  const applyScenarioStep = useCallback(
    (payload: { done: number; total: number; action: string }): LogEvent => {
      setScenario({
        playing: payload.done < payload.total,
        done: payload.done,
        total: payload.total,
        current: payload.action,
      });
      return feedItem(
        "scenario",
        `Scenario step ${payload.done}/${payload.total}: ${payload.action || "step"}`,
        "INFO",
      );
    },
    [],
  );

  const reset = useCallback(() => {
    setOrders([]);
    setErrorRates([]);
    setTrafficUntil(0);
    setFridgeTemps([]);
    setFridgeDefrost([]);
    setFridge(null);
    setScenario({ playing: false, done: 0, total: 0, current: "" });
  }, []);

  return {
    orders,
    fridgeTemps,
    fridgeDefrost,
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
    reset,
  };
}
