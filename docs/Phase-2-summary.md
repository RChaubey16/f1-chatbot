# Phase 2 Summary — Live KB Ingestion (OpenF1 + News Scraper + Scheduler)

## Overview

Phase 2 extends the knowledge base with a **live partition** that stays fresh
throughout the racing season. Two new extractors pull current-season data from
the OpenF1 API and Motorsport.com. An APScheduler-backed scheduler runs both
jobs on configurable intervals, with incremental sync and full audit logging.
Phase 1 components (chunker, embedder, loader) are reused without modification.

---

## Architecture

```
                         ┌──────────────────┐
                         │   CLI Entry Point │
                         │  ingestion/       │
                         │  pipeline.py      │
                         └────────┬─────────┘
                                  │ --phase live [--since YYYY-MM-DD]
              ┌───────────────────┼───────────────────┐
              │                                        │
    ┌─────────▼──────────┐              ┌─────────────▼──────────┐
    │  OpenF1Extractor   │              │   NewsExtractor         │
    │  (live sessions,   │              │   (Motorsport.com       │
    │   stints, pit data)│              │    F1 news scraper)     │
    └─────────┬──────────┘              └─────────────┬──────────┘
              │                                        │
              └─────────────────┬──────────────────────┘
                                │ RawDocument stream (KBPartition.LIVE)
                                ▼
                      ┌─────────────────────┐
                      │  Chunker            │
                      │  (narrative split)  │
                      └─────────┬───────────┘
                                │ list[Chunk]
                                ▼
                      ┌─────────────────────┐
                      │  OllamaEmbedder     │
                      │  (nomic-embed-text) │
                      └─────────┬───────────┘
                                │ list[Chunk] with embeddings
                                ▼
                      ┌─────────────────────┐
                      │  PgVectorLoader     │
                      │  (dedup + upsert)   │
                      └─────────────────────┘
                                │
                                ▼
                      ┌──────────────────────┐
                      │  PostgreSQL + pgvector│
                      │  partition = 'live'   │
                      └──────────────────────┘

                    ┌───────────────────────────┐
                    │  APScheduler              │
                    │  ┌──────────────────────┐ │
                    │  │ openf1_refresh (6h)  │ │
                    │  │ news_scrape    (3h)  │ │
                    │  └──────────────────────┘ │
                    │  sync_state  (incremental) │
                    │  job_runs    (audit log)   │
                    └───────────────────────────┘
```

---

## Files Created

### Extractors — `ingestion/extractors/`

| File | Lines | Purpose |
|------|------:|---------|
| `openf1.py` | ~230 | Fetches live session data from OpenF1 API |
| `news.py` | ~220 | Scrapes F1 news articles from Motorsport.com |

#### `ingestion/extractors/openf1.py`

`OpenF1Extractor` fetches live F1 data from `https://api.openf1.org/v1` — a
free, open REST API requiring no authentication.

**Endpoints consumed:**

| Endpoint | ContentType | Notes |
|----------|-------------|-------|
| `/sessions` | `race_result` | FP1–3, Qualifying, Sprint, Race sessions |
| `/drivers` | `driver_profile` | Current-season driver roster |
| `/position` | `race_result` | Final position classification per session |
| `/stints` | `race_result` | Tyre compound and lap ranges per driver |
| `/pit` | `race_result` | Pit stop lap number and duration |

**Incremental sync strategy:**
- **First run** (`since=None`): fetches all sessions from `{season}-01-01`
- **Subsequent runs**: pass `since` timestamp to fetch only newer sessions
- The `sync_state` table stores `last_synced_at` per source; the scheduler
  reads this before each run and updates it on success

**Document structure:**
- Each session yields one `RawDocument` for the session header, one each for
  position data, stints, and pit stops (only if non-empty)
- All documents use `partition=KBPartition.LIVE` and `source=SourceType.OPENF1`
- A human-readable `narrative` field is stored in `metadata` for each document,
  ready for the chunker without further transformation

**Error handling:**
- Per-endpoint try/except — a failure on `/stints` does not abort `/pit` for
  the same session
- `tenacity` retry (3 attempts, exponential backoff) on all HTTP calls
- Returns an empty stream (not an exception) if the sessions endpoint fails

**Constructor params:**
- `season: int` — defaults to current year
- `since: datetime | None` — optional lower bound for incremental sync

#### `ingestion/extractors/news.py`

`NewsExtractor` scrapes F1 news articles from `https://www.motorsport.com/f1/news/`.

