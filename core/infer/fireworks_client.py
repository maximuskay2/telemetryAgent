from __future__ import annotations

import json
import os
from typing import Optional

from core.infer.errors import translate
from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import GeneratedPatch, Runbook

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"


def patch_model() -> str:
    return os.getenv("FIREWORKS_PATCH_MODEL", "")


def _client():
    from openai import OpenAI

    key = os.environ.get("FIREWORKS_API_KEY", "")
    if not key:
        raise RuntimeError("Set FIREWORKS_API_KEY to use the Fireworks backup provider.")
    if not patch_model():
        raise RuntimeError("Set FIREWORKS_PATCH_MODEL to the Muse Spark Open ID on Fireworks.")
    return OpenAI(base_url=FIREWORKS_BASE_URL, api_key=key)


def generate(system_prompt: str, user_content: str) -> str:
    try:
        response = _client().chat.completions.create(
            model=patch_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise translate(exc, provider="Fireworks", action="generation") from exc
    return response.choices[0].message.content


def generate_patch(diagnosis: Diagnosis, previous_stderr: Optional[str] = None) -> GeneratedPatch:
    feedback = f"\nThe previous attempt failed with:\n{previous_stderr}" if previous_stderr else ""
    content = generate(
        "Return JSON with patch_code (solution.py) and test_code (pytest importing solution).",
        diagnosis.model_dump_json() + feedback,
    )
    return GeneratedPatch.model_validate(json.loads(content))


def generate_runbook(
    diagnosis: Diagnosis, previous_feedback: Optional[str] = None
) -> Runbook:
    from core.infer.baseten_client import RUNBOOK_SYSTEM_PROMPT

    feedback = (
        f"\nThe previous attempt failed validation with:\n{previous_feedback}"
        if previous_feedback
        else ""
    )
    content = generate(
        RUNBOOK_SYSTEM_PROMPT, diagnosis.model_dump_json() + feedback
    )
    return Runbook.model_validate(json.loads(content))
