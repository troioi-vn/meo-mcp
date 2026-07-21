import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Normalize database timestamps, including SQLite's naive test values, to UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def is_expired(value: datetime) -> bool:
    """Compare database timestamps safely, including SQLite test timestamps."""
    return as_utc(value) <= now()


def epoch_seconds(value: datetime) -> int:
    """Convert database timestamps to the integer UTC epoch expected by MCP."""
    return int(as_utc(value).timestamp())


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
        return base64.urlsafe_b64encode(
            nonce + self._cipher.encrypt(nonce, value.encode(), None)
        ).decode()

    def decrypt(self, value: str) -> str:
        raw = base64.urlsafe_b64decode(value)
        return self._cipher.decrypt(raw[:12], raw[12:], None).decode()


def signed_reference(payload: dict, secret: str) -> str:
    raw = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )
    signature = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest()
    return f"{raw}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "authorization_code",
    "client_secret",
    "code",
    "code_verifier",
    "delegated_token",
    "hmac_secret",
    "hmac",
    "meo_connector_api_key",
    "refresh_token",
    "request_ref",
    "sanctum_token",
    "token",
    "token_encryption_key",
}


def redact_log_event(
    _logger: object, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Remove credential-bearing fields before a structured event reaches a logger."""

    def redact(value: Any, key: str | None = None) -> Any:
        normalized = key.lower() if key else ""
        if normalized in _SENSITIVE_KEYS or normalized.endswith(("_secret", "_token")):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                nested_key: redact(nested_value, nested_key)
                for nested_key, nested_value in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [redact(item) for item in value]
        return value

    return redact(event_dict)
