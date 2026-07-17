import base64

from meo_mcp.security import TokenCipher, digest, signed_reference


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
