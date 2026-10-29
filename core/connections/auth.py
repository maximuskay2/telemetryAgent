"""Key auth for the production route (J-R0 real).

`system_for_key` resolves an ingest/device `ta_live_*` key to the system it
belongs to via the hashed store. The `ta_live_fixture` key is accepted only
when `TA_FIXTURE_KEYS=1` (tests and John's stub-phase builds).
"""

from __future__ import annotations

import os
from typing import Optional

from core.connections import store as connection_store
from core.schemas.production import FIXTURE_KEY, FIXTURE_SYSTEM_ID


def fixture_keys_allowed() -> bool:
    return os.environ.get("TA_FIXTURE_KEYS", "").strip() == "1"


def system_for_key(key: str, kind: str) -> Optional[str]:
    """System id for `key`, or None when the key is unknown."""
    if key == FIXTURE_KEY and fixture_keys_allowed():
        return FIXTURE_SYSTEM_ID
    return connection_store.find_system_for_key(key, kind)
