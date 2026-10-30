"""Envelope encryption for org secrets (C-J1, §8.3 frozen shape).

One random data key per org, wrapped by the master key (`COMMERCE_MASTER_KEY`,
a base64 32-byte Fernet key held outside the DB). Connection secrets are
sealed with the org's data key and decrypted only in the calling process.

The store orchestration (get-or-create the wrapped data key on the org row)
lives in `repo.py`; this module holds the pure primitives plus the frozen
`encrypt_for_org` / `decrypt_for_org` entry points.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class CommerceCryptoError(RuntimeError):
    """Missing master key, or a blob that does not open."""


def _master_key() -> bytes:
    raw = os.environ.get("COMMERCE_MASTER_KEY", "").strip()
    if not raw:
        raise CommerceCryptoError(
            "COMMERCE_MASTER_KEY is not set "
            "(generate: python -c "
            "\"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\")"
        )
    try:
        key = base64.urlsafe_b64decode(raw.encode("ascii"))
    except ValueError as exc:
        raise CommerceCryptoError(
            "COMMERCE_MASTER_KEY is not valid base64"
        ) from exc
    if len(key) != 32:
        raise CommerceCryptoError(
            "COMMERCE_MASTER_KEY must decode to 32 bytes"
        )
    return raw.encode("ascii")


def new_data_key() -> bytes:
    """Fresh 32-byte org data key (raw bytes; store wrapped)."""
    return os.urandom(32)


def wrap_data_key(data_key: bytes) -> str:
    """Seal an org data key with the master key for the org row."""
    return Fernet(_master_key()).encrypt(data_key).decode("ascii")


def unwrap_data_key(blob: str) -> bytes:
    """Open a wrapped org data key with the master key."""
    try:
        return Fernet(_master_key()).decrypt(blob.encode("ascii"))
    except InvalidToken as exc:
        raise CommerceCryptoError(
            "org data key does not open with this master key"
        ) from exc


def seal(data_key: bytes, plaintext: str) -> str:
    """Encrypt a secret with an org data key (Fernet token, ascii)."""
    fernet = Fernet(base64.urlsafe_b64encode(data_key))
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def open_seal(data_key: bytes, blob: str) -> str:
    """Decrypt a sealed secret with an org data key."""
    fernet = Fernet(base64.urlsafe_b64encode(data_key))
    try:
        return fernet.decrypt(blob.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise CommerceCryptoError("secret does not open") from exc


def encrypt_for_org(
    org_id: str, plaintext: str, store: Optional[object] = None
) -> str:
    """Seal `plaintext` with `org_id`'s data key (creating it if needed)."""
    from core.commerce import repo as repo_module

    backend = store if store is not None else repo_module.get_store()
    data_key = backend.org_data_key(org_id)  # type: ignore[union-attr]
    return seal(data_key, plaintext)


def decrypt_for_org(
    org_id: str, blob: str, store: Optional[object] = None
) -> str:
    """Open a blob sealed by `encrypt_for_org`."""
    from core.commerce import repo as repo_module

    backend = store if store is not None else repo_module.get_store()
    data_key = backend.org_data_key(org_id)  # type: ignore[union-attr]
    return open_seal(data_key, blob)
