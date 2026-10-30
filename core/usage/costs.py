"""Provider cost table: what providers charge US (not customer prices).

Every rate carries its provenance so the admin page can show which
numbers are measured and which are estimates awaiting invoice
reconciliation. Unknown models never raise: recording must never
crash the pipeline, so they fall back to the provider default, then
to a generic estimate.

Env overrides (all optional, take precedence over table defaults):
  TA_COST_<PROVIDER>_IN / _OUT   USD per 1M input/output tokens
      (providers: BASETEN, META, FIREWORKS)
  TA_COST_MODAL_SANDBOX_S        USD per Modal sandbox second
  TA_COST_DOCKER_SANDBOX_S       USD per local docker second
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# rate records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenRate:
    provider: str
    model: str  # exact model id, or "default" for the provider fallback
    input_usd_per_1m: float
    output_usd_per_1m: float
    source: str  # where the number came from
    verified: bool  # True only after invoice / dashboard confirmation


@dataclass(frozen=True)
class SandboxRate:
    backend: str  # "modal" | "docker"
    usd_per_second: float
    source: str
    verified: bool


# ---------------------------------------------------------------------------
# table defaults (October 2026; see `source` on each entry)
# ---------------------------------------------------------------------------

_TOKEN_RATES: dict[tuple[str, str], TokenRate] = {}


def _token(provider: str, model: str, inp: float, out: float,
            source: str, verified: bool = False) -> None:
    _TOKEN_RATES[(provider, model)] = TokenRate(
        provider=provider,
        model=model,
        input_usd_per_1m=inp,
        output_usd_per_1m=out,
        source=source,
        verified=verified,
    )


# Baseten: Muse Spark Open served on H100s. Baseten's own model-API
# pricing was not published; estimate from H100 market rate (~$2.50/hr).
_token("baseten", "meta-models/muse-spark-open-1026",
       0.60, 1.80, "estimate from H100 market rate Oct 2026")
_token("baseten", "default",
       0.60, 1.80, "estimate from H100 market rate Oct 2026")

# Meta inference API: no public per-token price found Oct 2026.
_token("meta", "muse-spark-1.3",
       0.50, 1.50, "estimate; Meta API pricing unpublished Oct 2026")
_token("meta", "muse-wonder-1.0",
       0.50, 1.50, "estimate; Meta API pricing unpublished Oct 2026")
_token("meta", "default",
       0.50, 1.50, "estimate; Meta API pricing unpublished Oct 2026")

# Fireworks: serverless 16B+ tier (Kimi K2 etc.), fireworks.ai/pricing.
_token("fireworks", "default",
       0.90, 0.90, "fireworks.ai/pricing serverless 16B+ tier Oct 2026",
       verified=True)

_GENERIC = TokenRate(
    provider="unknown",
    model="default",
    input_usd_per_1m=0.50,
    output_usd_per_1m=1.50,
    source="generic mid-size open-model estimate Oct 2026",
    verified=False,
)

_SANDBOX_RATES: dict[str, SandboxRate] = {
    # Modal CPU @ $0.000046/s
    # (modal.com/pricing "CPU per second", Oct 2026).
    "modal": SandboxRate(
        backend="modal",
        usd_per_second=0.000046,
        source="modal.com/pricing CPU per second Oct 2026",
        verified=True,
    ),
    # Local docker: our own machine, no marginal provider cost.
    "docker": SandboxRate(
        backend="docker",
        usd_per_second=0.0,
        source="local compute, no provider charge",
        verified=True,
    ),
}


# ---------------------------------------------------------------------------
# lookup + costing
# ---------------------------------------------------------------------------


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def rate_for(provider: str, model: str) -> TokenRate:
    """Best-known rate for a (provider, model) pair, with provenance.

    Exact model -> provider default -> generic estimate. Never raises.
    Env overrides replace the per-token numbers but keep the source note.
    """
    provider = (provider or "").lower()
    base = _TOKEN_RATES.get((provider, model))
    if base is None:
        base = _TOKEN_RATES.get((provider, "default"), _GENERIC)
    env_in = _env_float(f"TA_COST_{provider.upper()}_IN")
    env_out = _env_float(f"TA_COST_{provider.upper()}_OUT")
    if env_in is None and env_out is None:
        return base
    return TokenRate(
        provider=base.provider,
        model=base.model,
        input_usd_per_1m=env_in if env_in is not None else base.input_usd_per_1m,
        output_usd_per_1m=env_out if env_out is not None else base.output_usd_per_1m,
        source=f"{base.source} [env override]",
        verified=base.verified,
    )


def cost_of_tokens(provider: str, model: str,
                   input_tokens: int, output_tokens: int) -> float:
    """USD estimate for one model call. Never raises; unknown -> default."""
    rate = rate_for(provider, model)
    try:
        inp = max(0, int(input_tokens))
        out = max(0, int(output_tokens))
    except (TypeError, ValueError):
        return 0.0
    return inp / 1_000_000 * rate.input_usd_per_1m + out / 1_000_000 * rate.output_usd_per_1m


def sandbox_rate_for(backend: str) -> SandboxRate:
    """Best-known rate for a sandbox backend. Never raises."""
    backend = (backend or "").lower()
    base = _SANDBOX_RATES.get(backend, _SANDBOX_RATES["docker"])
    env = _env_float(f"TA_COST_{backend.upper()}_SANDBOX_S")
    if env is None:
        return base
    return SandboxRate(
        backend=base.backend,
        usd_per_second=env,
        source=f"{base.source} [env override]",
        verified=base.verified,
    )


def cost_of_sandbox(backend: str, seconds: float) -> float:
    """USD estimate for sandbox wall time. Never raises."""
    try:
        secs = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return 0.0
    return secs * sandbox_rate_for(backend).usd_per_second
