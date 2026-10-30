"""Local HS256 test issuer for commerce auth tests (C-J2).

Production verifies the provider (Clerk) session JWT via JWKS; tests set
`TA_AUTH_TEST_ISSUER=<secret>` and mint tokens with `mint(sub, email)`
instead — no network, no provider keys. Never set TA_AUTH_TEST_ISSUER in a
deployed environment.
"""

from __future__ import annotations

import os
import time
from typing import Optional

TEST_SECRET = "ta-auth-test-secret-not-for-prod"  # noqa: S105


def test_env() -> dict:
    return {"TA_AUTH_TEST_ISSUER": TEST_SECRET}


def mint(
    sub: str, email: str = "", secret: Optional[str] = None,
    ttl_s: int = 3600,
) -> str:
    import jwt

    now = int(time.time())
    return jwt.encode(
        {
            "sub": sub,
            "email": email,
            "iat": now,
            "exp": now + ttl_s,
        },
        secret if secret is not None else os.environ.get(
            "TA_AUTH_TEST_ISSUER", TEST_SECRET
        ),
        algorithm="HS256",
    )
