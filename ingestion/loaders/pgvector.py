"""PostgreSQL + pgvector loader with deduplication."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ingestion.core.config import settings
from ingestion.core.logging import get_logger
from ingestion.core.models import Chunk, IngestionResult, RawDocument

log = get_logger(__name__)


class PgVectorLoader:
    def __init__(self) -> None:
        self._engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )

    async def doc_exists(self, fingerprint: str) -> bool:
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                text("SELECT 1 FROM documents WHERE fingerprint = :fp"),
                {"fp": fingerprint},
            )
            return result.scalar() is not None

    async def upsert(
        self, doc: RawDocument, chunks: list[Chunk]
    ) -> IngestionResult:
        result = IngestionResult(docs_fetched=1)

        fp = doc.fingerprint
        if await self.doc_exists(fp):
            result.docs_skipped_duplicate = 1
            result.docs_fetched = 0
            return result

        async with AsyncSession(self._engine) as session:
            async with session.begin():
                # Insert document
                await session.execute(
                    text("""
                        INSERT INTO documents (fingerprint, source, content_type, partition, metadata)
                        VALUES (:fp, :src, :ct, :part, :meta)
                        ON CONFLICT (fingerprint) DO NOTHING
                    """),
                    {
                        "fp": fp,
                        "src": doc.source.value,
                        "ct": doc.content_type.value,
                        "part": doc.partition.value,
                        "meta": json.dumps(doc.metadata),
                    },
                )

                # Upsert chunks
                for chunk in chunks:
                    emb_str = (
                        str(chunk.embedding) if chunk.embedding else None
                    )
                    await session.execute(
                        text("""
                            INSERT INTO chunks
                                (chunk_id, doc_fingerprint, content, source,
                                 content_type, partition, metadata, embedding)
                            VALUES
                                (:cid, :dfp, :content, :src,
                                 :ct, :part, :meta, :emb)
                            ON CONFLICT (chunk_id) DO UPDATE
                              SET embedding = EXCLUDED.embedding,
                                  metadata  = EXCLUDED.metadata
                        """),
                        {
                            "cid": chunk.chunk_id,
                            "dfp": chunk.doc_fingerprint,
                            "content": chunk.content,
                            "src": chunk.source.value,
                            "ct": chunk.content_type.value,
                            "part": chunk.partition.value,
                            "meta": json.dumps(chunk.metadata),
                            "emb": emb_str,
                        },
                    )
                    result.chunks_upserted += 1

        result.chunks_created = len(chunks)
        result.chunks_embedded = sum(1 for c in chunks if c.embedding)
        return result

    async def rebuild_index(self) -> None:
        log.info("pgvector.rebuild_index")
        async with AsyncSession(self._engine) as session:
            async with session.begin():
                await session.execute(
                    text("DROP INDEX IF EXISTS chunks_embedding_idx")
                )
                await session.execute(
                    text("""
                        CREATE INDEX chunks_embedding_idx
                          ON chunks USING ivfflat (embedding vector_cosine_ops)
                          WITH (lists = 100)
                    """)
                )
        log.info("pgvector.rebuild_index.done")

    async def get_chunk_count(self) -> int:
        async with AsyncSession(self._engine) as session:
            result = await session.execute(text("SELECT COUNT(*) FROM chunks"))
            return result.scalar() or 0

    async def close(self) -> None:
        await self._engine.dispose()
