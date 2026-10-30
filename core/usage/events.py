"""Usage-event recorder: the contract shape for Phase 3.

Every billable-or-countable action appends one UsageEvent::

    org_id, system_id, run_id, kind, quantity, unit,
    provider, language, cost_estimate_usd, at, model

Kind/unit vocabulary (fixed; the admin API and allowance checks
depend on it):

    kind "model_call": unit "tokens_in" | "tokens_out" (two events
        per call, one per direction; quantity = token count)
    kind "sandbox_time": unit "seconds" (quantity = wall seconds;
        provider names the backend: "modal" | "docker")
    kind "fix_run": unit "run_started" | "run_pass" | "run_draft" |
        "run_failed" (quantity 1; cost lives on the model_call and
        sandbox_time events of the same run_id, NOT here)
    kind "pr": unit "pr_opened" | "pr_comment" (quantity 1)
    kind "mitigation": unit "action:<action>" (quantity 1)
    kind "ingest": unit "lines" (quantity = lines forwarded)
    kind "systems": unit "count" (quantity = systems on the org)
    kind "devices": unit "count" (quantity = devices on the org)

Empty string ("") marks not-applicable provider / language / run_id.
`at` is epoch seconds (UTC). Costs are USD estimates from
core.usage.costs — what providers charge us, not customer prices.

Backends: MemoryUsageStore (tests, ephemeral) and JsonlUsageStore
(data/usage_events.jsonl, TA_DATA_DIR-aware like the profile store).
James's Phase 0 Postgres work may add a third backend later.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

from core.setup.store import data_root
from core.usage import costs as cost_table


class Kind:
    MODEL_CALL = "model_call"
    SANDBOX_TIME = "sandbox_time"
    FIX_RUN = "fix_run"
    PR = "pr"
    MITIGATION = "mitigation"
    INGEST = "ingest"
    SYSTEMS = "systems"
    DEVICES = "devices"


@dataclass(frozen=True)
class UsageEvent:
    org_id: str
    system_id: str
    run_id: str
    kind: str
    quantity: float
    unit: str
    provider: str
    language: str
    cost_estimate_usd: float
    at: float
    model: str = ""  # §8.3: cost table is per provider+model

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict) -> "UsageEvent":
        return cls(
            org_id=str(row.get("org_id", "")),
            system_id=str(row.get("system_id", "")),
            run_id=str(row.get("run_id", "")),
            kind=str(row.get("kind", "")),
            quantity=float(row.get("quantity", 0.0)),
            unit=str(row.get("unit", "")),
            provider=str(row.get("provider", "")),
            language=str(row.get("language", "")),
            cost_estimate_usd=float(row.get("cost_estimate_usd", 0.0)),
            at=float(row.get("at", 0.0)),
            model=str(row.get("model", "")),
        )


# ---------------------------------------------------------------------------
# stores
# ---------------------------------------------------------------------------


class UsageStore:
    """Append + filter. Implementations must be safe for small scale."""

    def record(self, event: UsageEvent) -> UsageEvent:
        raise NotImplementedError

    def query(self,
              org_id: Optional[str] = None,
              kinds: Optional[Iterable[str]] = None,
              since: Optional[float] = None,
              until: Optional[float] = None,
              provider: Optional[str] = None,
              language: Optional[str] = None) -> list[UsageEvent]:
        raise NotImplementedError

    def close(self) -> None:
        """Flush / release. No-op unless the backend buffers."""


def _matches(event: UsageEvent,
             org_id: Optional[str],
             kinds: Optional[set[str]],
             since: Optional[float],
             until: Optional[float],
             provider: Optional[str],
             language: Optional[str]) -> bool:
    return (
        (org_id is None or event.org_id == org_id)
        and (kinds is None or event.kind in kinds)
        and (since is None or event.at >= since)
        and (until is None or event.at < until)
        and (provider is None or event.provider == provider)
        and (language is None or event.language == language)
    )


class MemoryUsageStore(UsageStore):
    def __init__(self) -> None:
        self._events: list[UsageEvent] = []

    def record(self, event: UsageEvent) -> UsageEvent:
        self._events.append(event)
        return event

    def query(self, org_id=None, kinds=None, since=None, until=None,
              provider=None, language=None) -> list[UsageEvent]:
        want = set(kinds) if kinds is not None else None
        return [e for e in self._events
                if _matches(e, org_id, want, since, until, provider, language)]


def usage_events_path() -> Path:
    return data_root() / "usage_events.jsonl"


class JsonlUsageStore(UsageStore):
    """Append-only JSONL file. Small scale: queries scan the file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else usage_events_path()

    def record(self, event: UsageEvent) -> UsageEvent:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
        return event

    def query(self, org_id=None, kinds=None, since=None, until=None,
              provider=None, language=None) -> list[UsageEvent]:
        want = set(kinds) if kinds is not None else None
        if not self.path.exists():
            return []
        out: list[UsageEvent] = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = UsageEvent.from_dict(json.loads(line))
                except (ValueError, TypeError, AttributeError):
                    continue  # never let a corrupt row break a query
                if _matches(event, org_id, want, since, until, provider, language):
                    out.append(event)
        return out


# ---------------------------------------------------------------------------
# record helpers (one per cost/count point; return cost added, if any)
# ---------------------------------------------------------------------------


def _now(at: Optional[float]) -> float:
    return time.time() if at is None else float(at)


