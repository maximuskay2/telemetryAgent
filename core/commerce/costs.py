"""Commercial §8.4: cost table (Jude owns).

COST_TABLE is our costs (what providers charge us), not customer
prices. Canonical per-model numbers live in the engine
(`core.usage.costs`, with source + verified provenance); this module
exposes the frozen §8.4 `COST_TABLE` dict view plus the costing
helpers `record_usage` uses to fill `cost_estimate_usd`.
"""

from __future__ import annotations

from core.usage import costs as _engine

# Frozen §8.4 name. JSON-safe: token rates as a list (exact model first,
# provider "default" fallback second), sandbox $/s as a map.
COST_TABLE: dict = {
    "tokens": [
        {
            "provider": "baseten",
            "model": "meta-models/muse-spark-open-1026",
            "input_usd_per_1m": 0.60,
            "output_usd_per_1m": 1.80,
            "source": "estimate from H100 market rate Oct 2026",
            "verified": False,
        },
        {
            "provider": "baseten",
            "model": "default",
            "input_usd_per_1m": 0.60,
            "output_usd_per_1m": 1.80,
            "source": "estimate from H100 market rate Oct 2026",
            "verified": False,
        },
        {
            "provider": "meta",
            "model": "muse-spark-1.3",
            "input_usd_per_1m": 0.50,
            "output_usd_per_1m": 1.50,
            "source": "estimate; Meta API pricing unpublished Oct 2026",
            "verified": False,
        },
        {
            "provider": "meta",
            "model": "muse-wonder-1.0",
            "input_usd_per_1m": 0.50,
            "output_usd_per_1m": 1.50,
            "source": "estimate; Meta API pricing unpublished Oct 2026",
            "verified": False,
        },
        {
            "provider": "meta",
            "model": "default",
            "input_usd_per_1m": 0.50,
            "output_usd_per_1m": 1.50,
            "source": "estimate; Meta API pricing unpublished Oct 2026",
            "verified": False,
        },
        {
            "provider": "fireworks",
            "model": "default",
            "input_usd_per_1m": 0.90,
            "output_usd_per_1m": 0.90,
            "source": "fireworks.ai/pricing serverless 16B+ tier Oct 2026",
            "verified": True,
        },
    ],
    "sandbox_usd_per_s": {
        "modal": 0.000046,  # modal.com/pricing CPU per second Oct 2026
        "docker": 0.0,      # local compute, no provider charge
    },
}


def rate_for(provider: str, model: str):
    """Best-known token rate (engine; env overrides apply)."""
    return _engine.rate_for(provider, model)


def cost_of_tokens(provider: str, model: str,
                   input_tokens: int, output_tokens: int) -> float:
    """USD estimate for one model call. Never raises."""
    return _engine.cost_of_tokens(provider, model,
                                  input_tokens, output_tokens)


def cost_of_sandbox(backend: str, seconds: float) -> float:
    """USD estimate for sandbox wall time. Never raises."""
    return _engine.cost_of_sandbox(backend, seconds)
