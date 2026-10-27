"""Translate provider SDK errors into actionable failures (Day 7 hardening).

Duck-typed on `status_code` so it works with the real OpenAI-compatible SDK
errors and with simple test fakes. The loop's provider failover catches these
and tries the next provider; the API turns them into 503 responses.
"""

from __future__ import annotations

MAX_DETAIL_CHARS = 300


def translate(exc: Exception, *, provider: str, action: str) -> RuntimeError:
    """Build an actionable RuntimeError for a failed inference request."""
    status = getattr(exc, "status_code", None)
    detail = _truncate(str(exc) or type(exc).__name__)
    if status == 401:
        return RuntimeError(
            f"{provider} rejected the API key (401) during {action}. "
            "Check the key and its spend limits."
        )
    if status == 404:
        return RuntimeError(
            f"{provider} could not find the model (404) during {action}. "
            "Check the model id."
        )
    if status == 429:
        return RuntimeError(
            f"{provider} rate-limited the request (429) during {action}. "
            "The loop fails over to the next provider."
        )
    kind = type(exc).__name__.lower()
    if status is None and ("connection" in kind or "timeout" in kind):
        return RuntimeError(
            f"{provider} request to {action} failed transiently "
            f"({type(exc).__name__}: {detail})."
        )
    if status is None:
        return RuntimeError(f"{provider} request failed during {action}: {detail}.")
    return RuntimeError(
        f"{provider} request failed ({status}) during {action}: {detail}."
    )


def _truncate(text: str, limit: int = MAX_DETAIL_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