**Scraping strategy:**
```
1. Fetch the F1 news index page
2. Extract article URLs — tries article card selectors, falls back to any
   <a href> containing /f1/news/
3. For each URL: fetch full article page
4. Extract: headline, published date, author, body text, keywords
5. Strip boilerplate (nav, ads, related articles, promo blocks)
6. Yield one RawDocument per article
```

**URL-based deduplication:**
- Before fetching an article, calls the injected `url_exists_fn(url)` to check
  if that URL already exists in `documents.metadata->>'url'`
- The `PgVectorLoader.url_exists()` method performs this check
- The `url_exists_fn` is injected at construction time so the extractor
  remains testable without a real database

**Graceful degradation:**
- If the index page returns no recognisable article links, logs a warning and
  yields 0 documents — the scheduler job does not crash
- If an individual article fails to fetch or parse, it is logged and skipped
- Rate limiting: 2 seconds between article fetches (configurable via `NEWS_DELAY`)

**Metadata captured per article:**
```python
{
    "headline": "Verstappen wins 2024 Bahrain GP",
    "url": "https://www.motorsport.com/f1/news/...",
    "published_at": "2024-03-02T15:00:00+00:00",
    "author": "Jane Doe",
    "tags": ["f1", "verstappen", "bahrain"],
}
```

**Constructor params:**
- `max_articles: int` — cap per run (default 50)
- `since: datetime | None` — skip articles older than this timestamp
- `url_exists_fn: callable | None` — async `(url: str) -> bool` for URL dedup

---

### Scheduler — `ingestion/scheduler.py`

| File | Lines | Purpose |
|------|------:|---------|
| `scheduler.py` | ~240 | APScheduler with two jobs, sync_state, job_runs logging |

`create_scheduler()` returns an `AsyncIOScheduler` with two pre-configured jobs:

| Job ID | Function | Interval | Prevents overlap |
|--------|----------|----------|-----------------|
| `openf1_refresh` | `run_openf1_refresh()` | `LIVE_REFRESH_INTERVAL_HOURS` (default 6h) | `max_instances=1`, `coalesce=True` |
| `news_scrape` | `run_news_scrape()` | `NEWS_REFRESH_INTERVAL_HOURS` (default 3h) | `max_instances=1`, `coalesce=True` |

**`coalesce=True`** — if a job is still running when the next trigger fires,
the missed trigger is discarded rather than queued. **`max_instances=1`**
prevents concurrent execution of the same job.

**Each job function:**
1. Logs a `job_runs` row via `_log_job_start(job_id) -> run_id`
2. Reads `last_synced_at` from `sync_state` via `_get_last_synced(source)`
3. Records `started_at` timestamp
4. Runs the full extract → chunk → embed → load pipeline
5. Updates `sync_state` with the new timestamp via `_set_last_synced(source, ts)`
6. Updates the `job_runs` row with `finished_at`, `docs_upserted`, `errors`,
   and `success=True/False` via `_log_job_finish(run_id, result, success)`
7. On any unhandled exception: records `success=False` and logs the error — the
   scheduler continues running

**Standalone entrypoint:**
```bash
uv run python -m ingestion.scheduler
```
Starts the scheduler in the foreground. Exits cleanly on `Ctrl+C`.

---

## Files Modified

### `ingestion/core/config.py`

Added two new scheduler interval settings:

```python
# Scheduler intervals (Phase 2)
live_refresh_interval_hours: int = 6
news_refresh_interval_hours: int = 3
```

Both are loaded from `.env` and already present in `.env.example` from the
project scaffold.

---

### `ingestion/loaders/pgvector.py`

Added two new methods:

**`url_exists(url: str) -> bool`**
```sql
SELECT 1 FROM documents WHERE metadata->>'url' = :url
```
Used by `NewsExtractor` to skip already-ingested articles before fetching them.

**`prune_live_partition(older_than_days: int = 90) -> int`**
Deletes live chunks older than N days and then cleans up any orphaned live
documents that have no remaining chunks. Returns the number of chunks deleted.
Intended to be called by a weekly scheduled job (wired up in Phase 4 alongside
the API).

---

### `ingestion/pipeline.py`

Added `run_live(since: datetime | None)` function:
- Same structure as `run_static` but uses `OpenF1Extractor` and `NewsExtractor`
- Passes `loader.url_exists` as `url_exists_fn` to `NewsExtractor`
- Does **not** rebuild the IVFFlat index after each live run (rebuilds are
  reserved for bulk static ingestion)

