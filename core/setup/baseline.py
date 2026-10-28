"""Baseline learning: what 'normal' looks like, per system (P7).

While a system has status `learning`, watchers keep running but the gate
only ever observes (P5 check 2). Meanwhile every log line, sensor reading,
and shop-metrics snapshot feeds the system's `BaselineLearner`. `finish()`
compiles the observations into the profile's `Baseline`: log templates
with per-minute rates, per-metric per-mode p5–p95 bands, and shop metric
bands. The gate's baseline check (P5 check 5) reads these back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.schemas.profile import Baseline
from core.setup.gate import template_of


def percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolation percentile over pre-sorted values (0..100)."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    low = int(rank)
    high = min(len(sorted_vals) - 1, low + 1)
    frac = rank - low
    return sorted_vals[low] + (sorted_vals[high] - sorted_vals[low]) * frac


def band(values: list[float]) -> list[float]:
    ordered = sorted(values)
    return [percentile(ordered, 5.0), percentile(ordered, 95.0)]


@dataclass
class BaselineLearner:
    system_id: str
    started_at: float = field(default_factory=time.time)
    log_counts: dict[str, int] = field(default_factory=dict)
    sensor_values: dict[str, dict[str, list[float]]] = field(
        default_factory=dict
    )
    sensor_rocs: dict[str, list[float]] = field(default_factory=dict)
    _sensor_last: dict[str, tuple[float, float]] = field(default_factory=dict)
    shop_error_rates: list[float] = field(default_factory=list)
    shop_p95: list[float] = field(default_factory=list)
    shop_orders: list[float] = field(default_factory=list)
    observations: int = 0
    hard_limit_hit: bool = False

    def observe_log(self, line: str) -> None:
        template = template_of(line)
        if not template:
            return
        self.log_counts[template] = self.log_counts.get(template, 0) + 1
        self.observations += 1

    def observe_sensor(
        self, metric: str, value: float, mode: str = "",
        now: Optional[float] = None,
    ) -> None:
        at = time.time() if now is None else now
        per_mode = self.sensor_values.setdefault(metric, {})
        per_mode.setdefault("all", []).append(value)
        per_mode.setdefault(mode or "normal", []).append(value)
        last = self._sensor_last.get(metric)
        if last is not None:
            prev_at, prev_value = last
            dt = at - prev_at
            if dt > 0:
                self.sensor_rocs.setdefault(metric, []).append(
                    abs(value - prev_value) / dt
                )
        self._sensor_last[metric] = (at, value)
        self.observations += 1

    def observe_shop(
        self, error_rate: float, p95_ms: float, orders_per_min: float
    ) -> None:
        self.shop_error_rates.append(error_rate)
        self.shop_p95.append(p95_ms)
        self.shop_orders.append(orders_per_min)
        self.observations += 1

    def elapsed_s(self, now: Optional[float] = None) -> float:
        return max(0.0, (time.time() if now is None else now) - self.started_at)

    def patterns_learned(self) -> int:
        return len(self.log_counts) + len(self.sensor_values) + (
            1 if self.shop_error_rates else 0
        )

    def finish(self, now: Optional[float] = None) -> Baseline:
        at = time.time() if now is None else now
        minutes = max(self.elapsed_s(at) / 60.0, 1.0 / 60.0)
        templates = [
            {
                "template": template,
                "count": count,
                "rate_per_min": round(count / minutes, 3),
            }
            for template, count in sorted(
                self.log_counts.items(), key=lambda item: -item[1]
            )[:200]
        ]
        sensor_bands: dict[str, dict] = {}
        for metric, per_mode in self.sensor_values.items():
            entry: dict[str, object] = {}
            for mode, values in per_mode.items():
                entry[mode] = band(values)
            rocs = sorted(self.sensor_rocs.get(metric, []))
            entry["stats"] = {
                "mean": (
                    sum(per_mode["all"]) / len(per_mode["all"])
                    if per_mode.get("all")
                    else 0.0
                ),
                "roc_per_s": percentile(rocs, 50.0) if rocs else 0.0,
            }
            sensor_bands[metric] = entry
        metric_bands: dict[str, list[float]] = {}
        if self.shop_error_rates:
            metric_bands["error_rate"] = band(self.shop_error_rates)
        if self.shop_p95:
            metric_bands["p95_ms"] = band(self.shop_p95)
        if self.shop_orders:
            metric_bands["orders_per_min"] = band(self.shop_orders)
        return Baseline(
            status="ready",
            duration_s=round(self.elapsed_s(at), 1),
            learned_at=datetime.fromtimestamp(at, timezone.utc).isoformat(),
            log_templates=templates,
            sensor_bands=sensor_bands,
            metric_bands=metric_bands,
        )
