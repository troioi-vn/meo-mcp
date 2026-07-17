import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def now() -> datetime:
    return datetime.now(UTC)


def is_expired(value: datetime) -> bool:
    """Compare database timestamps safely, including SQLite test timestamps."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= now()


def token() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class TokenCipher:
    def __init__(self, encoded_key: str):
        try:
            key = base64.urlsafe_b64decode(encoded_key + "=" * (-len(encoded_key) % 4))
        except Exception as exc:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be base64url-encoded") from exc
        if len(key) != 32:
            raise ValueError("TOKEN_ENCRYPTION_KEY must contain exactly 32 bytes")
        self._cipher = AESGCM(key)

    def encrypt(self, value: str) -> str:
        nonce = secrets.token_bytes(12)
        return base64.urlsafe_b64encode(nonce + self._cipher.encrypt(nonce, value.encode(), None)).decode()

    def decrypt(self, value: str) -> str:
        raw = base64.urlsafe_b64decode(value)
        return self._cipher.decrypt(raw[:12], raw[12:], None).decode()


def signed_reference(payload: dict, secret: str) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
    signature = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest()
    return f"{raw}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
