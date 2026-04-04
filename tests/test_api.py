"""Tests for FastAPI routes: POST /chat, GET /chat/stream, GET /health."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_mock(intent: str = "HISTORICAL", answer: str = "Senna won.") -> MagicMock:
    """Return a mock Agent whose run_sync returns a canned response."""
    agent = MagicMock()
    agent.run_sync = AsyncMock(
        return_value={
            "answer": answer,
            "sources": [
                {"content_type": "race_result", "source": "jolpica", "metadata": {"season": 1988}}
            ],
            "intent": intent,
            "latency_ms": 42.0,
        }
    )

    async def _run_gen(query: str):
        for token in ["Sen", "na ", "won."]:
            yield token

    agent.run = _run_gen
    agent.close = AsyncMock()
    return agent


# ---------------------------------------------------------------------------
# Fixture: app with mocked lifespan
# ---------------------------------------------------------------------------

@pytest.fixture()
async def test_client():
    """AsyncClient wired to the FastAPI app with a pre-seeded mock agent.

    ASGITransport does not run the lifespan, so we set app.state.agent directly.
    """
    from api.main import app

    mock_agent = _make_agent_mock()
    app.state.agent = mock_agent

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, mock_agent


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_returns_answer(test_client):
    client, _ = test_client
    response = await client.post("/chat", json={"query": "Who won the 1988 championship?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Senna won."
    assert body["intent"] == "HISTORICAL"
    assert isinstance(body["latency_ms"], float)
    assert len(body["sources"]) == 1


@pytest.mark.asyncio
async def test_chat_passes_max_chunks(test_client):
    client, agent = test_client
    await client.post("/chat", json={"query": "Champions?", "max_chunks": 3})
    agent.run_sync.assert_awaited_once_with("Champions?", max_chunks=3)


@pytest.mark.asyncio
async def test_chat_default_max_chunks(test_client):
    client, agent = test_client
    await client.post("/chat", json={"query": "Champions?"})
    agent.run_sync.assert_awaited_once_with("Champions?", max_chunks=6)


@pytest.mark.asyncio
async def test_chat_missing_query_returns_422(test_client):
    client, _ = test_client
    response = await client.post("/chat", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /chat/stream
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_stream_returns_sse(test_client):
    client, _ = test_client
    response = await client.get("/chat/stream", params={"query": "Who won 1988?"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    body = response.text
    # Each yielded token is a "data:" SSE line
    assert "data:" in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_chat_stream_missing_query_returns_422(test_client):
    client, _ = test_client
    response = await client.get("/chat/stream")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_ok(test_client):
    client, _ = test_client

    mock_conn_result = MagicMock()
    mock_conn_result.scalar.return_value = 100

    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: None

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=mock_conn_result)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_engine.dispose = AsyncMock()

    mock_embedder = AsyncMock()
    mock_embedder.health_check = AsyncMock(return_value=True)
    mock_embedder.close = AsyncMock()

    with (
        patch("api.routes.health.create_async_engine", return_value=mock_engine),
        patch("api.routes.health.OllamaEmbedder", return_value=mock_embedder),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["postgres"] == "ok"
    assert body["ollama"] == "ok"
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_health_postgres_error(test_client):
    client, _ = test_client

    mock_engine = MagicMock()
    mock_engine.connect.side_effect = Exception("DB down")
    mock_engine.dispose = AsyncMock()

    mock_embedder = AsyncMock()
    mock_embedder.health_check = AsyncMock(return_value=True)
    mock_embedder.close = AsyncMock()

    with (
        patch("api.routes.health.create_async_engine", return_value=mock_engine),
        patch("api.routes.health.OllamaEmbedder", return_value=mock_embedder),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["postgres"] == "error"
    assert body["status"] == "error"
