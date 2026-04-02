"""APScheduler-based background scheduler for live KB refresh.

Two recurring jobs:
  - openf1_refresh  — every LIVE_REFRESH_INTERVAL_HOURS (default 6h)
  - news_scrape     — every NEWS_REFRESH_INTERVAL_HOURS  (default 3h)

Each job writes a row to the job_runs table on completion.

Standalone entrypoint:
    uv run python -m ingestion.scheduler
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ingestion.core.config import settings
from ingestion.core.logging import get_logger, setup_logging
from ingestion.core.models import IngestionResult
from ingestion.embedders.ollama import OllamaEmbedder
from ingestion.extractors.news import NewsExtractor
from ingestion.extractors.openf1 import OpenF1Extractor
from ingestion.loaders.pgvector import PgVectorLoader
from ingestion.transformers.chunker import Chunker

log = get_logger(__name__)

# Shared engine for job_runs logging (created once at module level when scheduler starts)
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, echo=False)
    return _engine


# ------------------------------------------------------------------
# Sync-state helpers
# ------------------------------------------------------------------

async def _get_last_synced(source: str) -> datetime | None:
    """Return last_synced_at for a given source, or None if never synced."""
    async with AsyncSession(_get_engine()) as session:
        result = await session.execute(
            text("SELECT last_synced_at FROM sync_state WHERE source = :src"),
            {"src": source},
        )
        row = result.fetchone()
        return row[0] if row else None


async def _set_last_synced(source: str, ts: datetime) -> None:
    async with AsyncSession(_get_engine()) as session:
        async with session.begin():
            await session.execute(
                text("""
                    INSERT INTO sync_state (source, last_synced_at)
                    VALUES (:src, :ts)
                    ON CONFLICT (source) DO UPDATE
                      SET last_synced_at = EXCLUDED.last_synced_at
                """),
                {"src": source, "ts": ts},
            )


# ------------------------------------------------------------------
# Job-run logging
# ------------------------------------------------------------------

async def _log_job_start(job_id: str) -> int:
    """Insert a job_runs row and return its id."""
    async with AsyncSession(_get_engine()) as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    INSERT INTO job_runs (job_id, started_at)
                    VALUES (:job_id, NOW())
                    RETURNING id
                """),
                {"job_id": job_id},
            )
            return result.scalar()


async def _log_job_finish(
    run_id: int,
    result: IngestionResult,
    success: bool,
) -> None:
    async with AsyncSession(_get_engine()) as session:
        async with session.begin():
            await session.execute(
                text("""
                    UPDATE job_runs
                       SET finished_at   = NOW(),
                           docs_upserted = :docs,
                           errors        = :errors,
                           success       = :success
                     WHERE id = :run_id
                """),
                {
                    "run_id": run_id,
                    "docs": result.docs_fetched,
                    "errors": json.dumps(result.errors),
                    "success": success,
                },
            )


# ------------------------------------------------------------------
# Job: OpenF1 refresh
# ------------------------------------------------------------------

async def run_openf1_refresh() -> None:
    log.info("scheduler.openf1.start")
    run_id = await _log_job_start("openf1_refresh")
    result = IngestionResult()
    success = False

    try:
        since = await _get_last_synced("openf1")
        started_at = datetime.now(tz=timezone.utc)

        chunker = Chunker()
        embedder = OllamaEmbedder()
        loader = PgVectorLoader()

        extractor = OpenF1Extractor(since=since)

        try:
            async for raw_doc in extractor.extract():
                if await loader.doc_exists(raw_doc.fingerprint):
                    result.docs_skipped_duplicate += 1
                    continue

                chunks = chunker.chunk(raw_doc)
                result.chunks_created += len(chunks)

                chunks = await embedder.embed_batch(chunks)
                result.chunks_embedded += sum(1 for c in chunks if c.embedding)

                r = await loader.upsert(raw_doc, chunks)
                result.docs_fetched += r.docs_fetched
                result.chunks_upserted += r.chunks_upserted
                result.errors.extend(r.errors)

        finally:
            await embedder.close()
            await loader.close()

        await _set_last_synced("openf1", started_at)
        success = True
        log.info("scheduler.openf1.done", summary=result.summarise())

    except Exception as exc:
        result.errors.append(str(exc))
        log.error("scheduler.openf1.fail", error=str(exc))
    finally:
        await _log_job_finish(run_id, result, success)


# ------------------------------------------------------------------
# Job: News scrape
# ------------------------------------------------------------------

async def run_news_scrape() -> None:
    log.info("scheduler.news.start")
    run_id = await _log_job_start("news_scrape")
    result = IngestionResult()
    success = False

    try:
        since = await _get_last_synced("news")
        started_at = datetime.now(tz=timezone.utc)

        chunker = Chunker()
        embedder = OllamaEmbedder()
        loader = PgVectorLoader()

        extractor = NewsExtractor(
            since=since,
            url_exists_fn=loader.url_exists,
        )

        try:
            async for raw_doc in extractor.extract():
                if await loader.doc_exists(raw_doc.fingerprint):
                    result.docs_skipped_duplicate += 1
                    continue

                chunks = chunker.chunk(raw_doc)
                result.chunks_created += len(chunks)

                chunks = await embedder.embed_batch(chunks)
                result.chunks_embedded += sum(1 for c in chunks if c.embedding)

                r = await loader.upsert(raw_doc, chunks)
                result.docs_fetched += r.docs_fetched
                result.chunks_upserted += r.chunks_upserted
                result.errors.extend(r.errors)

        finally:
            await embedder.close()
            await loader.close()

        await _set_last_synced("news", started_at)
        success = True
        log.info("scheduler.news.done", summary=result.summarise())

    except Exception as exc:
        result.errors.append(str(exc))
        log.error("scheduler.news.fail", error=str(exc))
    finally:
        await _log_job_finish(run_id, result, success)


# ------------------------------------------------------------------
# Scheduler setup
# ------------------------------------------------------------------

def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        run_openf1_refresh,
        trigger="interval",
        hours=settings.live_refresh_interval_hours,
        id="openf1_refresh",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        run_news_scrape,
        trigger="interval",
        hours=settings.news_refresh_interval_hours,
        id="news_scrape",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    return scheduler


# ------------------------------------------------------------------
# Standalone entrypoint
# ------------------------------------------------------------------

async def _run_scheduler() -> None:
    setup_logging()
    log.info("scheduler.starting")

    scheduler = create_scheduler()
    scheduler.start()

    log.info(
        "scheduler.running",
        openf1_interval_hours=settings.live_refresh_interval_hours,
        news_interval_hours=settings.news_refresh_interval_hours,
    )

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler.stopping")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(_run_scheduler())
