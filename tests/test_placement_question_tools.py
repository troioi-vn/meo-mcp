import base64
import json
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import respx

from meo_mcp.config import Settings
from meo_mcp.database import AccessTokenRecord, Base, Grant, make_session_factory
from meo_mcp.main import create_app
from meo_mcp.security import TokenCipher, digest, now

BASE = "https://app.example.com/api"


async def _app_with_token(tmp_path, scopes: list[str]):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'questions.db'}"
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


def _question(status: str = "pending", **extra) -> dict:
    return {
        "id": 5,
        "pet_id": 4,
        "placement_request_id": 7,
        "asker_name": "Nga",
        "question": "Is she good with dogs?",
        "question_locale": "en",
        "answer": None,
        "answer_locale": None,
        "answered_by_name": None,
        "answered_at": None,
        "published_at": None,
        "created_at": "2026-09-02T10:00:00Z",
        "is_answered": False,
        "status": status,
        **extra,
    }


async def _client(app, settings):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
    )


@pytest.mark.asyncio
async def test_asking_sends_no_altcha_and_no_idempotency_key(tmp_path) -> None:
    """Meo's proof-of-work guard applies to anonymous askers only, and the
    route carries no idempotency middleware, so claiming replay protection by
    sending a key would be a lie about what Meo does."""
    app, engine, settings = await _app_with_token(tmp_path, ["placement:read", "placement:write"])
    with respx.mock:
        asked = respx.post(f"{BASE}/placement-requests/7/questions").mock(
            return_value=httpx.Response(201, json={"data": _question()})
        )
        async with app.router.lifespan_context(app), await _client(app, settings) as client:
            result = await _call(
                client,
                "ask_placement_question",
                {
                    "placement_request_id": 7,
                    "asker_name": "Nga",
                    "question": "Is she good with dogs?",
                },
            )

    assert result["isError"] is False, result
    request = asked.calls[0].request
    assert "altcha" not in json.loads(request.content)
    assert "Idempotency-Key" not in request.headers
    assert result["structuredContent"]["question"]["status"] == "pending"
    await engine.dispose()


@pytest.mark.asyncio
async def test_answering_publishes_and_is_verified(tmp_path) -> None:
    """Answering is what publishes a question; there is no separate step, so a
    reply that leaves it unpublished is a failed write, not a success."""
    app, engine, settings = await _app_with_token(tmp_path, ["placement:read", "placement:write"])
    with respx.mock:
        answered = respx.post(f"{BASE}/placement-questions/5/answer").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": _question(
                        "published",
                        answer="She is.",
                        is_answered=True,
                        published_at="2026-09-03T09:00:00Z",
                    )
                },
            )
        )
        async with app.router.lifespan_context(app), await _client(app, settings) as client:
            result = await _call(
                client,
                "answer_placement_question",
                {"question_id": 5, "answer": "She is.", "idempotency_key": str(uuid4())},
            )

    assert result["isError"] is False, result
    assert json.loads(answered.calls[0].request.content)["answer"] == "She is."
    assert answered.calls[0].request.headers["Idempotency-Key"]
    assert result["structuredContent"]["question"]["status"] == "published"
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_write_that_does_not_reach_the_expected_state_is_reported(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["placement:read", "placement:write"])
    with respx.mock:
        respx.post(f"{BASE}/placement-questions/5/hide").mock(
            return_value=httpx.Response(200, json={"data": _question("published")})
        )
        async with app.router.lifespan_context(app), await _client(app, settings) as client:
            result = await _call(
                client,
                "hide_placement_question",
                {"question_id": 5, "idempotency_key": str(uuid4())},
            )

    assert result["isError"] is True
    assert json.loads(result["content"][0]["text"])["code"] == "post_write_verification_failed"
    await engine.dispose()


@pytest.mark.asyncio
async def test_listing_keeps_moderator_and_translation_fields_only_when_sent(tmp_path) -> None:
    """Meo sends `hidden_at` only to a moderator and translations only when it
    has them, so their absence carries information and is not defaulted in."""
    app, engine, settings = await _app_with_token(tmp_path, ["placement:read"])
    with respx.mock:
        respx.get(f"{BASE}/placement-requests/7/questions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        _question("published", hidden_at=None, question_translation="Xin chao?"),
                        _question("pending"),
                    ]
                },
            )
        )
        async with app.router.lifespan_context(app), await _client(app, settings) as client:
            result = await _call(client, "list_placement_questions", {"placement_request_id": 7})

    questions = result["structuredContent"]["questions"]
    assert questions[0]["question_translation"] == "Xin chao?"
    assert "hidden_at" in questions[0]
    assert "hidden_at" not in questions[1]
    assert "question_translation" not in questions[1]
    await engine.dispose()
