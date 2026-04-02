# Last Session Memory — F1 Chatbot

**Last updated:** 2026-04-02
**Session scope:** Phase 2 — Live KB Ingestion (complete)

---

## Project Overview

An F1 AI chatbot that answers questions about Formula 1 history (1950–2024) and
the current live season, using a RAG (Retrieval-Augmented Generation) pipeline.
Data is ingested from Jolpica API, Wikipedia, OpenF1 API, and Motorsport.com,
embedded with Ollama (`nomic-embed-text`), and stored in PostgreSQL with pgvector
for vector similarity search.

**Three-phase plan:**
- **Phase 1** (DONE): Static KB ingestion — Jolpica + Wikipedia
- **Phase 2** (DONE): Live KB + scheduler — OpenF1 + News scraping
- **Phase 3** (TODO): FastAPI RAG agent + query routing

---

## What Was Done This Session

### README.md

- Created comprehensive `README.md` with architecture diagram, full tech stack,
  project structure, getting started guide, env var table, data sources detail,
  ingestion pipeline breakdown, DB schema tables, and roadmap.
- Fixed PostgreSQL port: `.env.example` had `POSTGRES_PORT=5432` / `DATABASE_URL`
  pointing to 5432 — corrected to **5433** to match docker-compose port mapping.
  README and `.env.example` were both updated.

### Phase 2 — Live KB Ingestion (implemented this session)

#### Files Created

| File | What it does |
|------|-------------|
| `ingestion/extractors/openf1.py` (~230 lines) | `OpenF1Extractor(season, since)`. Fetches from `https://api.openf1.org/v1`. Endpoints: `/sessions`, `/drivers`, `/position`, `/stints`, `/pit`. Incremental sync via `since` datetime. Per-endpoint try/except so one failure doesn't abort the session. Tenacity retry (3 attempts). All docs use `partition=KBPartition.LIVE`. |
| `ingestion/extractors/news.py` (~220 lines) | `NewsExtractor(max_articles, since, url_exists_fn)`. Scrapes `https://www.motorsport.com/f1/news/`. Two CSS selector patterns for article URLs (graceful fallback). 2s delay between articles. URL-based dedup via injected `url_exists_fn`. Fails gracefully (0 docs, not exception) on broken layout. Captures headline, published_at, author, tags, body. |
| `ingestion/scheduler.py` (~240 lines) | `create_scheduler()` returns `AsyncIOScheduler` with `openf1_refresh` (interval=`live_refresh_interval_hours`, default 6h) and `news_scrape` (interval=`news_refresh_interval_hours`, default 3h). Both have `coalesce=True`, `max_instances=1`. Each job: reads `sync_state`, runs full extract→chunk→embed→load pipeline, updates `sync_state`, writes `job_runs` row. Standalone CLI: `python -m ingestion.scheduler`. |
| `tests/test_scheduler.py` (7 tests) | Tests: job registration, max_instances, coalesce, interval config, job_run written on success (openf1 + news), job_run written with success=False on exception. Uses `unittest.mock` — no real DB or scheduler needed. |

#### Files Modified

| File | Change |
|------|--------|
| `ingestion/core/config.py` | Added `live_refresh_interval_hours: int = 6` and `news_refresh_interval_hours: int = 3` |
| `ingestion/loaders/pgvector.py` | Added `url_exists(url: str) -> bool` (checks `metadata->>'url'`) and `prune_live_partition(older_than_days=90) -> int` |
| `ingestion/pipeline.py` | Added `run_live(since)` function; added `--phase live` and `--since YYYY-MM-DD` CLI flags; `--phase all` now runs both static and live |
| `tests/test_extractors.py` | Added 6 new tests for OpenF1 (3) and News (3) extractors |

#### Documentation Created / Updated

| File | Change |
|------|--------|
| `docs/Phase-2-summary.md` | Full technical summary matching Phase-1-summary.md format |
| `explain/notes.md` | Updated with Phase 2 — new extractors, scheduler section, updated project structure, updated tests section, Phase 2 glossary terms |
| `README.md` | Created from scratch this session (see above) |

---

## Test Results

**23 tests, all passing.**

