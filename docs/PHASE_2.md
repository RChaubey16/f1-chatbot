# Phase 2 — Live KB Ingestion (OpenF1 + News Scraper + Scheduler)

## Goal

Extend the knowledge base with a live partition that stays fresh throughout the
racing season. A scheduler runs background refresh jobs on a configurable
interval so the chatbot always has current standings, session results, and
recent news.

**Completion criteria:**
- OpenF1 API data (current season sessions, lap data, stint info) ingested
- News articles from Motorsport.com scraped and embedded
- APScheduler running both jobs on configurable intervals
- Live partition clearly separated from static (different `partition` tag,
  easy to wipe and rebuild independently)

---

## What Changes vs Phase 1

Phase 2 reuses every component from Phase 1 without modification:
- Same `RawDocument` / `Chunk` models
- Same `OllamaEmbedder`
- Same `PgvectorLoader`
- Same `Chunker`

New additions only:
- Two new extractors (`OpenF1Extractor`, `NewsExtractor`)
- One new scheduler module (`ingestion/scheduler.py`)
- Small extension to `pipeline.py` for `--phase live`

---

## Step 1 — OpenF1 Extractor

### File: `ingestion/extractors/openf1.py`

OpenF1 is a free, open REST API — no auth required. Base URL:
`https://api.openf1.org/v1`

**Endpoints to ingest:**

| Endpoint | Content type | Notes |
|---|---|---|
| `/sessions` | `race_result` | All sessions (FP1–3, Quali, Race, Sprint) |
| `/drivers` | `driver_profile` | Current season driver info |
| `/position` | `race_result` | Position data per session |
| `/stints` | `lap_data` | Tyre stints per driver per session |
| `/pit` | `race_result` | Pit stop timings |
| `/intervals` | `race_result` | Gap to leader per lap |

**Incremental sync strategy:**

OpenF1 returns data filtered by `session_key`. The extractor should:
1. On first run → fetch all sessions from `date_start >= {current_season}-01-01`
2. On subsequent runs → only fetch sessions newer than `last_synced_at`
   (store this timestamp in a `sync_state` table)

```sql
-- Add to db/schema.sql
CREATE TABLE IF NOT EXISTS sync_state (
    source       TEXT PRIMARY KEY,
    last_synced_at TIMESTAMPTZ,
    metadata     JSONB DEFAULT '{}'
);
```

**Constructor params:**
- `season: int` — defaults to current year
- `since: datetime | None` — if provided, only fetch newer sessions

**`_to_narrative` for OpenF1 session:**
```
Session: Australian Grand Prix 2024 — Race
Date: 2024-03-24
Circuit: Albert Park

Position data:
P1: Max Verstappen (Red Bull) — led from lap 12
P2: Carlos Sainz (Ferrari) — +2.366s
...

Stints:
Verstappen: Medium (laps 1–18) → Hard (laps 19–58)
...
```

---

## Step 2 — News Scraper Extractor

### File: `ingestion/extractors/news.py`

**Target:** `https://www.motorsport.com/f1/news/`

This is the most fragile part of the pipeline — scrapers break when sites
change their HTML structure. Design it to fail gracefully and log loudly
rather than silently corrupt the knowledge base.

**Libraries:** `httpx` + `BeautifulSoup` (already in deps)

**Scraping strategy:**

```
1. Fetch the F1 news index page
2. Extract article URLs (CSS selector: find all <a> tags within article cards)
3. For each URL — fetch full article page
4. Extract: headline, published date, author, article body text
5. Strip boilerplate (nav, ads, related articles section)
6. Yield one RawDocument per article
```

**Metadata to capture:**
```python
metadata = {
    "headline": "...",
    "url": "https://www.motorsport.com/f1/news/...",
    "published_at": "2024-03-25T10:30:00",
    "author": "...",
    "tags": ["race-report", "red-bull"],
}
```

**Deduplication:** URL stored in metadata is the natural dedup key. Before
scraping an article, check if a document with `metadata->>'url' = ?` already
exists in the `documents` table.

**Add a SQL helper to `PgvectorLoader`:**
```python
async def url_exists(self, url: str) -> bool:
    # SELECT 1 FROM documents WHERE metadata->>'url' = $1
```

**Rate limiting:** 2s between article fetches — news sites are not APIs.

**Fallback:** If Motorsport.com changes layout, the scraper should log a
warning and return 0 documents rather than crash the scheduler.

**Constructor params:**
- `max_articles: int = 50` — cap per run to avoid overloading
- `since: datetime | None` — skip articles older than this

