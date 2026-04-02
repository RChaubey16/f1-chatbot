"""Tests for the APScheduler-based live KB scheduler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingestion.scheduler import create_scheduler


# -----------------------------------------------------------------------
# Scheduler registration tests
# -----------------------------------------------------------------------

def test_scheduler_registers_both_jobs():
    scheduler = create_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "openf1_refresh" in job_ids
    assert "news_scrape" in job_ids


def test_scheduler_jobs_have_max_instances_one():
    scheduler = create_scheduler()
    for job in scheduler.get_jobs():
        assert job.max_instances == 1, f"Job {job.id} should have max_instances=1"


def test_scheduler_jobs_have_coalesce():
    scheduler = create_scheduler()
    for job in scheduler.get_jobs():
        assert job.coalesce is True, f"Job {job.id} should have coalesce=True"


def test_scheduler_interval_matches_config():
    from ingestion.core.config import settings
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = create_scheduler()
    jobs = {job.id: job for job in scheduler.get_jobs()}

    openf1_job = jobs["openf1_refresh"]
    assert isinstance(openf1_job.trigger, IntervalTrigger)
    # interval is stored as a timedelta
    assert openf1_job.trigger.interval.seconds == settings.live_refresh_interval_hours * 3600

    news_job = jobs["news_scrape"]
    assert isinstance(news_job.trigger, IntervalTrigger)
    assert news_job.trigger.interval.seconds == settings.news_refresh_interval_hours * 3600


# -----------------------------------------------------------------------
# Job execution tests (with mocked pipeline components)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_openf1_refresh_writes_job_run():
    """run_openf1_refresh should write a job_runs row on completion."""
    with (
        patch("ingestion.scheduler._log_job_start", new_callable=AsyncMock, return_value=1) as mock_start,
        patch("ingestion.scheduler._log_job_finish", new_callable=AsyncMock) as mock_finish,
        patch("ingestion.scheduler._get_last_synced", new_callable=AsyncMock, return_value=None),
        patch("ingestion.scheduler._set_last_synced", new_callable=AsyncMock),
        patch("ingestion.scheduler.OpenF1Extractor") as MockExtractor,
        patch("ingestion.scheduler.OllamaEmbedder") as MockEmbedder,
        patch("ingestion.scheduler.PgVectorLoader") as MockLoader,
    ):
        # Extractor yields nothing — extract() is an async generator, not a coroutine,
        # so use MagicMock (not AsyncMock) to return the async iterable directly.
        mock_extractor = MagicMock()
        mock_extractor.extract = MagicMock(side_effect=_async_empty)
        MockExtractor.return_value = mock_extractor

        mock_embedder = MagicMock()
        mock_embedder.close = AsyncMock()
        MockEmbedder.return_value = mock_embedder

        mock_loader = MagicMock()
        mock_loader.doc_exists = AsyncMock(return_value=False)
        mock_loader.close = AsyncMock()
        MockLoader.return_value = mock_loader

        from ingestion.scheduler import run_openf1_refresh
        await run_openf1_refresh()

        mock_start.assert_called_once_with("openf1_refresh")
        mock_finish.assert_called_once()
        # success=True because no exception
        _, result_arg, success_arg = mock_finish.call_args.args
        assert success_arg is True


@pytest.mark.asyncio
async def test_run_news_scrape_writes_job_run():
    """run_news_scrape should write a job_runs row on completion."""
    with (
        patch("ingestion.scheduler._log_job_start", new_callable=AsyncMock, return_value=2) as mock_start,
        patch("ingestion.scheduler._log_job_finish", new_callable=AsyncMock) as mock_finish,
        patch("ingestion.scheduler._get_last_synced", new_callable=AsyncMock, return_value=None),
        patch("ingestion.scheduler._set_last_synced", new_callable=AsyncMock),
        patch("ingestion.scheduler.NewsExtractor") as MockExtractor,
        patch("ingestion.scheduler.OllamaEmbedder") as MockEmbedder,
        patch("ingestion.scheduler.PgVectorLoader") as MockLoader,
    ):
        mock_extractor = MagicMock()
        mock_extractor.extract = MagicMock(side_effect=_async_empty)
        MockExtractor.return_value = mock_extractor

        mock_embedder = MagicMock()
        mock_embedder.close = AsyncMock()
        MockEmbedder.return_value = mock_embedder

        mock_loader = MagicMock()
        mock_loader.url_exists = AsyncMock(return_value=False)
        mock_loader.doc_exists = AsyncMock(return_value=False)
        mock_loader.close = AsyncMock()
        MockLoader.return_value = mock_loader

        from ingestion.scheduler import run_news_scrape
        await run_news_scrape()

        mock_start.assert_called_once_with("news_scrape")
        mock_finish.assert_called_once()
        _, result_arg, success_arg = mock_finish.call_args.args
        assert success_arg is True


@pytest.mark.asyncio
async def test_run_openf1_refresh_records_failure():
    """run_openf1_refresh should log success=False when an exception occurs."""
    with (
        patch("ingestion.scheduler._log_job_start", new_callable=AsyncMock, return_value=3),
        patch("ingestion.scheduler._log_job_finish", new_callable=AsyncMock) as mock_finish,
        patch("ingestion.scheduler._get_last_synced", new_callable=AsyncMock, side_effect=RuntimeError("DB down")),
        patch("ingestion.scheduler._set_last_synced", new_callable=AsyncMock),
        patch("ingestion.scheduler.OllamaEmbedder"),
        patch("ingestion.scheduler.PgVectorLoader"),
    ):
        from ingestion.scheduler import run_openf1_refresh
        await run_openf1_refresh()

        mock_finish.assert_called_once()
        _, result_arg, success_arg = mock_finish.call_args.args
        assert success_arg is False
        assert len(result_arg.errors) > 0


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

async def _async_empty():
    """Async generator that yields nothing."""
    return
    yield  # noqa: unreachable — makes this an async generator