def record_model_call(store: UsageStore,
                      *,
                      org_id: str,
                      system_id: str = "",
                      run_id: str = "",
                      language: str = "",
                      provider: str,
                      model: str,
                      input_tokens: int,
                      output_tokens: int,
                      at: Optional[float] = None) -> float:
    """Record a model call as two events (in + out). Returns total cost."""
    ts = _now(at)
    rate = cost_table.rate_for(provider, model)
    try:
        inp = max(0, int(input_tokens))
        out = max(0, int(output_tokens))
    except (TypeError, ValueError):
        inp, out = 0, 0
    store.record(UsageEvent(
        org_id=org_id, system_id=system_id, run_id=run_id,
        kind=Kind.MODEL_CALL, quantity=float(inp), unit="tokens_in",
        provider=provider, language=language,
        cost_estimate_usd=inp / 1_000_000 * rate.input_usd_per_1m, at=ts,
        model=model))
    store.record(UsageEvent(
        org_id=org_id, system_id=system_id, run_id=run_id,
        kind=Kind.MODEL_CALL, quantity=float(out), unit="tokens_out",
        provider=provider, language=language,
        cost_estimate_usd=out / 1_000_000 * rate.output_usd_per_1m, at=ts,
        model=model))
    return cost_table.cost_of_tokens(provider, model, inp, out)


def record_sandbox_time(store: UsageStore,
                        *,
                        org_id: str,
                        system_id: str = "",
                        run_id: str = "",
                        language: str = "",
                        backend: str,
                        seconds: float,
                        at: Optional[float] = None) -> float:
    """Record sandbox wall time. Returns cost added."""
    try:
        secs = max(0.0, float(seconds))
    except (TypeError, ValueError):
        secs = 0.0
    store.record(UsageEvent(
        org_id=org_id, system_id=system_id, run_id=run_id,
        kind=Kind.SANDBOX_TIME, quantity=secs, unit="seconds",
        provider=backend, language=language,
        cost_estimate_usd=cost_table.cost_of_sandbox(backend, secs),
        at=_now(at)))
    return cost_table.cost_of_sandbox(backend, secs)


_RUN_UNITS = {
    "started": "run_started",
    "pass": "run_pass",
    "draft": "run_draft",
    "failed": "run_failed",
}


def record_fix_run(store: UsageStore,
                   *,
                   org_id: str,
                   system_id: str = "",
                   run_id: str = "",
                   language: str = "",
                   outcome: str,
                   at: Optional[float] = None) -> None:
    """Record a fix-run start/finish. Cost stays on its model/sandbox events."""
    unit = _RUN_UNITS.get((outcome or "").lower(), "run_started")
    store.record(UsageEvent(
        org_id=org_id, system_id=system_id, run_id=run_id,
        kind=Kind.FIX_RUN, quantity=1.0, unit=unit,
        provider="", language=language,
        cost_estimate_usd=0.0, at=_now(at)))


def record_pr(store: UsageStore,
              *,
              org_id: str,
              system_id: str = "",
              run_id: str = "",
              language: str = "",
              action: str,
              at: Optional[float] = None) -> None:
    """Record a PR open or comment. `action`: "opened" | "comment"."""
    unit = "pr_opened" if (action or "").lower() == "opened" else "pr_comment"
    store.record(UsageEvent(
        org_id=org_id, system_id=system_id, run_id=run_id,
        kind=Kind.PR, quantity=1.0, unit=unit,
        provider="", language=language,
        cost_estimate_usd=0.0, at=_now(at)))


def record_mitigation(store: UsageStore,
                      *,
                      org_id: str,
                      system_id: str = "",
                      run_id: str = "",
                      language: str = "",
                      action: str,
                      at: Optional[float] = None) -> None:
    """Record one auto-mitigation, by action name."""
    store.record(UsageEvent(
        org_id=org_id, system_id=system_id, run_id=run_id,
        kind=Kind.MITIGATION, quantity=1.0,
        unit=f"action:{action or 'unknown'}",
        provider="", language=language,
        cost_estimate_usd=0.0, at=_now(at)))


def record_ingest(store: UsageStore,
                  *,
                  org_id: str,
                  system_id: str = "",
                  lines: int,
                  at: Optional[float] = None) -> None:
    """Record forwarded log lines (abuse-guard input)."""
    try:
        n = max(0, int(lines))
    except (TypeError, ValueError):
        n = 0
    store.record(UsageEvent(
        org_id=org_id, system_id=system_id, run_id="",
        kind=Kind.INGEST, quantity=float(n), unit="lines",
        provider="", language="",
        cost_estimate_usd=0.0, at=_now(at)))


def record_snapshot(store: UsageStore,
                    *,
                    org_id: str,
                    kind: str,
                    count: int,
                    at: Optional[float] = None) -> None:
    """Record a systems/devices count snapshot. `kind`: "systems"|"devices"."""
    kind = kind if kind in (Kind.SYSTEMS, Kind.DEVICES) else Kind.SYSTEMS
    try:
        n = max(0, int(count))
    except (TypeError, ValueError):
        n = 0
    store.record(UsageEvent(
        org_id=org_id, system_id="", run_id="",
        kind=kind, quantity=float(n), unit="count",
        provider="", language="",
        cost_estimate_usd=0.0, at=_now(at)))


def default_store() -> JsonlUsageStore:
    """Process-shared JSONL store (tests: point TA_DATA_DIR at tmp)."""
    return JsonlUsageStore()