Extended `main()` CLI:

```bash
uv run python -m ingestion.pipeline --phase live
uv run python -m ingestion.pipeline --phase live --since 2024-01-01
uv run python -m ingestion.pipeline --phase all        # static then live
```

The new `--since` flag accepts an ISO date string and is passed through to
`run_live()` as a timezone-aware `datetime`.

---

## Tests

| File | Tests added | Total tests |
|------|------------:|------------:|
| `tests/test_extractors.py` | +6 | 10 |
| `tests/test_scheduler.py` | 7 (new file) | 7 |
| **Total** | **+13** | **23** |

### New extractor tests (`test_extractors.py`)

- **`test_openf1_extracts_sessions`** — mocks all OpenF1 endpoints; verifies a
  session document is yielded with correct `source`, `partition`, and
  `session_key` in the parsed JSON
- **`test_openf1_extracts_stints`** — mocks stints endpoint; verifies the
  stint document's narrative contains tyre compound names
- **`test_openf1_returns_empty_on_no_sessions`** — verifies the extractor
  yields nothing (not an exception) when the sessions endpoint returns `[]`
- **`test_news_extracts_articles`** — mocks index page and article page HTML;
  verifies a document is yielded with correct source, content type, partition,
  and URL metadata
- **`test_news_skips_known_urls`** — injects an `url_exists_fn` that always
  returns `True`; verifies no documents are yielded
- **`test_news_returns_empty_on_broken_layout`** — feeds index page with no
  article links; verifies the extractor returns 0 docs without raising

### Scheduler tests (`test_scheduler.py`)

- **`test_scheduler_registers_both_jobs`** — verifies `create_scheduler()`
  registers jobs with IDs `openf1_refresh` and `news_scrape`
- **`test_scheduler_jobs_have_max_instances_one`** — asserts `max_instances=1`
  on all jobs
- **`test_scheduler_jobs_have_coalesce`** — asserts `coalesce=True` on all jobs
- **`test_scheduler_interval_matches_config`** — reads `Settings` and verifies
  trigger intervals match `live_refresh_interval_hours` and
  `news_refresh_interval_hours`
- **`test_run_openf1_refresh_writes_job_run`** — mocks all pipeline components
  and DB calls; verifies `_log_job_start` and `_log_job_finish` are called with
  `success=True`
- **`test_run_news_scrape_writes_job_run`** — same for the news job
- **`test_run_openf1_refresh_records_failure`** — forces an exception in
  `_get_last_synced`; verifies `_log_job_finish` is called with `success=False`
  and a non-empty `errors` list

**All 23 tests pass.**

---

## Database Tables Used (Phase 2)

All four tables defined in `db/schema.sql` are now active:

| Table | Phase 2 usage |
|-------|--------------|
| `documents` | Live documents written via `PgVectorLoader.upsert()` |
| `chunks` | Live chunks with embeddings written via `PgVectorLoader.upsert()` |
| `sync_state` | `last_synced_at` read and written by scheduler jobs |
| `job_runs` | One row written per job execution with status and stats |

---

## Expected Data Volume (Phase 2)

| Source | Est. documents per run | Est. chunks per run |
|--------|----------------------:|--------------------:|
| OpenF1 — full season first run | ~2,000 | ~6,000 |
| OpenF1 — incremental refresh | ~50–200 | ~150–600 |
| News — per scrape run | ~30–50 articles | ~300–500 |

Live partition total after a full season: **~25,000–35,000 chunks**.

---

## How to Run

```bash
# One-off live ingestion (all current-season data)
uv run python -m ingestion.pipeline --phase live

# One-off live ingestion from a specific date
uv run python -m ingestion.pipeline --phase live --since 2024-01-01

# Start the background scheduler (runs indefinitely)
uv run python -m ingestion.scheduler

# Run all tests
uv run python -m pytest tests/ -v
```

---

## Completion Criteria Status

- [x] `uv run python -m ingestion.pipeline --phase live` runs without error
- [x] News articles stored with correct `url` metadata
- [x] Running pipeline twice does not duplicate news articles (URL dedup works)
- [x] Scheduler starts with both jobs registered on correct intervals
- [x] `coalesce=True` and `max_instances=1` prevent overlapping runs
- [x] Each job writes a `job_runs` row on completion (success and failure)
- [x] `prune_live_partition()` removes stale live chunks
- [x] All 23 tests pass
