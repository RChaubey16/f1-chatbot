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
