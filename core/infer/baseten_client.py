from __future__ import annotations

import json
import os
from typing import Optional

from core.infer.errors import translate
from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import GeneratedPatch, Runbook

BASETEN_BASE_URL = "https://inference.baseten.co/v1"
GENERATION_MODEL = os.getenv(
    "BASETEN_PATCH_MODEL", "meta-models/muse-spark-open-1026"
)


def _client():
    from openai import OpenAI

    key = os.environ.get("BASETEN_API_KEY", "")
    if not key:
        raise RuntimeError("Set BASETEN_API_KEY to use Muse Spark Open on Baseten.")
    return OpenAI(base_url=BASETEN_BASE_URL, api_key=key)


def generate(system_prompt: str, user_content: str) -> str:
    try:
        response = _client().chat.completions.create(
            model=GENERATION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise translate(exc, provider="Baseten", action="generation") from exc
    return response.choices[0].message.content


def generate_patch(
    diagnosis: Diagnosis,
    previous_stderr: Optional[str] = None,
    contract: Optional[str] = None,
) -> GeneratedPatch:
    feedback = f"\nThe previous attempt failed with:\n{previous_stderr}" if previous_stderr else ""
    pinned = f"\n\nInterface contract (the patch MUST satisfy this):\n{contract}" if contract else ""
    content = generate(
        "Return JSON with patch_code (solution.py) and test_code (pytest importing solution).",
        diagnosis.model_dump_json() + feedback + pinned,
    )
    return GeneratedPatch.model_validate(json.loads(content))


RUNBOOK_SYSTEM_PROMPT = (
    "Return JSON for an appliance diagnostic runbook: steps (string array of "
    "technician/owner actions), target_temperature_c (number), restart_delay_s "
    "(integer seconds, at least 180), power_off_minutes (number), "
    "disables_protection (boolean, must be false)."
)


def generate_runbook(
    diagnosis: Diagnosis, previous_feedback: Optional[str] = None
) -> Runbook:
    feedback = (
        f"\nThe previous attempt failed validation with:\n{previous_feedback}"
        if previous_feedback
        else ""
    )
    content = generate(
        RUNBOOK_SYSTEM_PROMPT, diagnosis.model_dump_json() + feedback
    )
    return Runbook.model_validate(json.loads(content))
