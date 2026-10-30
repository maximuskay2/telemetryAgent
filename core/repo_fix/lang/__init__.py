"""Adapter registry: auto-discovery, parse, detect (languages §3, L-J0).

Every module in this package defining `ADAPTER` (or `ADAPTERS`, a list for
two-name modules like `javascript`/`typescript`) is registered — nobody
edits a shared list. `all_adapters()` returns python first, the rest
alphabetical (deterministic; each parser only accepts its own format so
order rarely matters).

Two refinements live here (not in the adapters): `detect_repo` reports
`typescript` when the repo has a `tsconfig.json` and `kotlin` when `.kt`
files are present, so `/connect` can name them; `by_name` resolves those
back to the `javascript` / `java` adapters through `_ALIASES`.
`registry.parse` stamps `info.language` with the accepting adapter's name
unless the parser preset something more specific.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, List, Optional, Tuple

from core.ingest.traceback import TracebackInfo
from core.repo_fix.lang.base import LanguageAdapter

#: Refined language name -> adapter that implements it.
_ALIASES: Dict[str, str] = {
    "typescript": "javascript",
    "kotlin": "java",
}


def all_adapters() -> List[LanguageAdapter]:
    """Every adapter in this package: python first, rest alphabetical.

    Modules define either `ADAPTER` (one language) or `ADAPTERS` (a list,
    for two-name modules); both shapes register. First registration wins
    on duplicate names.
    """
    found: Dict[str, LanguageAdapter] = {}
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_"):
            continue
        imported = importlib.import_module(f"{__name__}.{module.name}")
        candidates: List[LanguageAdapter] = []
        plural = getattr(imported, "ADAPTERS", None)
        if plural is not None:
            candidates.extend(list(plural))
        singular = getattr(imported, "ADAPTER", None)
        if singular is not None:
            candidates.append(singular)
        for adapter in candidates:
            if adapter.name not in found:
                found[adapter.name] = adapter
    return sorted(found.values(), key=lambda item: (item.name != "python", item.name))


def parse(text: str) -> Optional[Tuple[LanguageAdapter, TracebackInfo]]:
    """First adapter whose parser accepts `text`, with the parsed trace."""
    for adapter in all_adapters():
        try:
            info = adapter.parse_trace(text)
        except Exception:
            continue  # a parser must never break the chain
        if info is None:
            continue
        if info.language == "python" and adapter.name != "python":
            info.language = adapter.name
        return adapter, info
    return None


def by_name(name: str) -> Optional[LanguageAdapter]:
    """Adapter for a language name (aliases resolve to their adapter)."""
    adapters = all_adapters()
    for adapter in adapters:
        if adapter.name == name:
            return adapter
    want = _ALIASES.get(name, name)
    for adapter in adapters:
        if adapter.name == want:
            return adapter
    return None


def refined_name(name: str, paths: List[str]) -> str:
    """TypeScript/Kotlin refinements for repo-level detection."""
    if name == "javascript" and any(
        path == "tsconfig.json" or path.endswith("/tsconfig.json") for path in paths
    ):
        return "typescript"
    if name == "java" and any(path.endswith(".kt") for path in paths):
        return "kotlin"
    return name


def detect_repo(paths: List[str]) -> List[Tuple[str, int]]:
    """Languages present in a repo: [(name, score)] strongest first."""
    scored = []
    for adapter in all_adapters():
        try:
            score = adapter.detect(paths)
        except Exception:
            continue
        if score > 0:
            scored.append((refined_name(adapter.name, paths), score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored
