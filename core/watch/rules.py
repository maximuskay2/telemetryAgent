"""Trigger rules shared by the log and sensor watchers (Sim 2, Sim 4).

Warning rules cluster repeated signals (retries on the same item) so a storm
fires once; error rules fire on the failure line itself. Fingerprints are
error type + resource, so debounce is per incident, not per line.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

ERROR_PATTERNS = [
    ("deadlock", re.compile(r"deadlock", re.IGNORECASE)),
    ("traceback", re.compile(r"Traceback \(most recent call last\)")),
    ("error", re.compile(r"\bERROR\b")),
]

RETRY_RE = re.compile(r"\bretry=\d+\b", re.IGNORECASE)
ITEMS_RE = re.compile(r"items=([A-Za-z0-9_,-]+)")
ORDER_RE = re.compile(r"order=([A-Za-z0-9_-]+)")
TX_RE = re.compile(r"transaction=([A-Za-z0-9_-]+)")

RETRY_WINDOW_S = 30.0
RETRY_THRESHOLD = 2


@dataclass
class RuleHit:
    rule: str
    level: str  # warning | error
    resource: str
    line: str


def match_error(line: str) -> Optional[RuleHit]:
    """Match Deadlock / ERROR / Traceback lines; None for anything else."""
    for rule, compiled in ERROR_PATTERNS:
        if compiled.search(line):
            return RuleHit(
                rule=rule, level="error", resource=extract_resource(line), line=line
            )
    return None


def extract_resource(line: str) -> str:
    """Best resource key for a line: items, order, transaction, else empty."""
    for regex in (ITEMS_RE, ORDER_RE, TX_RE):
        found = regex.search(line)
        if found:
            return found.group(1)
    return ""


def fingerprint_for(rule: str, resource: str, line: str) -> str:
    """Stable incident id from error type + resource (numbers normalized)."""
    key = resource or re.sub(r"\d+", "#", line).strip()
    digest = hashlib.sha1(f"{rule}:{key}".encode()).hexdigest()
    return digest[:12]


@dataclass
class RetryClusterTracker:
    """Fires once when one item retries ≥ threshold times inside the window."""

    window_s: float = RETRY_WINDOW_S
    threshold: int = RETRY_THRESHOLD
    events: Dict[str, List[float]] = field(default_factory=dict)

    def observe(self, line: str, ts: float) -> Optional[RuleHit]:
        if not RETRY_RE.search(line):
            return None
        item = ITEMS_RE.search(line)
        resource = item.group(1) if item else "unknown"
        recent = [t for t in self.events.get(resource, []) if ts - t < self.window_s]
        recent.append(ts)
        self.events[resource] = recent
        if len(recent) >= self.threshold:
            self.events[resource] = []  # fire once per cluster
            return RuleHit(
                rule="retry-cluster", level="warning", resource=resource, line=line
            )
        return None
