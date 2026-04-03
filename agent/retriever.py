"""Hybrid retriever: dense (pgvector) + sparse (full-text) with RRF merge."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ingestion.core.config import settings
from ingestion.core.logging import get_logger
from ingestion.embedders.ollama import OllamaEmbedder

log = get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    content: str
    source: str
    content_type: str
    partition: str
    metadata: dict
    score: float = 0.0


class Retriever:
    def __init__(self) -> None:
        self._engine = create_async_engine(settings.database_url, echo=False)
        self._embedder = OllamaEmbedder()

    async def retrieve(
        self,
        query: str,
        partitions: list[str] | None = None,
        top_k: int = 6,
    ) -> list[RetrievedChunk]:
        if partitions is None:
            partitions = ["static", "live"]
        query_embedding = await self._embedder._embed_one(query)
        dense = await self._dense_search(query_embedding, partitions, limit=20)
        sparse = await self._sparse_search(query, partitions, limit=20)
        merged = self._rrf(dense, sparse, k=60)
        return merged[:top_k]

    async def _dense_search(
        self,
        embedding: list[float],
        partitions: list[str],
        limit: int,
    ) -> list[RetrievedChunk]:
        emb_str = str(embedding)
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                text("""
                    SELECT chunk_id, content, source, content_type, partition, metadata,
                           1 - (embedding <=> :emb::vector) AS similarity
                    FROM chunks
                    WHERE partition = ANY(:parts)
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> :emb::vector
                    LIMIT :lim
                """),
                {"emb": emb_str, "parts": partitions, "lim": limit},
            )
            rows = result.fetchall()
        return [
            RetrievedChunk(
                chunk_id=r.chunk_id,
                content=r.content,
                source=r.source,
                content_type=r.content_type,
                partition=r.partition,
                metadata=r.metadata or {},
                score=float(r.similarity or 0.0),
            )
            for r in rows
        ]

    async def _sparse_search(
        self,
        query: str,
        partitions: list[str],
        limit: int,
    ) -> list[RetrievedChunk]:
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                text("""
                    SELECT chunk_id, content, source, content_type, partition, metadata,
                           ts_rank(content_tsv, plainto_tsquery('english', :q)) AS rank
                    FROM chunks
                    WHERE content_tsv @@ plainto_tsquery('english', :q)
                      AND partition = ANY(:parts)
                    ORDER BY rank DESC
                    LIMIT :lim
                """),
                {"q": query, "parts": partitions, "lim": limit},
            )
            rows = result.fetchall()
        return [
            RetrievedChunk(
                chunk_id=r.chunk_id,
                content=r.content,
                source=r.source,
                content_type=r.content_type,
                partition=r.partition,
                metadata=r.metadata or {},
                score=float(r.rank or 0.0),
            )
            for r in rows
        ]

    @staticmethod
    def _rrf(
        dense: list[RetrievedChunk],
        sparse: list[RetrievedChunk],
        k: int = 60,
    ) -> list[RetrievedChunk]:
        scores: dict[str, float] = defaultdict(float)
        chunks_by_id: dict[str, RetrievedChunk] = {}

        for rank, chunk in enumerate(dense):
            scores[chunk.chunk_id] += 1.0 / (k + rank + 1)
            chunks_by_id[chunk.chunk_id] = chunk

        for rank, chunk in enumerate(sparse):
            scores[chunk.chunk_id] += 1.0 / (k + rank + 1)
            chunks_by_id[chunk.chunk_id] = chunk

        sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        return [
            RetrievedChunk(
                chunk_id=cid,
                content=chunks_by_id[cid].content,
                source=chunks_by_id[cid].source,
                content_type=chunks_by_id[cid].content_type,
                partition=chunks_by_id[cid].partition,
                metadata=chunks_by_id[cid].metadata,
                score=scores[cid],
            )
            for cid in sorted_ids
        ]

    async def close(self) -> None:
        await self._engine.dispose()
        await self._embedder.close()
