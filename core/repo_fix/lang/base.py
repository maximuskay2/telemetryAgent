"""Language-adapter protocol (languages-roadmap §3, frozen at L-J0).

One adapter per language implements `LanguageAdapter`; the registry in
`core/repo_fix/lang/__init__.py` auto-discovers every module in this
package that defines `ADAPTER` (or `ADAPTERS`, a list — see below). John
and Jude code their adapters to this text — it does not change after the
`lang-contracts-in` tag without all three agreeing (L-2).

Two names, one module: `javascript.py` serves `javascript` + `typescript`
and `java.py` serves `java` + `kotlin`. A module with two adapters defines
`ADAPTERS = [first, second]` (each with its own `name`); single-language
modules keep `ADAPTER = ...`. The registry accepts both shapes.

Manifest hook (optional): `suite_cmd` / `single_test_cmd` / `install_cmds`
see `paths` only, so a runner configured inside a manifest (e.g. the
`scripts` + `devDependencies` of a `package.json` with no config file) is
undetectable from names alone. Adapters that need manifest text MAY define:

    def manifest_names(self) -> List[str]: ...          # e.g. ["package.json"]
    def configure_manifests(self, manifests) -> None: ...  # {name: text|None}

`run.py` fetches each named manifest from the repo tree (None when absent)
and calls `configure_manifests` once before any command method. Adapters
that omit both get no manifests. JavaScript defaults to Jest when no
runner is detectable (config file, manifest, or runtime probe).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol


@dataclass
class SuiteResult:
    total: int
    passed: int
    failed: int
    failed_ids: List[str] = field(default_factory=list)
    #: Runner/compile error before any test ran (missing reports count).
    errored: bool = False


class LanguageAdapter(Protocol):
    name: str                      # "python" | "javascript" | ... (see §3)
    image: str                     # sandbox image key: "python"|"node"|"jvm"|"go"|"rust"|"php"
    install_timeout_s: int
    suite_timeout_s: int

    def detect(self, paths: List[str]) -> int: ...
    def trace_start(self, line: str) -> bool: ...
    def trace_continues(self, line: str) -> bool: ...
    def parse_trace(self, text: str): ...  # Optional[TracebackInfo], this format only
    def map_frame(self, frame_file: str, func: str, paths: List[str]) -> Optional[str]: ...
    def source_files(self, paths: List[str]) -> List[str]: ...
    def install_cmds(self, paths: List[str]) -> List[List[str]]: ...
    def suite_cmd(self, paths: List[str]) -> List[str]: ...
    def single_test_cmd(self, test_relpath: str, paths: List[str]) -> List[str]: ...
    def parse_results(
        self, stdout: str, stderr: str, read_file: Callable[[str], Optional[str]]
    ) -> SuiteResult: ...
    def repro_test_path(
        self, fingerprint: str, paths: List[str], located: List[str]
    ) -> str: ...
    def repro_rules(self) -> str: ...
    def looks_like_test(self, code: str) -> bool: ...
