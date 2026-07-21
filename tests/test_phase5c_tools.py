import base64
import hashlib
import json
from datetime import timedelta
from ipaddress import ip_address
from uuid import uuid4

import httpx
import pytest
import respx

from meo_mcp.config import Settings
from meo_mcp.database import AccessTokenRecord, Base, Grant, make_session_factory
from meo_mcp.main import create_app
from meo_mcp.meo_api import PHOTO_MAX_BYTES, MeoApi
from meo_mcp.oauth import ALLOWED_SCOPES
from meo_mcp.security import TokenCipher, digest, now


async def _app_with_token(tmp_path, scopes: list[str]):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase5c.db'}"
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    settings = Settings(
        database_url=database_url,
        token_encryption_key=key,
        meo_connector_hmac_secret="hmac",
        meo_connector_api_key="key",
    )
    engine, sessions = make_session_factory(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    grant = Grant(
        id=uuid4(),
        client_id="client",
        subject="42",
        scopes=scopes,
        delegated_token_ciphertext=TokenCipher(key).encrypt("delegated"),
        expires_at=now() + timedelta(days=1),
    )
    async with sessions() as session:
        session.add(grant)
        await session.flush()
        session.add(
            AccessTokenRecord(
                token_hash=digest("access"),
                grant_id=grant.id,
                client_id="client",
                scopes=scopes,
                subject="42",
                resource=settings.resource,
                expires_at=now() + timedelta(hours=1),
            )
        )
        await session.commit()
    return create_app(settings), engine, settings


async def _call(client: httpx.AsyncClient, name: str, arguments: dict):
    response = await client.post(
        "/mcp",
        headers={"Authorization": "Bearer access", "Accept": "application/json"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200
    return response.json()["result"]


def _transaction(*, has_receipt: bool, version: str) -> dict:
    return {
        "data": {
            "id": 31,
            "ledger_id": 11,
            "account_id": 7,
            "type": "expense",
            "amount": "4.25",
            "amount_minor": 425,
            "occurred_on": "2026-07-21",
            "has_receipt": has_receipt,
            "updated_at": version,
        }
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mime", "content_type"),
    [("image/png", "image"), ("application/pdf", "resource")],
)
async def test_inspect_receipt_returns_bounded_mcp_content_without_binary_metadata(
    tmp_path, mime: str, content_type: str
) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read"])
    receipt = b"private-receipt"
    with respx.mock:
        respx.get("https://app.example.com/api/ledgers/11/transactions/31").mock(
            return_value=httpx.Response(200, json=_transaction(has_receipt=True, version="t1"))
        )
        respx.get("https://app.example.com/api/ledgers/11/transactions/31/receipt").mock(
            return_value=httpx.Response(200, content=receipt, headers={"Content-Type": mime})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "inspect_ledger_transaction_receipt",
                {"ledger_id": 11, "transaction_id": 31},
            )

    metadata = result["structuredContent"]["receipt"]
    assert metadata == {
        "transaction_id": 31,
        "present": True,
        "mime_type": mime,
        "byte_size": len(receipt),
        "sha256": hashlib.sha256(receipt).hexdigest(),
        "version": "t1",
    }
    assert result["content"][1]["type"] == content_type
    assert (
        base64.b64decode(
            result["content"][1].get("data") or result["content"][1]["resource"]["blob"]
        )
        == receipt
    )
    assert "blob" not in json.dumps(metadata)
    assert "url" not in json.dumps(metadata)
    await engine.dispose()


@pytest.mark.asyncio
async def test_inspect_absent_and_invalid_receipts_are_structured(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read"])
    detail = respx.get("https://app.example.com/api/ledgers/11/transactions/31")
    with respx.mock:
        detail.mock(
            side_effect=[
                httpx.Response(200, json=_transaction(has_receipt=False, version="t1")),
                httpx.Response(200, json=_transaction(has_receipt=True, version="t2")),
            ]
        )
        receipt = respx.get("https://app.example.com/api/ledgers/11/transactions/31/receipt").mock(
            return_value=httpx.Response(
                200, content=b"text", headers={"Content-Type": "text/plain"}
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            absent = await _call(
                client,
                "inspect_ledger_transaction_receipt",
                {"ledger_id": 11, "transaction_id": 31},
            )
            invalid = await _call(
                client,
                "inspect_ledger_transaction_receipt",
                {"ledger_id": 11, "transaction_id": 31},
            )

    assert absent["structuredContent"]["receipt"]["present"] is False
    assert len(absent["content"]) == 1
    assert receipt.call_count == 1
    assert invalid["isError"] is True
    assert invalid["structuredContent"]["error"]["code"] == "receipt_content_invalid"
    await engine.dispose()


@pytest.mark.asyncio
async def test_receipt_upload_and_delete_are_exact_and_post_write_verified(
    tmp_path, monkeypatch
) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read", "finance:write"])

    async def public_addresses(_: str):
        return {ip_address("93.184.216.34")}

    monkeypatch.setattr(MeoApi, "_public_addresses", staticmethod(public_addresses))
    with respx.mock:
        source = respx.get("https://93.184.216.34/receipt.pdf").mock(
            return_value=httpx.Response(
                200, content=b"%PDF-safe", headers={"Content-Type": "application/pdf"}
            )
        )
        respx.get("https://app.example.com/api/ledgers/11/transactions/31").mock(
            side_effect=[
                httpx.Response(200, json=_transaction(has_receipt=False, version="t1")),
                httpx.Response(200, json=_transaction(has_receipt=True, version="t2")),
                httpx.Response(200, json=_transaction(has_receipt=True, version="t2")),
                httpx.Response(200, json=_transaction(has_receipt=False, version="t3")),
            ]
        )
        upload = respx.post("https://app.example.com/api/ledgers/11/transactions/31/receipt").mock(
            return_value=httpx.Response(201, json={"data": {"id": 51}})
        )
        delete = respx.delete(
            "https://app.example.com/api/ledgers/11/transactions/31/receipt"
        ).mock(return_value=httpx.Response(204))
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            uploaded = await _call(
                client,
                "upload_ledger_transaction_receipt_from_url",
                {
                    "ledger_id": 11,
                    "transaction_id": 31,
                    "expected_has_receipt": False,
                    "base_version": "t1",
                    "source_url": "https://receipts.example/receipt.pdf",
                    "idempotency_key": "receipt-upload",
                },
            )
            deleted = await _call(
                client,
                "delete_ledger_transaction_receipt",
                {
                    "ledger_id": 11,
                    "transaction_id": 31,
                    "expected_has_receipt": True,
                    "base_version": "t2",
                    "idempotency_key": "receipt-delete",
                },
            )

    assert uploaded["structuredContent"]["uploaded"] is True
    assert uploaded["structuredContent"]["verified"] is True
    assert deleted["structuredContent"]["deleted"] is True
    assert deleted["structuredContent"]["verified"] is True
    assert source.calls[0].request.headers["host"] == "receipts.example"
    assert upload.calls[0].request.headers["Idempotency-Key"] == "receipt-upload"
    assert b'name="receipt"; filename="receipt.pdf"' in upload.calls[0].request.content
    assert b'name="base_version"' in upload.calls[0].request.content
    assert b'name="expected_has_receipt"' in upload.calls[0].request.content
    assert delete.calls[0].request.headers["Idempotency-Key"] == "receipt-delete"
    assert json.loads(delete.calls[0].request.content) == {
        "base_version": "t2",
        "expected_has_receipt": True,
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_receipt_size_and_scope_failures_are_structured(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read"])
    with respx.mock:
        respx.get("https://app.example.com/api/ledgers/11/transactions/31").mock(
            side_effect=[
                httpx.Response(200, json=_transaction(has_receipt=True, version="t1")),
                httpx.Response(200, json=_transaction(has_receipt=False, version="t1")),
            ]
        )
        respx.get("https://app.example.com/api/ledgers/11/transactions/31/receipt").mock(
            return_value=httpx.Response(
                200,
                headers={"Content-Type": "image/png", "Content-Length": str(PHOTO_MAX_BYTES + 1)},
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            too_large = await _call(
                client,
                "inspect_ledger_transaction_receipt",
                {"ledger_id": 11, "transaction_id": 31},
            )
            denied = await _call(
                client,
                "delete_ledger_transaction_receipt",
                {
                    "ledger_id": 11,
                    "transaction_id": 31,
                    "expected_has_receipt": True,
                    "base_version": "t1",
                    "idempotency_key": "denied",
                },
            )

    assert too_large["structuredContent"]["error"]["code"] == "receipt_too_large"
    assert denied["structuredContent"]["error"]["code"] == "scope_required"
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase5c_tools_are_discoverable(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ALLOWED_SCOPES)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
        ) as client,
    ):
        response = await client.post(
            "/mcp",
            headers={"Authorization": "Bearer access", "Accept": "application/json"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert len(names) == 172
    assert {
        "inspect_ledger_transaction_receipt",
        "upload_ledger_transaction_receipt_from_url",
        "delete_ledger_transaction_receipt",
    } <= names
    await engine.dispose()
