"""Key auth for the production route (H0 stub).

`system_for_key` resolves an ingest/device `ta_live_*` key to the system it
belongs to. Until J-R0 lands the real hashed-key store, only the fixture
key from §3.4 is accepted; J-R0 keeps accepting it only when
`TA_FIXTURE_KEYS=1`.
"""

from __future__ import annotations

from typing import Optional

from core.schemas.production import FIXTURE_KEY, FIXTURE_SYSTEM_ID


def system_for_key(key: str, kind: str) -> Optional[str]:
    """System id for `key`, or None when the key is unknown (H0 stub)."""
    _ = kind  # kinds share one key space until the real store lands.
    if key == FIXTURE_KEY:
        return FIXTURE_SYSTEM_ID
    return None
