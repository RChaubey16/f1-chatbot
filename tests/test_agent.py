"""Tests for the F1 RAG agent (unit + integration)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from agent.retriever import RetrievedChunk, Retriever
from agent.router import Intent, Router
from ingestion.core.config import settings


# -----------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------

def _make_chunk(chunk_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=f"Content for chunk {chunk_id}.",
        source="jolpica",
        content_type="race_result",
        partition="static",
        metadata={"season": 1988},
        score=0.9,
    )


# -----------------------------------------------------------------------
# Retriever unit test (pure Python, no DB)
# -----------------------------------------------------------------------

def test_retriever_rrf_merge():
    chunk_a = _make_chunk("a")
    chunk_b = _make_chunk("b")
    chunk_c = _make_chunk("c")
    chunk_d = _make_chunk("d")

    dense = [chunk_a, chunk_b, chunk_c]
    sparse = [chunk_b, chunk_c, chunk_d]

    result = Retriever._rrf(dense, sparse, k=60)

    result_ids = [c.chunk_id for c in result]
    # b and c appear in both lists → highest RRF scores
    assert result_ids[0] in ("b", "c")
    assert result_ids[1] in ("b", "c")
    assert len(result) == 4


# -----------------------------------------------------------------------
# Router unit tests (no real Ollama required)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_classifies_historical():
    """Mock Ollama returning HISTORICAL — router should return Intent.HISTORICAL."""
    router = Router()
    with respx.mock:
        respx.post(f"{settings.ollama_base_url}/api/generate").mock(
            return_value=httpx.Response(200, json={"response": "HISTORICAL"})
        )
        intent = await router.classify("Who won the 1988 championship?")
    await router.close()
    assert intent == Intent.HISTORICAL


@pytest.mark.asyncio
async def test_router_classifies_current():
    """Mock Ollama returning CURRENT — router should return Intent.CURRENT."""
    router = Router()
    with respx.mock:
        respx.post(f"{settings.ollama_base_url}/api/generate").mock(
            return_value=httpx.Response(200, json={"response": "CURRENT"})
        )
        intent = await router.classify("What is the latest standings?")
    await router.close()
    assert intent == Intent.CURRENT


@pytest.mark.asyncio
async def test_router_defaults_to_mixed_on_unknown():
    """Mock Ollama returning an unknown label — router should default to Intent.MIXED."""
    router = Router()
    with respx.mock:
        respx.post(f"{settings.ollama_base_url}/api/generate").mock(
            return_value=httpx.Response(200, json={"response": "BLAH"})
        )
        intent = await router.classify("Tell me everything about F1.")
    await router.close()
    assert intent == Intent.MIXED


# -----------------------------------------------------------------------
# Agent unit tests
# -----------------------------------------------------------------------

def _make_mock_stream():
    """Return a context-manager mock that mimics httpx streaming."""
    from unittest.mock import MagicMock

    async def _aiter_lines():
        yield '{"response": "test", "done": false}'
        yield '{"done": true}'

    mock_response = MagicMock()
    mock_response.aiter_lines = _aiter_lines
    mock_response.raise_for_status = MagicMock()

    mock_stream_cm = AsyncMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_stream_cm)

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=None)

    return mock_client_cm


@pytest.mark.asyncio
async def test_agent_historical_uses_static_partition():
    """HISTORICAL intent → retriever called with partitions=['static'] only."""
    from agent.agent import Agent

    agent = Agent()

    agent._router.classify = AsyncMock(return_value=Intent.HISTORICAL)
    agent._retriever.retrieve = AsyncMock(return_value=[])
    agent._router.close = AsyncMock()
    agent._retriever.close = AsyncMock()

    with patch("agent.agent.httpx.AsyncClient", return_value=_make_mock_stream()):
        result = await agent.run_sync("Who won the 1988 championship?")

    agent._retriever.retrieve.assert_awaited_once()
    call_kwargs = agent._retriever.retrieve.call_args
    assert call_kwargs.kwargs["partitions"] == ["static"]

    assert result["intent"] == "HISTORICAL"
    await agent.close()


@pytest.mark.asyncio
async def test_agent_current_skips_retriever():
    """CURRENT intent → retriever NOT called, get_current_standings IS called."""
    from agent.agent import Agent

    agent = Agent()

    agent._router.classify = AsyncMock(return_value=Intent.CURRENT)
    agent._retriever.retrieve = AsyncMock(return_value=[])
    agent._router.close = AsyncMock()
    agent._retriever.close = AsyncMock()

    with patch("agent.agent.get_current_standings", new_callable=AsyncMock, return_value="1. Verstappen...") as mock_standings:
        with patch("agent.agent.httpx.AsyncClient", return_value=_make_mock_stream()):
            result = await agent.run_sync("What are the current standings?")

    mock_standings.assert_awaited_once()
    agent._retriever.retrieve.assert_not_awaited()
    assert result["intent"] == "CURRENT"
    await agent.close()


@pytest.mark.asyncio
async def test_agent_mixed_uses_both_partitions():
    """MIXED intent → retriever called with partitions=['static', 'live']."""
    from agent.agent import Agent

    agent = Agent()

    agent._router.classify = AsyncMock(return_value=Intent.MIXED)
    agent._retriever.retrieve = AsyncMock(return_value=[])
    agent._router.close = AsyncMock()
    agent._retriever.close = AsyncMock()

    with patch("agent.agent.get_current_standings", new_callable=AsyncMock, return_value="standings text"):
        with patch("agent.agent.httpx.AsyncClient", return_value=_make_mock_stream()):
            result = await agent.run_sync("Compare Hamilton now vs 2008.")

    agent._retriever.retrieve.assert_awaited_once()
    call_kwargs = agent._retriever.retrieve.call_args
    assert call_kwargs.kwargs["partitions"] == ["static", "live"]

    assert result["intent"] == "MIXED"
    await agent.close()
