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
)
from core.repo_fix.lang import by_name as _adapter_by_name
from core.repo_fix.lang import parse as _registry_parse
from core.setup import gate as setup_gate
from core.setup import store as setup_store
from core.setup.modes import ModeState
from core.watch import rules

#: Gate windows are capped (tracebacks can be long).
MAX_WINDOW_CHARS = 4000
MAX_SIGNATURE_CHARS = 500

#: `sentry_texts` marks non-Python events with this first line so the
#: language survives even before its adapter exists (no route change: the
#: marker travels inside `texts`, `assemble` strips it for sentry keys).
SENTRY_LANG_PREFIX = "ta-language: "

_assemblers: Dict[str, TracebackAssembler] = {}


@dataclass
class Entry:
    text: str
    ts: float
    traceback: Optional[TracebackInfo] = None
    #: Sentry platform language for unparsed first lines (else None).
    hint: Optional[str] = None


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


def _parsed_trace(text: str) -> Optional[TracebackInfo]:
    """Traceback for joined text via the adapter registry (None if none)."""
    try:
        found = _registry_parse(text)
    except Exception:
        return None
    return found[1] if found is not None else None


def assemble(key: str, lines: List[str], now: float) -> List[Entry]:
    """Group raw lines into entries; one traceback = one entry."""
    hint: Optional[str] = None
    if (
        key.endswith(":sentry")
        and lines
        and lines[0].startswith(SENTRY_LANG_PREFIX)
    ):
        hint = lines[0][len(SENTRY_LANG_PREFIX):].strip() or None
        lines = lines[1:]
    assembler = _assembler_for(key)
    entries: List[Entry] = []
    for stale in assembler.flush_stale(now):
        entries.append(Entry(text=stale, ts=now))
    first_index = 0
    for line in lines:
        was_collecting = assembler.collecting
        completed = assembler.feed(line, now)
        if completed is not None:
            parsed = _parsed_trace(completed)
            entries.append(
                Entry(
                    text=completed, ts=now, traceback=parsed,
                    hint=hint if parsed is None else None,
                )
            )
            orphan = assembler.take_orphan()
            if orphan is not None:
                entries.append(Entry(text=orphan, ts=now))
        elif not was_collecting and not assembler.collecting:
            entries.append(
                Entry(
                    text=line, ts=now,
                    hint=hint if first_index == 0 else None,
                )
            )
        first_index += 1
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
    commit: str = "",
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
        if hit is None and (
            (entry.traceback is not None and entry.traceback.frames)
            or entry.hint
        ):
            # Parsed non-Python trace (rules only know the Python header
            # and ERROR), or an unparsed Sentry head line carrying its
            # platform language: still one error candidate.
            hit = rules.RuleHit(
                rule="traceback", level="error",
                resource=rules.extract_resource(entry.text),
                line=entry.text,
            )
        if hit is None:
            continue
        candidates += 1
        signature = _signature_for(entry)
        resource = rules.extract_resource(entry.text)
        fingerprint = rules.fingerprint_for(hit.rule, resource, signature)
        window = entry.text[:MAX_WINDOW_CHARS]
        language = (
            entry.traceback.language if entry.traceback is not None
            else entry.hint
        )
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
            "commit": commit,
        }
        if language:
            # Languages §3: the gate may carry the language; readers that
            # predate it ignore the new keys (additive, L-3).
            supported = _adapter_by_name(language) is not None
            body["language"] = language
            body["autofix"] = supported
            if not supported:
                body["autofix_note"] = (
                    f"auto-fix not supported for {language} yet"
                )
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


#: Sentry `issue.platform` → adapter language (L-J2). Siblings refine
#: below from frame filenames (`.ts` → typescript, `.kt` → kotlin).
_SENTRY_PLATFORMS = {
    "python": "python",
    "javascript": "javascript",
    "node": "javascript",
    "java": "java",
    "kotlin": "kotlin",
    "go": "go",
    "golang": "go",
    "rust": "rust",
    "php": "php",
}


