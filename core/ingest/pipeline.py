"""Log-entry pipeline: lines → entries → rules → gate (J-R1).

One assembler per (system, service) joins multi-line tracebacks across
requests. Rule hits become gate candidates with the real `system_id`:
production systems are evaluated in-process (an `act` is recorded and
queued — J-R3 wires it to the repo pipeline), anything else delegates to
the existing candidate endpoint for byte-identical demo behaviour.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.connections import is_production
from core.ingest.traceback import (
    TracebackAssembler,
    TracebackInfo,
    parse_traceback,
)
from core.setup import gate as setup_gate
from core.setup import store as setup_store
from core.setup.modes import ModeState
from core.watch import rules

#: Gate windows are capped (tracebacks can be long).
MAX_WINDOW_CHARS = 4000
MAX_SIGNATURE_CHARS = 500

_assemblers: Dict[str, TracebackAssembler] = {}


@dataclass
class Entry:
    text: str
    ts: float
    traceback: Optional[TracebackInfo] = None


def _assembler_for(key: str) -> TracebackAssembler:
    assembler = _assemblers.get(key)
    if assembler is None:
        assembler = TracebackAssembler()
        _assemblers[key] = assembler
        if len(_assemblers) > 1000:  # never grow without bound
            oldest = next(iter(_assemblers))
            if oldest != key:
                _assemblers.pop(oldest, None)
    return assembler


def reset_assemblers() -> None:
    """Drop all reassembly state (tests only)."""
    _assemblers.clear()


def assemble(key: str, lines: List[str], now: float) -> List[Entry]:
    """Group raw lines into entries; one traceback = one entry."""
    assembler = _assembler_for(key)
    entries: List[Entry] = []
    for stale in assembler.flush_stale(now):
        entries.append(Entry(text=stale, ts=now))
    for line in lines:
        was_collecting = assembler.collecting
        completed = assembler.feed(line, now)
        if completed is not None:
            entries.append(
                Entry(
                    text=completed, ts=now,
                    traceback=parse_traceback(completed),
                )
            )
        elif not was_collecting and not assembler.collecting:
            entries.append(Entry(text=line, ts=now))
    return entries


def _signature_for(entry: Entry) -> str:
    if entry.traceback is not None and entry.traceback.signature:
        return entry.traceback.signature[:MAX_SIGNATURE_CHARS]
    first = entry.text.splitlines()[0] if entry.text.splitlines() else ""
    return first.strip()[:MAX_SIGNATURE_CHARS]


async def process_lines(
    system_id: str,
    service: str,
    lines: List[str],
    extra_metrics: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Evaluate one batch; returns accepted/candidates/decisions."""
    from apps.api.main import (  # deferred: routers load before main ends
        CandidateIn,
        _mark_learning_incident,
        _record_gate_decision,
        post_incident_candidate,
    )

    now = time.time()
    profile = setup_store.get_profile(system_id)
    production = profile is None or is_production(profile)
    entries = assemble(f"ingest:{system_id}:{service}", lines, now)
    decisions: List[Dict[str, Any]] = []
    candidates = 0
    for entry in entries:
        hit = rules.match_error(entry.text)
        if hit is None:
            continue
        candidates += 1
        signature = _signature_for(entry)
        resource = rules.extract_resource(entry.text)
        fingerprint = rules.fingerprint_for(hit.rule, resource, signature)
        window = entry.text[:MAX_WINDOW_CHARS]
        if not production:
            await post_incident_candidate(
                CandidateIn(
                    system_id=system_id,
                    source="log",
                    rule=hit.rule,
                    fingerprint=fingerprint,
                    signature=signature,
                    window=window,
                )
            )
            continue
        candidate = setup_gate.Candidate(
            system_id=system_id,
            source="log",
            rule=hit.rule,
            fingerprint=fingerprint,
            window=window,
            signature=signature,
            metrics=dict(extra_metrics or {}),
        )
        decision = setup_gate.evaluate(candidate, profile, ModeState())
        body = {
            **decision.payload(),
            "rule": hit.rule,
            "signature": signature,
            # J-R3 re-parses frames from this window (run["gate"] keeps it).
            "window": window,
        }
        _mark_learning_incident(system_id, body)
        _record_gate_decision(system_id, body)
        # NOTE: an `act` here is recorded + broadcast but starts no run:
        # log lines carry no metrics so act is unreachable today, and J-R3
        # wires production acts to the repo pipeline.
        decisions.append(body)
    return {
        "accepted": len(lines),
        "candidates": candidates,
        "decisions": decisions,
    }


def sentry_texts(payload: Dict[str, Any]) -> List[str]:
    """Render a Sentry issue-alert webhook as traceback-ish text lines."""
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    issue = data.get("issue", {}) if isinstance(data, dict) else {}
    if not isinstance(issue, dict):
        issue = {}
    title = str(issue.get("title", "") or "")
    metadata = issue.get("metadata", {}) or {}
    exc_type = str(metadata.get("type", "") or "")
    exc_value = str(metadata.get("value", "") or "")
    frames: List[str] = []
    entries = issue.get("entries", []) or []
    for item in entries:
        if not isinstance(item, dict) or item.get("type") != "stacktrace":
            continue
        stacked = (item.get("data", {}) or {}).get("frames", []) or []
        for frame in stacked:
            if not isinstance(frame, dict):
                continue
            name = frame.get("filename") or frame.get("module") or "?"
            try:
                lineno = int(frame.get("lineno") or 0)
            except (TypeError, ValueError):
                lineno = 0
            func = frame.get("function") or "?"
            frames.append(f'  File "{name}", line {lineno}, in {func}')
        break
    if frames:
        head = exc_type or "Error"
        tail = f"{head}: {exc_value}" if exc_value else head
        return [
            "Traceback (most recent call last):",
            *frames,
            tail,
        ]
    detail = " ".join(part for part in (title, exc_type, exc_value) if part)
    return [f"ERROR {detail}".strip() or "ERROR sentry alert"]