| File | Tests | Status |
|------|------:|--------|
| `tests/test_extractors.py` | 10 | ✅ All pass |
| `tests/test_pipeline.py` | 6 | ✅ All pass |
| `tests/test_scheduler.py` | 7 | ✅ All pass |

Run: `/home/ruturaj-hp/.local/bin/uv sync --extra dev && /home/ruturaj-hp/.local/bin/uv run python -m pytest tests/ -v`

---

## Important Technical Notes

- **Port:** PostgreSQL is on port **5433** (not default 5432) in docker-compose and `.env` `DATABASE_URL`. `.env.example` was incorrectly showing 5432 — fixed this session.
- **Python version:** >=3.13 (pinned in pyproject.toml)
- **Embedding dimensions:** 768 (nomic-embed-text) — must match `vector(768)` in schema
- **Qualifying data:** Only available from 1994 onwards — Jolpica extractor skips earlier years
- **Deduplication:**
  - Static/structured data: fingerprint = `xxhash.xxh64` of `raw_content`
  - News articles: URL stored in `metadata->>'url'`, checked via `loader.url_exists()`
- **Index rebuild:** IVFFlat index is dropped and recreated after static ingestion only (not live runs)
- **uv dev deps:** `uv sync` alone does NOT install pytest. Must use `uv sync --extra dev`
- **Async generator mocking:** When mocking an async generator method in tests, use `MagicMock(side_effect=fn)` not `AsyncMock(return_value=...)`. AsyncMock wraps the result in a coroutine, which breaks `async for`.
- **Dependencies:** All locked in `uv.lock`, install with `uv sync --extra dev`
- **Wikipedia User-Agent:** Wikipedia API returns 403 without a proper `User-Agent` header. Value: `"F1Chatbot/0.1 (https://github.com/f1-chatbot; f1chatbot@example.com)"`

---

## Database Tables — All Four Now Active

| Table | Used Since | Purpose |
|-------|-----------|---------|
| `documents` | Phase 1 | One row per raw document, dedup via fingerprint |
| `chunks` | Phase 1 | Text chunks with 768-dim embeddings |
| `sync_state` | Phase 2 | `last_synced_at` per source for incremental sync |
| `job_runs` | Phase 2 | Audit log — one row per scheduler job execution |

---

## What Was NOT Done Yet

### Phase 3 — FastAPI RAG Agent
- `agent/retriever.py` — Hybrid search (pgvector + BM25 full-text via RRF)
- `agent/router.py` — Query intent classification (HISTORICAL/CURRENT/MIXED)
- `agent/tools.py` — Structured tools (standings, results lookup)
- `agent/agent.py` — Core reasoning loop
- `agent/prompts.py` — System prompts
- `api/main.py` — FastAPI app
- `api/schemas.py` — Request/response models
- `api/routes/chat.py` — POST /chat + GET /chat/stream
- `api/routes/health.py` — GET /health
- `Dockerfile`
- `tests/test_agent.py`
- Weekly `prune_live_partition()` scheduled job (wired into Phase 3 scheduler)

---

## How to Resume

```bash
# Start services
docker compose up -d
docker compose exec ollama ollama pull nomic-embed-text

# Verify
uv run python -m ingestion.healthcheck

# Run static ingestion (if not done yet)
uv run python -m ingestion.pipeline --phase static

# Run live ingestion
uv run python -m ingestion.pipeline --phase live

# Start background scheduler
uv run python -m ingestion.scheduler

# Run tests
/home/ruturaj-hp/.local/bin/uv sync --extra dev
/home/ruturaj-hp/.local/bin/uv run python -m pytest tests/ -v

# Next: Start Phase 3 from docs/PHASE_3.md
```

---

## Git State

- **Branch:** `main`
- **Recent commits:**
  - `4db8c8d` chore: increase intervals between requests to avoid rate-limitation from Jolpica
  - `6fe9a91` fix: add user-agent header for requests to wikipedia API
  - `be8acae` feat: bootstrap the static knowledge base with all historical F1 data
  - `f98657a` chore: project scaffold, packages, docker, db schema, env
- **Uncommitted this session:** All Phase 2 files + README.md + docs/Phase-2-summary.md + explain/notes.md updates + .env.example port fix
- **Nothing has been committed or pushed for Phase 2 work**