def _sentry_issue(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    issue = data.get("issue", {}) if isinstance(data, dict) else {}
    return issue if isinstance(issue, dict) else {}


def _sentry_frames(issue: Dict[str, Any]) -> List[Dict[str, Any]]:
    for item in issue.get("entries", []) or []:
        if not isinstance(item, dict) or item.get("type") != "stacktrace":
            continue
        stacked = (item.get("data", {}) or {}).get("frames", []) or []
        return [frame for frame in stacked if isinstance(frame, dict)]
    return []


def sentry_language(payload: Dict[str, Any]) -> str:
    """Adapter language for a Sentry webhook (`platform`, else python).

    Missing platform keeps the legacy Python rendering (old webhooks are
    Python in practice); an unmapped platform passes through verbatim so
    the decision names it as unsupported instead of mistaking it.
    """
    issue = _sentry_issue(payload)
    platform = str(issue.get("platform", "") or "").strip().lower()
    if not platform:
        return "python"
    language = _SENTRY_PLATFORMS.get(platform, platform)
    if language in ("javascript", "java"):
        for frame in _sentry_frames(issue):
            name = str(frame.get("filename", "") or "")
            if language == "javascript" and name.endswith(
                (".ts", ".tsx", ".mts", ".cts")
            ):
                return "typescript"
            if language == "java" and name.endswith(".kt"):
                return "kotlin"
    return language


def _frame_name(frame: Dict[str, Any]) -> str:
    return str(frame.get("filename") or frame.get("module") or "?")


def _frame_lineno(frame: Dict[str, Any]) -> int:
    try:
        return int(frame.get("lineno") or 0)
    except (TypeError, ValueError):
        return 0


def _frame_func(frame: Dict[str, Any]) -> str:
    return str(frame.get("function") or "?")


def _sentry_native(
    language: str,
    exc_type: str,
    exc_value: str,
    frames: List[Dict[str, Any]],
) -> List[str]:
    """Native-shaped trace lines per §1.1 (no `ta-language` marker)."""
    head = exc_type or "Error"
    tail = f"{head}: {exc_value}" if exc_value else head
    if language in ("java", "kotlin"):
        lines = [tail]
        for frame in frames:
            module = str(frame.get("module") or "")
            func = _frame_func(frame)
            qualified = f"{module}.{func}" if module else func
            lines.append(
                f"\tat {qualified}"
                f"({_frame_name(frame)}:{_frame_lineno(frame)})"
            )
        return lines
    if language in ("javascript", "typescript"):
        lines = [tail]
        for frame in frames:
            func = _frame_func(frame)
            loc = f"{_frame_name(frame)}:{_frame_lineno(frame)}:1"
            if func in ("?", "<anonymous>"):
                lines.append(f"    at {loc}")
            else:
                lines.append(f"    at {func} ({loc})")
        return lines
    if language == "go":
        lines = [f"panic: {exc_value or exc_type or 'panic'}"]
        lines.append("goroutine 1 [running]:")
        for frame in frames:
            module = str(frame.get("module") or "")
            func = _frame_func(frame)
            lines.append(f"{module}.{func}()" if module else f"{func}()")
            lines.append(
                f"\t{_frame_name(frame)}:{_frame_lineno(frame)} +0x0"
            )
        return lines
    if language == "rust":
        if frames:
            first = frames[0]
            loc = f"{_frame_name(first)}:{_frame_lineno(first)}:1"
        else:
            loc = "unknown:0:1"
        lines = [f"thread 'main' panicked at {loc}:"]
        if exc_value or exc_type:
            lines.append(exc_value or exc_type)
        for frame in frames:
            lines.append(
                f"    at {_frame_func(frame)} "
                f"({_frame_name(frame)}:{_frame_lineno(frame)}:1)"
            )
        return lines
    if language == "php":
        if frames:
            first = frames[0]
            where = f"{_frame_name(first)}:{_frame_lineno(first)}"
        else:
            where = "unknown:0"
        lines = [f"PHP Fatal error:  Uncaught {tail} in {where}"]
        lines.append("Stack trace:")
        for index, frame in enumerate(frames):
            lines.append(
                f"#{index} {_frame_name(frame)}({_frame_lineno(frame)}): "
                f"{_frame_func(frame)}()"
            )
        return lines
    lines = [tail]  # unknown platform: plain, never Python-shaped
    for frame in frames:
        lines.append(
            f"  {_frame_name(frame)}:{_frame_lineno(frame)}"
            f" in {_frame_func(frame)}"
        )
    return lines


def sentry_texts(payload: Dict[str, Any]) -> List[str]:
    """Render a Sentry issue-alert webhook as traceback-ish text lines.

    Python (or a missing platform) renders exactly as before. Other
    platforms render their §1.1 shape behind a `ta-language:` marker so
    the language survives even before its adapter exists; the marker is
    stripped in `assemble` and never reaches a window or fingerprint.
    """
    issue = _sentry_issue(payload)
    title = str(issue.get("title", "") or "")
    metadata = issue.get("metadata", {}) or {}
    exc_type = str(metadata.get("type", "") or "")
    exc_value = str(metadata.get("value", "") or "")
    language = sentry_language(payload)
    frames = _sentry_frames(issue)
    if language == "python":
        rendered: List[str] = []
        for frame in frames:
            rendered.append(
                f'  File "{_frame_name(frame)}", '
                f"line {_frame_lineno(frame)}, in {_frame_func(frame)}"
            )
        if rendered:
            head = exc_type or "Error"
            tail = f"{head}: {exc_value}" if exc_value else head
            return [
                "Traceback (most recent call last):",
                *rendered,
                tail,
            ]
        detail = " ".join(
            part for part in (title, exc_type, exc_value) if part
        )
        return [f"ERROR {detail}".strip() or "ERROR sentry alert"]
    if not frames and not exc_type and not exc_value:
        detail = title.strip()
        line = f"ERROR {detail}".strip() or "ERROR sentry alert"
        return [f"{SENTRY_LANG_PREFIX}{language}", line]
    return [
        f"{SENTRY_LANG_PREFIX}{language}",
        *_sentry_native(language, exc_type, exc_value, frames),
    ]
