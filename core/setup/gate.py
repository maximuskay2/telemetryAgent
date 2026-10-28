"""The Gate: "Is this really abnormal?" (P5).

Every watcher candidate passes through `evaluate()` before any run starts.
Checks run in order; the first decisive one wins. Each produces a
human-readable reason + citation so the dashboard, the phone, and the report
can explain the decision. Pure logic: callers supply the profile, the mode,
live metrics, and above-threshold durations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from core.schemas.profile import SystemProfile
from core.setup.modes import ModeState

RECHECK_S = 30.0

_WS = re.compile(r"\s+")
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "lines",
    "line", "may", "rise", "above", "below", "under", "over",
})
_METRIC_ALIASES = {
    "temp_c": ("temp_c", "temp", "temperature"),
    "current_a": ("current_a", "current", "amps"),
    "vibration_g": ("vibration_g", "vibration"),
    "error_rate": ("error_rate", "error rate", "errors"),
    "p95_ms": ("p95_ms", "p95", "latency"),
    "retry": ("retry", "retries"),
    "door": ("door",),
}


@dataclass
class Candidate:
    system_id: str
    source: str  # "log" | "sensor"
    rule: str
    fingerprint: str
    window: str = ""
    signature: str = ""
    template: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    durations: dict[str, float] = field(default_factory=dict)
    mode: str = ""


@dataclass
class GateCheck:
    name: str
    result: str  # "trigger" | "pass" | "skip"
    detail: str = ""


@dataclass
class GateDecision:
    decision: str  # "suppress" | "observe" | "act"
    reason: str
    citation: str
    checks: list[GateCheck] = field(default_factory=list)
    system_id: str = ""
    fingerprint: str = ""
    recheck_in_s: float = 0.0

    def payload(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "citation": self.citation,
            "checks": [
                {"name": c.name, "result": c.result, "detail": c.detail}
                for c in self.checks
            ],
            "system_id": self.system_id,
            "fingerprint": self.fingerprint,
            "recheck_in_s": self.recheck_in_s,
        }


def baseline_band(entry: Any, mode: str = "") -> Optional[list[float]]:
    """[lo, hi] from a legacy flat band or a per-mode band dict.

    Per-mode dicts prefer the candidate's mode, then the merged "all"
    band; anything else (stats blocks, junk) resolves to None.
    """
    if isinstance(entry, (list, tuple)) and len(entry) == 2:
        try:
            return [float(entry[0]), float(entry[1])]
        except (TypeError, ValueError):
            return None
    if isinstance(entry, dict):
        keys = ([mode] if mode else []) + ["all"]
        for key in keys:
            bounds = entry.get(key)
            if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
                try:
                    return [float(bounds[0]), float(bounds[1])]
                except (TypeError, ValueError):
                    return None
    return None


def gate_has_impact(gate: Optional[dict[str, Any]]) -> bool:
    """True when a gate payload proves impact (P6 second line of defence).

    A hard-limit or impact check that triggered means the run must proceed
    even if the model calls the telemetry normal.
    """
    if not gate:
        return False
    checks = gate.get("checks") or []
    return any(
        isinstance(check, dict)
        and check.get("name") in ("hard_limit", "impact")
        and check.get("result") == "trigger"
        for check in checks
    )


def normalize(text: str) -> str:
    return _WS.sub(" ", text or "").strip().lower()


def template_of(line: str) -> str:
    """Log template: numbers and ids normalized away (shared with P7)."""
    text = normalize(line)
    text = re.sub(r"\border=[a-z0-9]+\b", "order=<id>", text)
    text = re.sub(r"\b[a-f0-9]{6,}\b", "<id>", text)
    text = re.sub(r"\d+(\.\d+)?", "#", text)
    return text


def cite(provenance) -> str:
    doc = provenance.source_doc
    if doc == "user":
        by = provenance.page_or_region or "operator"
        return f"Marked normal by {by}"
    if doc in ("manual", "learned", "feedback"):
        return f"{doc} entry"
    region = provenance.page_or_region
    return f"{doc} {region}".strip() if region else doc


def _metric_value(name: str, metrics: dict[str, float]) -> Optional[float]:
    if name in metrics:
        return metrics[name]
    for canonical, aliases in _METRIC_ALIASES.items():
        if name == canonical or name in aliases:
            for alias in (canonical, *aliases):
                if alias in metrics:
                    return metrics[alias]
    return None


def _breached(op: str, value: float, threshold: float) -> bool:
    return value > threshold if op == ">" else value < threshold


def _text_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9=%.]+", normalize(text))
        if len(token) > 2 and token not in _STOPWORDS
    }


def behaviour_matches(signature: str, candidate: Candidate) -> bool:
    """Signature hit against the candidate's rule, signature, and window."""
    sig = normalize(signature)
    if not sig:
        return False
    if "=" in sig and " " not in sig.strip():
        # "mode=defrost" style: exact key=value match on known keys.
        # Anything else ("retry=1") falls through to token matching.
        key, _, want = sig.partition("=")
        key = key.strip()
        if key in ("mode", "rule"):
            haystacks = {
                "mode": normalize(candidate.mode),
                "rule": normalize(candidate.rule),
            }
            return haystacks.get(key, "") == want.strip()
    tokens = _text_tokens(sig)
    if not tokens:
        return False
    hay = _text_tokens(
        f"{candidate.rule} {candidate.signature} {candidate.window[:2000]}"
    )
    shared = tokens.intersection(hay)
    if len(shared) >= 2:
        return True
    # One shared token only counts when it is distinctive: a bare log
    # level like "warn" must not match every warning signature (S-12).
    return any(len(token) >= 6 for token in shared)


