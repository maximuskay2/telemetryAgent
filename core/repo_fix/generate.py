"""Generation for repo fixes: repro test, patch, file picks (J-R3).

Attempts 1..n-1 use Muse Spark Open on Baseten; the final attempt
escalates to Muse Wonder on the Meta Model API (same shape as the demo
loop's escalation). JSON out, validated strictly: the repro test must
define tests, the patch touches at most 3 known files.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.infer import baseten_client
from core.repo_fix.lang import by_name as _adapter_by_name
from core.infer.errors import translate
from core.infer.meta_client import ESCALATION_MODEL, META_BASE_URL

#: Fallback when no adapter is passed (V1: via the registry, never a
#: direct adapter-module read).
_PYTHON = _adapter_by_name("python")
assert _PYTHON is not None  # lang/python.py must register

MAX_PATCH_FILES = 3

#: chars/token estimate (providers don't report usage through these
#: thin clients; Jude's cost table prices the quantities either way).
_CHARS_PER_TOKEN = 4


def _record_model_call(
    provider: str,
    model: str,
    prompt_chars: int,
    completion_chars: int,
    org_id: str = "",
    system_id: str = "",
    run_id: str = "",
    language: str = "",
) -> None:
    """Log one LLM call as tokens_in/out usage (never raises).

    Untagged sim/demo runs record nothing; org runs attribute spend to
    the org. Vocabulary comes from Jude's Kind (status coordination).
    """
    if not org_id or org_id == "demo":
        return
    try:
        from core.commerce.usage import Kind, record_usage

        tokens_in = max(1, int(prompt_chars / _CHARS_PER_TOKEN))
        tokens_out = max(1, int(completion_chars / _CHARS_PER_TOKEN))
        record_usage(
            org_id, Kind.MODEL_CALL, quantity=tokens_in,
            unit="tokens_in", system_id=system_id, run_id=run_id,
            provider=provider, model=model, language=language,
        )
        record_usage(
            org_id, Kind.MODEL_CALL, quantity=tokens_out,
            unit="tokens_out", system_id=system_id, run_id=run_id,
            provider=provider, model=model, language=language,
        )
    except Exception:
        pass

#: Generic repro prompt; the adapter's repro_rules() is appended (§3).
REPRO_BASE = (
    "You write ONE test file that reproduces a production crash. "
    "Return JSON {\"test_code\": \"...\"} only. Rules: import the repo's "
    "own modules exactly as laid out in the file list; the test MUST fail "
    "on the current code and pass once the bug is fixed; no network, no "
    "sleep, deterministic. "
)


def _wonder_generate(system_prompt: str, user_content: str) -> str:
    """One Meta Model API call on the escalation model (own stanza).

    meta_client has no generic prompt entrypoint and that file is not
    James's to edit, so the ~10 lines live here instead.
    """
    from openai import OpenAI

    key = os.environ.get("MODEL_API_KEY") or os.environ.get(
        "META_MODEL_API_KEY", ""
    )
    if not key:
        raise RuntimeError("Set MODEL_API_KEY to use the Meta Model API.")
    try:
        response = OpenAI(base_url=META_BASE_URL, api_key=key).chat.completions.create(
            model=ESCALATION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise translate(exc, provider="Meta Model API", action="generation") from exc
    return response.choices[0].message.content


def generate_json(
    system_prompt: str,
    user_content: str,
    attempt: int,
    max_attempts: int,
    org_id: str = "",
    system_id: str = "",
    run_id: str = "",
    language: str = "",
) -> Tuple[Dict[str, Any], str]:
    """JSON from Baseten, or Wonder on the final attempt."""
    prompt_chars = len(system_prompt) + len(user_content)
    if attempt >= max_attempts:
        content = _wonder_generate(system_prompt, user_content)
        _record_model_call(
            "meta", ESCALATION_MODEL, prompt_chars, len(content),
            org_id, system_id, run_id, language,
        )
        return json.loads(content), f"meta:{ESCALATION_MODEL}"
    content = baseten_client.generate(system_prompt, user_content)
    _record_model_call(
        "baseten", baseten_client.GENERATION_MODEL, prompt_chars,
        len(content), org_id, system_id, run_id, language,
    )
    return json.loads(content), f"baseten:{baseten_client.GENERATION_MODEL}"


def generate_repro_test(
    traceback_text: str,
    exc_signature: str,
    contexts: List[Dict[str, Any]],
    file_list: List[str],
    previous_output: Optional[str],
    attempt: int,
    max_attempts: int,
    test_path: str,
    adapter: Any = None,
    org_id: str = "",
    system_id: str = "",
    run_id: str = "",
    language: str = "",
) -> Tuple[str, str]:
    """Repro test source + model label; raises when unusable."""
    checker = adapter if adapter is not None else _PYTHON
    shown_files = "\n".join(file_list[:120])
    shown_contexts = "\n\n".join(
        f"--- {item['path']} (error near line {item.get('line', '?')}) ---\n"
        f"{item.get('context', '')}"
        for item in contexts[:5]
    )
    feedback = (
        f"\nThe previous test did not fail on the original code. "
        f"Pytest output:\n{previous_output}"
        if previous_output
        else ""
    )
    user_content = (
        f"Traceback:\n{traceback_text}\n\n"
        f"Exception: {exc_signature}\n\n"
        f"Repo layout (test will live at {test_path}):\n{shown_files}\n\n"
        f"Suspect code:\n{shown_contexts}{feedback}"
    )
    parsed, model_used = generate_json(
        REPRO_BASE + checker.repro_rules(),
        user_content,
        attempt,
        max_attempts,
        org_id=org_id,
        system_id=system_id,
        run_id=run_id,
        language=language or getattr(checker, "name", ""),
    )
    test_code = str(parsed.get("test_code", "") or "")
    if not checker.looks_like_test(test_code):
        raise ValueError("generated repro test defines no test_ function")
    return test_code, model_used


PATCH_SYSTEM = (
    "You fix a production bug. Return JSON "
    "{\"files\": [{\"path\": ..., \"content\": ...}]} only. Rules: at most "
    "3 files, each an EXISTING repo path with its COMPLETE new content; "
    "minimal diff that makes the failing test pass without breaking "
    "others; no new dependencies; never touch tests outside the given "
    "repro test."
)


def generate_patch(
    traceback_text: str,
    exc_signature: str,
    diagnosis: str,
    contexts: List[Dict[str, Any]],
    known_paths: List[str],
    repro_output: str,
    attempt: int,
    max_attempts: int,
    org_id: str = "",
    system_id: str = "",
    run_id: str = "",
    language: str = "",
) -> Tuple[List[Dict[str, str]], str, str]:
    """Patch files + model label + note. Raises when unusable."""
    shown_contexts = "\n\n".join(
        f"--- {item['path']} ---\n{item.get('context', '')}"
        for item in contexts[:5]
    )
    user_content = (
        f"Traceback:\n{traceback_text}\n\n"
        f"Diagnosis: {diagnosis}\n\n"
        f"Failing repro test output:\n{repro_output}\n\n"
        f"Suspect code:\n{shown_contexts}"
    )
    parsed, model_used = generate_json(
        PATCH_SYSTEM, user_content, attempt, max_attempts,
        org_id=org_id, system_id=system_id, run_id=run_id,
        language=language,
    )
    raw = parsed.get("files", []) or []
    files: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "") or "").strip()
        content = str(item.get("content", "") or "")
        if path in known_paths and content.strip():
            files.append({"path": path, "content": content})
    note = ""
    if len(files) > MAX_PATCH_FILES:
        note = (
            f"model proposed {len(files)} files; kept the first "
            f"{MAX_PATCH_FILES}"
        )
        files = files[:MAX_PATCH_FILES]
    if not files:
        raise ValueError("generated patch touches no known repo file")
    return files, model_used, note


PICK_SYSTEM = (
    "Pick the repo files most likely to contain a bug. Return JSON "
    "{\"files\": [...]} with at most 5 paths copied EXACTLY from the "
    "candidate list."
)


def choose_files(
    ranked: List[str],
    exc_signature: str,
    generate: Optional[Callable[[str, str], str]] = None,
    org_id: str = "",
    system_id: str = "",
    run_id: str = "",
    language: str = "",
) -> List[str]:
    """Model file picks for frameless errors (fallback: rank order)."""
    call = generate or baseten_client.generate
    user_content = (
        f"Exception: {exc_signature}\n\nCandidates:\n"
        + "\n".join(ranked)
    )
    content = call(PICK_SYSTEM, user_content)
    _record_model_call(
        "baseten", baseten_client.GENERATION_MODEL,
        len(PICK_SYSTEM) + len(user_content), len(content or ""),
        org_id, system_id, run_id, language,
    )
    try:
        picked = json.loads(content).get("files", []) or []
    except ValueError:
        return ranked[:5]
    known = [path for path in picked if path in ranked]
    return (known or ranked)[:5]
