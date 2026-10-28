"""Interface contracts for allowlisted demo targets.

A patch can pass sandbox tests yet break the shop when it does not implement
the module interface the shop actually calls (e2e, Oct 28: a SQL-retry helper
with no `acquire_all` passed verify, deployed, and 500'd every order). These
helpers pin the contract in one place; generation prompts, the sandbox
harness, the deploy gate, and the shop reload gate all share them.
"""

from __future__ import annotations

import inspect
import threading
import time
from types import ModuleType
from typing import Callable, Optional

REQUIRED_FUNCTIONS = ("acquire_all", "release_all")

# Smoke SKUs never collide with the demo catalog; the check only proves the
# call shape works, not that the fix is correct (the harness proves that).
_SMOKE_ITEMS = ["__contract_b__", "__contract_a__"]

#: Threads × rounds for the best-effort deadlock probe (the canonical-order
#: assertion below it is the deterministic check).
_HARNESS_THREADS = 4
_HARNESS_ROUNDS = 10
_HARNESS_JOIN_S = 10.0


def load_module_from_source(
    source: str, name: str = "candidate_inventory"
) -> ModuleType:
    """Import untrusted source into a fresh, isolated module object."""
    module = ModuleType(name)
    exec(compile(source, f"<{name}>", "exec"), module.__dict__)
    return module


def check_inventory_module(module: object) -> Optional[str]:
    """Fast shape check: required functions + a no-raise round-trip.

    Returns None when the module is a plausible drop-in, else the reason.
    Used by the deploy gate and the shop reload gate (cheap, in-process).
    """
    for func in REQUIRED_FUNCTIONS:
        if not callable(getattr(module, func, None)):
            return f"missing required function: {func}(...)"
    acquire = getattr(module, "acquire_all")
    release = getattr(module, "release_all")
    try:
        held = acquire(list(_SMOKE_ITEMS))
    except Exception as exc:  # noqa: BLE001 - any raise fails the shape check
        return f"acquire_all smoke call failed: {type(exc).__name__}: {exc}"
    try:
        release(held)
    except Exception as exc:  # noqa: BLE001 - any raise fails the shape check
        return f"release_all smoke call failed: {type(exc).__name__}: {exc}"
    return None


def check_inventory_source(source: str) -> Optional[str]:
    """Shape-check patch source without touching the filesystem."""
    try:
        module = load_module_from_source(source)
    except Exception as exc:  # noqa: BLE001 - report, don't crash the gate
        return f"module does not import: {type(exc).__name__}: {exc}"
    return check_inventory_module(module)


def run_inventory_harness(module: object) -> list[str]:
    """Repo-owned conformance probe; violations (empty means conforming).

    Deterministic part: interface presence, round-trip, and canonical
    (sorted) acquisition order — the documented contract in
    `demo/target-service/inventory.py`. Best-effort part: concurrent
    overlapping acquires must all finish (a deadlock fails the join).
    Stdlib only so the same function runs in-process and in the sandbox.
    """
    violations: list[str] = []
    for func in REQUIRED_FUNCTIONS:
        if not callable(getattr(module, func, None)):
            violations.append(f"missing required function: {func}(...)")
    if violations:
        return violations
    acquire = getattr(module, "acquire_all")
    release = getattr(module, "release_all")
    try:
        held = acquire(["brake-pad", "axle"])
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        return [f"acquire_all raised {type(exc).__name__}: {exc}"]
    try:
        order = [item for item, _ in held]
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        order = []
        violations.append(f"acquire_all return shape unreadable: {exc}")
    if order != sorted(order):
        violations.append(
            f"acquisition order not canonical: {order} (must be sorted)"
        )
    try:
        release(held)
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        violations.append(f"release_all raised {type(exc).__name__}: {exc}")
    errors: list[str] = []

    def worker(pair: list[str]) -> None:
        try:
            for _ in range(_HARNESS_ROUNDS):
                release(acquire(list(pair)))
        except Exception as exc:  # noqa: BLE001 - collected below
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [
        threading.Thread(
            target=worker,
            args=(["axle", "brake-pad"] if i % 2 else ["brake-pad", "axle"],),
            daemon=True,
        )
        for i in range(_HARNESS_THREADS)
    ]
    deadline = time.time() + _HARNESS_JOIN_S
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=max(0.1, deadline - time.time()))
        if thread.is_alive():
            violations.append("concurrent overlapping acquires deadlocked")
            break
    violations.extend(f"worker: {message}" for message in errors)
    return violations


def _harness_pytest_source() -> str:
    """Self-contained pytest file: the sandbox has no repo to import."""
    runner = inspect.getsource(run_inventory_harness)
    consts = (
        f"REQUIRED_FUNCTIONS = {REQUIRED_FUNCTIONS!r}\n"
        f"_HARNESS_THREADS = {_HARNESS_THREADS}\n"
        f"_HARNESS_ROUNDS = {_HARNESS_ROUNDS}\n"
        f"_HARNESS_JOIN_S = {_HARNESS_JOIN_S}\n"
    )
    return (
        "import threading\n"
        "import time\n\n"
        "import solution\n\n"
        f"{consts}\n"
        f"{runner}\n"
        "def test_inventory_contract():\n"
        "    violations = run_inventory_harness(solution)\n"
        "    assert violations == [], '; '.join(violations)\n"
    )


#: Pytest file executed against the patch in the sandbox before fail-to-pass.
HARNESS_PYTEST = _harness_pytest_source()


def inventory_contract(original_code: str) -> str:
    """Generation prompt section: the patch must be a drop-in replacement."""
    return (
        "Interface contract — the patch MUST be a complete, stdlib-only, "
        "drop-in replacement for the original module below, keeping these "
        "exact public functions:\n"
        "  acquire_all(items: list[str]) -> list[tuple[str, Lock]]: acquire "
        "one threading.Lock per item in canonical (sorted-by-name) order and "
        "return them; concurrent callers with overlapping items must never "
        "deadlock.\n"
        "  release_all(acquired) -> None: release previously acquired locks "
        "in reverse order.\n"
        "Do not invent other APIs, SQL, or dependencies. Your test_code MUST "
        "import the module under test and exercise acquire_all/release_all "
        "(round-trip plus concurrent overlapping acquires).\n"
        "Original buggy module:\n"
        f"{original_code}"
    )


def contract_for_target(
    target: Optional[str], original_code: Optional[str] = None
) -> tuple[Optional[str], Optional[str]]:
    """Return (generation contract, sandbox harness) for a known target."""
    if target != "inventory" or not original_code:
        return None, None
    return inventory_contract(original_code), HARNESS_PYTEST


#: Type of the per-target contract resolver (for dependency injection).
ContractResolver = Callable[
    [Optional[str], Optional[str]], tuple[Optional[str], Optional[str]]
]