def _parse_bound(pattern: str) -> tuple[Optional[str], Optional[float]]:
    """Metric + ceiling from 'temp_c up to 7 C' / 'error_rate under 1%'."""
    text = normalize(pattern).replace("≤", "<=").replace("≥", ">=")
    metric = next(
        (
            canonical
            for canonical, aliases in _METRIC_ALIASES.items()
            if any(alias in text for alias in (canonical, *aliases))
        ),
        None,
    )
    bound = None
    match = re.search(
        r"(?:up to|under|below|to)\s*(<=?)?\s*(\d+(?:\.\d+)?)\s*(%?)",
        text,
    )
    if match:
        bound = float(match.group(2))
        if match.group(3) == "%":
            bound /= 100.0
    return metric, bound


def _rated_estimate(profile, metric: str) -> Optional[float]:
    """Midpoint of the profile's normal range: the 'rated' value."""
    if profile is None:
        return None
    for item in profile.normal_ranges:
        if item.metric == metric or metric in _METRIC_ALIASES.get(
            item.metric, ()
        ):
            return (item.min + item.max) / 2.0
        if item.metric in _METRIC_ALIASES.get(metric, ()):
            return (item.min + item.max) / 2.0
    return None


def _effect_within(
    allowed_effect: str,
    metrics: dict[str, float],
    profile=None,
) -> bool:
    """True unless live metrics provably exceed the allowed effect."""
    if not allowed_effect.strip():
        return True
    metric, bound = _parse_bound(allowed_effect)
    if metric is None:
        return True
    text = normalize(allowed_effect)
    multiplier = re.search(r"(\d+(?:\.\d+)?)\s*x\b", text)
    if multiplier is not None and "rated" in text:
        rated = _rated_estimate(profile, metric)
        if rated is None:
            return True
        bound = float(multiplier.group(1)) * rated
    if bound is None:
        return True
    value = _metric_value(metric, metrics)
    if value is None:
        return True
    return value <= bound


def relax_matches(pattern: str, candidate: Candidate) -> bool:
    """Does a mode's relax pattern excuse this candidate?"""
    metric, bound = _parse_bound(pattern)
    text = normalize(
        f"{candidate.rule} {candidate.signature} {candidate.window[:2000]}"
    )
    if metric is not None and not any(
        alias in text for alias in (metric, *_METRIC_ALIASES[metric])
    ):
        # Metric named but absent from the candidate — unless the metric is
        # carried as a live value (sensor candidates have no window text).
        if _metric_value(metric, candidate.metrics) is None:
            return False
    if metric is None:
        tokens = _text_tokens(pattern)
        if not tokens or tokens.isdisjoint(_text_tokens(text)):
            return False
    if bound is not None and metric is not None:
        value = _metric_value(metric, candidate.metrics)
        if value is None or value > bound:
            return False
    return True


