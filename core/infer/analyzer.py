from __future__ import annotations

import os

from core.schemas.diagnosis import Diagnosis


async def diagnose(log_text: str) -> Diagnosis:
    """Diagnose via Muse Spark on the Meta Model API (Meta models only)."""
    if os.getenv("MODEL_API_KEY") or os.getenv("META_MODEL_API_KEY"):
        import asyncio

        from core.infer.meta_client import diagnose as meta_diagnose
        from core.schemas.telemetry import SoftwareTelemetry

        telemetry = SoftwareTelemetry(source_id="diagnose", raw_log=log_text)
        return await asyncio.to_thread(meta_diagnose, telemetry.model_dump_json())

    return Diagnosis(
        summary="Remote inference is not configured.",
        likely_cause="Set MODEL_API_KEY to request a Muse Spark diagnosis.",
        suggested_actions=["Review the log context and configure inference if needed."],
        confidence=0.0,
    )
