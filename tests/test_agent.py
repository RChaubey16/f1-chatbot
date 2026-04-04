"""Tests for the F1 RAG agent (unit + integration)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.retriever import RetrievedChunk, Retriever
from agent.router import Intent, Router


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
# Retriever unit tests (pure Python, no DB)
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
    assert result_ids[0] in ("b", "c")
    assert result_ids[1] in ("b", "c")
    assert len(result) == 4


def test_retriever_rrf_empty_dense():
    chunk_a = _make_chunk("a")
    result = Retriever._rrf([], [chunk_a], k=60)
    assert len(result) == 1
    assert result[0].chunk_id == "a"


def test_retriever_rrf_empty_sparse():
    chunk_a = _make_chunk("a")
    result = Retriever._rrf([chunk_a], [], k=60)
    assert len(result) == 1
    assert result[0].chunk_id == "a"


def test_retriever_rrf_both_empty():
    assert Retriever._rrf([], [], k=60) == []


# -----------------------------------------------------------------------
# Router unit tests — mock agent.llm.generate
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_classifies_historical():
    with patch("agent.router.gemini.generate", new_callable=AsyncMock, return_value="HISTORICAL"):
        intent = await Router().classify("Who won the 1988 championship?")
    assert intent == Intent.HISTORICAL


@pytest.mark.asyncio
async def test_router_classifies_current():
    with patch("agent.router.gemini.generate", new_callable=AsyncMock, return_value="CURRENT"):
        intent = await Router().classify("What is the latest standings?")
    assert intent == Intent.CURRENT


@pytest.mark.asyncio
async def test_router_defaults_to_mixed_on_unknown():
    with patch("agent.router.gemini.generate", new_callable=AsyncMock, return_value="BLAH"):
        intent = await Router().classify("Tell me everything about F1.")
    assert intent == Intent.MIXED


@pytest.mark.asyncio
async def test_router_defaults_to_mixed_on_api_error():
    with patch("agent.router.gemini.generate", new_callable=AsyncMock, side_effect=Exception("API error")):
        intent = await Router().classify("Who won the 1988 championship?")
    assert intent == Intent.MIXED


# -----------------------------------------------------------------------
# Agent unit tests — mock agent.llm.stream
# -----------------------------------------------------------------------

async def _mock_stream(*_args, **_kwargs):
    for token in ["Senna ", "won."]:
        yield token


@pytest.mark.asyncio
async def test_agent_historical_uses_static_partition():
    from agent.agent import Agent

    agent = Agent()
    agent._router.classify = AsyncMock(return_value=Intent.HISTORICAL)
    agent._retriever.retrieve = AsyncMock(return_value=[])
    agent._retriever.close = AsyncMock()

    with patch("agent.agent.gemini.stream", side_effect=_mock_stream):
        result = await agent.run_sync("Who won the 1988 championship?")

    agent._retriever.retrieve.assert_awaited_once()
    assert agent._retriever.retrieve.call_args.kwargs["partitions"] == ["static"]
    assert result["intent"] == "HISTORICAL"
    assert result["answer"] == "Senna won."
    await agent.close()


@pytest.mark.asyncio
async def test_agent_current_skips_retriever():
    from agent.agent import Agent

    agent = Agent()
    agent._router.classify = AsyncMock(return_value=Intent.CURRENT)
    agent._retriever.retrieve = AsyncMock(return_value=[])
    agent._retriever.close = AsyncMock()

    with patch("agent.agent.get_current_standings", new_callable=AsyncMock, return_value="1. Verstappen..."):
        with patch("agent.agent.gemini.stream", side_effect=_mock_stream):
            result = await agent.run_sync("What are the current standings?")

    agent._retriever.retrieve.assert_not_awaited()
    assert result["intent"] == "CURRENT"
    await agent.close()


@pytest.mark.asyncio
async def test_agent_mixed_uses_both_partitions():
    from agent.agent import Agent

    agent = Agent()
    agent._router.classify = AsyncMock(return_value=Intent.MIXED)
    agent._retriever.retrieve = AsyncMock(return_value=[])
    agent._retriever.close = AsyncMock()

    with patch("agent.agent.get_current_standings", new_callable=AsyncMock, return_value="standings text"):
        with patch("agent.agent.gemini.stream", side_effect=_mock_stream):
            result = await agent.run_sync("Compare Hamilton now vs 2008.")

    assert agent._retriever.retrieve.call_args.kwargs["partitions"] == ["static", "live"]
    assert result["intent"] == "MIXED"
    await agent.close()
