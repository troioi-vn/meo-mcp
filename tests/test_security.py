import base64
import logging

import structlog

from meo_mcp.config import Settings
from meo_mcp.main import create_app
from meo_mcp.security import TokenCipher, digest, redact_log_event, signed_reference


def test_token_cipher_round_trip_and_hashing() -> None:
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    cipher = TokenCipher(key)
    encrypted = cipher.encrypt("sanctum-secret")
    assert encrypted != "sanctum-secret"
    assert cipher.decrypt(encrypted) == "sanctum-secret"
    assert digest("value") != "value"


def test_signed_reference_is_stable_for_verification() -> None:
    reference = signed_reference({"request_id": "a", "exp": 1}, "secret")
    body, signature = reference.split(".")
    assert body and signature


def test_structured_log_capture_redacts_all_credential_classes(caplog) -> None:
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    create_app(
        Settings(
            database_url="sqlite+aiosqlite:///ignored.db",
            token_encryption_key=key,
            meo_connector_hmac_secret="configured-hmac",
            meo_connector_api_key="configured-api-key",
        )
    )
    secrets = {
        "access_token": "mcp-access-secret",
        "refresh_token": "mcp-refresh-secret",
        "sanctum_token": "sanctum-pat-secret",
        "api_key": "connector-api-secret",
        "authorization_code": "authorization-code-secret",
        "hmac": "hmac-material-secret",
        "client_secret": "dcr-client-secret",
    }
    with caplog.at_level(logging.INFO):
        structlog.get_logger("meo_mcp.redaction_test").info("redaction_probe", **secrets)

    for secret in secrets.values():
        assert secret not in caplog.text
    assert caplog.text.count("[REDACTED]") == len(secrets)


def test_redaction_processor_handles_nested_token_fields() -> None:
    event = redact_log_event(
        None,
        "info",
        {"nested": {"token": "secret", "safe": "request-123"}},
    )
    assert event == {"nested": {"token": "[REDACTED]", "safe": "request-123"}}
