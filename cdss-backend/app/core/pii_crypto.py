"""
Encrypt patient PII at rest using Fernet (symmetric authenticated encryption).

Fernet uses AES-128 in CBC mode plus HMAC-SHA256 (see cryptography docs).
For field-level encryption compatible with SQLAlchemy String columns.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import String, TypeDecorator

from app.core.config import settings


def _fernet_key_bytes() -> bytes:
    raw = (getattr(settings, "PII_FERNET_KEY", None) or "").strip()
    if raw:
        return raw.encode("utf-8")
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    return Fernet(_fernet_key_bytes())


def encrypt_pii(plain: str) -> str:
    if plain is None:
        raise TypeError("plain must not be None")
    return get_fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_pii(token: Optional[str]) -> Optional[str]:
    if token is None:
        return None
    try:
        return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Legacy rows stored as plaintext during migration / dev resets
        return str(token)


class EncryptedString(TypeDecorator):
    """Maps Python str <-> Fernet ciphertext stored as ASCII string."""

    impl = String
    cache_ok = True

    def __init__(self, length: int = 512, **kw: Any):
        super().__init__(length, **kw)

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        s = str(value)
        if s.startswith("gAAAAA"):
            return s
        return encrypt_pii(s)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return decrypt_pii(value)
