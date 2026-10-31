from __future__ import annotations

import os

from core.schemas.diagnosis import Diagnosis


async def diagnose(log_text: str, reference: str = "") -> Diagnosis:
    """Diagnose via Muse Spark (Meta Model API, then Baseten if the id 404s)."""
    import asyncio
    from functools import partial

    from core.schemas.telemetry import SoftwareTelemetry

    telemetry = SoftwareTelemetry(source_id="diagnose", raw_log=log_text)
    payload = telemetry.model_dump_json()

    if os.getenv("MODEL_API_KEY") or os.getenv("META_MODEL_API_KEY"):
        from core.infer.meta_client import diagnose as meta_diagnose

        try:
            call = partial(meta_diagnose, payload, reference=reference)
            return await asyncio.to_thread(call)
        except RuntimeError as exc:
            if "could not find the model (404)" not in str(exc):
                raise
            if not os.getenv("BASETEN_API_KEY"):
                raise

    if os.getenv("BASETEN_API_KEY"):
        from core.infer.baseten_client import diagnose as baseten_diagnose

        call = partial(baseten_diagnose, payload, reference=reference)
        return await asyncio.to_thread(call)

    return Diagnosis(
        summary="Remote inference is not configured.",
        likely_cause="Set MODEL_API_KEY to request a Muse Spark diagnosis.",
        suggested_actions=["Review the log context and configure inference if needed."],
        confidence=0.0,
    )