def evaluate(
    candidate: Candidate,
    profile: Optional[SystemProfile],
    mode: Optional[ModeState] = None,
    metrics: Optional[dict[str, float]] = None,
    durations: Optional[dict[str, float]] = None,
) -> GateDecision:
    """Run the checks in order; first decisive one wins."""
    mode = mode or ModeState()
    merged = dict(metrics or {})
    merged.update(candidate.metrics)
    durs = dict(durations or {})
    durs.update(candidate.durations)
    checks: list[GateCheck] = []

    def decide(
        decision: str, reason: str, citation: str, recheck: float = 0.0
    ) -> GateDecision:
        return GateDecision(
            decision=decision,
            reason=reason,
            citation=citation,
            checks=checks,
            system_id=candidate.system_id,
            fingerprint=candidate.fingerprint,
            recheck_in_s=recheck,
        )

    # 1. Hard limits beat everything.
    if profile is not None:
        for limit in profile.hard_limits:
            value = _metric_value(limit.metric, merged)
            if value is None:
                checks.append(
                    GateCheck("hard_limit", "skip", f"no {limit.metric}")
                )
                continue
            if _breached(limit.op, value, limit.threshold):
                checks.append(
                    GateCheck(
                        "hard_limit", "trigger",
                        f"{limit.metric} {value:g} {limit.op} "
                        f"{limit.threshold:g}",
                    )
                )
                return decide(
                    "act",
                    f"Hard limit breached: {limit.metric} {value:g} "
                    f"{limit.op} {limit.threshold:g}",
                    cite(limit.provenance),
                )
        checks.append(GateCheck("hard_limit", "pass", "no breach"))

    # 2. Unarmed systems are watch-only.
    if profile is None:
        checks.append(GateCheck("armed", "trigger", "no profile"))
        return decide(
            "observe", "No profile for this system yet — Setup needed", ""
        )
    if profile.status != "armed":
        checks.append(GateCheck("armed", "trigger", f"status={profile.status}"))
        if profile.status == "learning":
            reason = "System is learning its baseline — observing only"
        else:
            reason = f"System is {profile.status} — Setup needed"
        return decide("observe", reason, "", recheck=RECHECK_S)
    checks.append(GateCheck("armed", "pass", "armed"))

    # 3. Expected behaviours (signature + schedule + within max
    # duration and allowed effect).
    seen_behaviour = False
    longest_s = max(durs.values()) if durs else 0.0
    for behaviour in profile.expected_behaviours:
        if not behaviour_matches(behaviour.signature, candidate):
            continue
        seen_behaviour = True
        if (
            behaviour.max_duration_s > 0
            and longest_s > behaviour.max_duration_s
        ):
            checks.append(
                GateCheck(
                    "expected", "pass",
                    f"{behaviour.name} overran "
                    f"{behaviour.max_duration_s:g}s",
                )
            )
            continue
        if not _effect_within(behaviour.allowed_effect, merged, profile):
            checks.append(
                GateCheck(
                    "expected", "pass",
                    f"{behaviour.name} exceeded allowed effect",
                )
            )
            continue
        checks.append(
            GateCheck("expected", "trigger", behaviour.name)
        )
        schedule = (
            f" ({behaviour.schedule})" if behaviour.schedule else ""
        )
        effect = (
            f", {behaviour.allowed_effect}"
            if behaviour.allowed_effect
            else ""
        )
        return decide(
            "suppress",
            f"Expected: {behaviour.name}{schedule}{effect}",
            cite(behaviour.provenance),
        )
    checks.append(
        GateCheck(
            "expected", "pass",
            "matched behaviours excused nothing"
            if seen_behaviour
            else "no behaviour matched",
        )
    )

    # 4. Current mode excuses — unless it overran. An overrun is an
    # anomaly itself: no mode excuse, no baseline excuse (below), and at
    # minimum an observe. Impact still decides act (S-7).
    overrun = bool(mode.mode and mode.overrun)
    if mode.mode:
        if mode.overrun:
            overrun_s = (
                mode.max_duration_s
                if mode.max_duration_s > 0
                else 0.0
            )
            checks.append(
                GateCheck(
                    "mode", "trigger",
                    f"mode {mode.mode} overran {overrun_s:g}s",
                )
            )
        else:
            entry = next(
                (
                    item
                    for item in profile.modes
                    if item.mode == mode.mode
                ),
                None,
            )
            patterns = entry.relaxes if entry is not None else []
            if any(relax_matches(p, candidate) for p in patterns):
                checks.append(
                    GateCheck("mode", "trigger", mode.mode)
                )
                citation = cite(entry.provenance) if entry is not None else ""
                return decide(
                    "suppress",
                    f"Mode {mode.mode} explains it",
                    citation,
                )
            checks.append(
                GateCheck("mode", "pass", f"{mode.mode} excuses nothing here")
            )
    else:
        checks.append(GateCheck("mode", "skip", "no mode"))

    # 5. Known in the baseline.
    baseline = profile.baseline
    if overrun:
        checks.append(
            GateCheck(
                "baseline", "pass",
                "mode overrun: baseline cannot excuse",
            )
        )
    elif baseline.status == "ready":
        template = candidate.template or template_of(candidate.signature)
        learned = {
            item.get("template", ""): item
            for item in baseline.log_templates
            if isinstance(item, dict)
        }
        if template and template in learned:
            try:
                normal_rate = float(
                    learned[template].get("rate_per_min", 0.0) or 0.0
                )
            except (TypeError, ValueError):
                normal_rate = 0.0
            live_rate = merged.get("template_rate_per_min")
            if live_rate is not None and live_rate > max(
                3.0 * normal_rate, normal_rate + 2.0
            ):
                checks.append(
                    GateCheck(
                        "baseline", "pass",
                        f"{template} rate spike {live_rate:g}/min",
                    )
                )
            else:
                checks.append(
                    GateCheck("baseline", "trigger", "log template")
                )
                return decide(
                    "suppress",
                    "Seen during baseline learning at normal rate",
                    "baseline",
                )
        for bands, label in (
            (baseline.sensor_bands or {}, "sensor"),
            (baseline.metric_bands or {}, "metric"),
        ):
            usable = [
                (metric, baseline_band(bands[metric], candidate.mode))
                for metric in bands
                if metric in merged
            ]
            usable = [
                (metric, bounds)
                for metric, bounds in usable
                if bounds is not None
            ]
            if usable and all(
                bounds[0] <= float(merged[metric]) <= bounds[1]
                for metric, bounds in usable
            ):
                checks.append(
                    GateCheck("baseline", "trigger", f"{label} band")
                )
                return decide(
                    "suppress",
                    f"Within the learned {label} band",
                    "baseline",
                )
        checks.append(GateCheck("baseline", "pass", "not in baseline"))
    else:
        checks.append(
            GateCheck("baseline", "skip", f"baseline {baseline.status}")
        )

    # 6. Proof of impact against the failure definitions.
    for failure in profile.failure_definitions:
        excepted = [
            item
            for item in failure.except_modes
            if not (item == mode.mode and mode.overrun)
        ]
        if mode.mode and mode.mode in excepted:
            checks.append(
                GateCheck(
                    "impact", "skip",
                    f"{failure.name} excepted in {mode.mode}",
                )
            )
            continue
        value = _metric_value(failure.metric, merged)
        if value is None or not _breached(
            failure.op, value, failure.threshold
        ):
            continue
        lasted = durs.get(failure.metric, 0.0)
        if lasted < failure.duration_s:
            checks.append(
                GateCheck(
                    "impact", "pass",
                    f"{failure.name} {lasted:g}s < {failure.duration_s:g}s",
                )
            )
            continue
        checks.append(GateCheck("impact", "trigger", failure.name))
        return decide(
            "act",
            f"{failure.name}: {failure.metric} {value:g} {failure.op} "
            f"{failure.threshold:g} for {lasted:g}s",
            cite(failure.provenance),
        )
    checks.append(GateCheck("impact", "pass", "no impact yet"))
    if overrun:
        entry = next(
            (item for item in profile.modes if item.mode == mode.mode),
            None,
        )
        return decide(
            "observe",
            f"Mode {mode.mode} overran its limit — watching for impact",
            cite(entry.provenance) if entry is not None else "",
            recheck=RECHECK_S,
        )
    return decide(
        "observe",
        "No impact yet — watching",
        "",
        recheck=RECHECK_S,
    )