---

## Step 3 — Scheduler

### File: `ingestion/scheduler.py`

Uses `APScheduler` with an async job store backed by the existing Postgres
connection.

**Two scheduled jobs:**

```python
# Job 1: Refresh OpenF1 live session data
scheduler.add_job(
    run_openf1_refresh,
    trigger="interval",
    hours=LIVE_REFRESH_INTERVAL_HOURS,   # default 6
    id="openf1_refresh",
    replace_existing=True,
)

# Job 2: Scrape latest news
scheduler.add_job(
    run_news_scrape,
    trigger="interval",
    hours=NEWS_REFRESH_INTERVAL_HOURS,   # default 3
    id="news_scrape",
    replace_existing=True,
)
```

**Scheduler startup:** The scheduler starts as a background task when the
FastAPI app starts (Phase 3). For Phase 2, expose it as a standalone entrypoint
too:

```bash
uv run python -m ingestion.scheduler   # runs scheduler in foreground
```

**Job locking:** Use APScheduler's `coalesce=True` + `max_instances=1` to
prevent overlapping runs if a job takes longer than its interval.

**Job result logging:** Each job should log an `IngestionResult.summarise()`
on completion and write a row to a `job_runs` table:

```sql
CREATE TABLE IF NOT EXISTS job_runs (
    id          SERIAL PRIMARY KEY,
    job_id      TEXT NOT NULL,
    started_at  TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    docs_upserted INT DEFAULT 0,
    errors      JSONB DEFAULT '[]',
    success     BOOLEAN DEFAULT FALSE
);
```

---

## Step 4 — Extend Pipeline CLI

### File: `ingestion/pipeline.py` (extend Phase 1 version)

Add `--phase live` handling:

```python
async def run_live(since: datetime | None = None):
    extractors = [
        OpenF1Extractor(since=since),
        NewsExtractor(since=since),
    ]
    for extractor in extractors:
        async for raw_doc in extractor.extract():
            chunks = chunker.chunk(raw_doc)
            chunks = await embedder.embed_batch(chunks)
            await loader.upsert(raw_doc, chunks)
```

CLI flags:
```bash
uv run python -m ingestion.pipeline --phase live
uv run python -m ingestion.pipeline --phase live --since 2024-01-01
uv run python -m ingestion.pipeline --phase all   # static + live
```

---

## Step 5 — Live Partition Management

The live partition will accumulate stale data over time (old news articles
become less relevant). Add a utility to prune old live chunks:

### File: `ingestion/loaders/pgvector.py` (extend)

```python
async def prune_live_partition(older_than_days: int = 90):
    """Delete live chunks older than N days."""
    # DELETE FROM chunks
    # WHERE partition = 'live'
    # AND created_at < NOW() - INTERVAL '{older_than_days} days'
    #
    # Also clean up orphaned documents
```

Add a weekly scheduled job to call this.

---

## Docker Compose Changes (Phase 2)

No new services required. The existing `postgres` + `ollama` stack handles
everything. Just ensure `LIVE_REFRESH_INTERVAL_HOURS` and
`NEWS_REFRESH_INTERVAL_HOURS` are in `.env`.

---

## Testing

### File: `tests/test_extractors.py` (extend)

- Mock OpenF1 HTTP responses; assert correct session → narrative conversion
- Mock Motorsport.com HTML; assert article body extracted correctly
- Assert scraper returns 0 docs (not an error) when HTML structure not found

### File: `tests/test_scheduler.py`

- Assert both jobs are registered on scheduler startup
- Assert `max_instances=1` prevents concurrent runs
- Assert `job_runs` table gets a row written on completion

---

## Expected Data Volume (Phase 2)

| Source | Est. documents per run | Est. chunks per run |
|---|---|---|
| OpenF1 (full season first run) | ~2,000 | ~6,000 |
| OpenF1 (incremental refresh) | ~50–200 | ~150–600 |
| News (per scrape run) | ~30–50 articles | ~300–500 |

Live partition total after a full season: ~25,000–35,000 chunks.

---

## Phase 2 Done When

- [ ] `uv run python -m ingestion.pipeline --phase live` runs without error
- [ ] `SELECT COUNT(*) FROM chunks WHERE partition = 'live';` returns > 0
- [ ] News articles appear in DB with correct `url` metadata
- [ ] Running pipeline twice does not duplicate news articles (URL dedup works)
- [ ] Scheduler starts and both jobs fire on schedule (verify via `job_runs` table)
- [ ] `prune_live_partition()` removes old rows correctly
- [ ] All tests pass
