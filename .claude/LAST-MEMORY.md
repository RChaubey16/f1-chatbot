# Last Session Memory — F1 Chatbot

**Last updated:** 2026-04-01
**Session scope:** Phase 1 — Static KB Ingestion (complete)

---

## Project Overview

An F1 AI chatbot that answers questions about Formula 1 history (1950–2024) using
a RAG (Retrieval-Augmented Generation) pipeline. Data is ingested from Jolpica
API and Wikipedia, embedded with Ollama (`nomic-embed-text`), and stored in
PostgreSQL with pgvector for vector similarity search.

**Three-phase plan:**
- **Phase 1** (DONE): Static KB ingestion — Jolpica + Wikipedia
- **Phase 2** (TODO): Live KB + scheduler — OpenF1 + News scraping
- **Phase 3** (TODO): FastAPI RAG agent + query routing

---

## What Was Done

### Phase 0 — Scaffold (pre-existing before this session)

These files existed from the initial commit (`f98657a`):

- `pyproject.toml` — 29 dependencies pinned (FastAPI, SQLAlchemy, pgvector, httpx, etc.), Python >=3.13
- `docker-compose.yml` — PostgreSQL (pgvector:pg16) on port **5433**, Ollama on port 11434, both with healthchecks
- `db/schema.sql` — Full schema for all 3 phases: `documents`, `chunks`, `sync_state`, `job_runs` tables; pgvector extension; IVFFlat + GIN indexes
- `.env` / `.env.example` — All config vars (DB URL uses port 5433, chunk sizes 512/800, overlap 80, batch size 32)
- Directory structure with empty `__init__.py` files for `ingestion/`, `agent/`, `api/`, `tests/`
- `docs/PHASE_1.md`, `PHASE_2.md`, `PHASE_3.md` — Detailed implementation plans
- `docs/PLAN.md`, `PREREQUISITES.md` — Architecture overview and setup checklist

### Phase 1 — Static KB Ingestion (implemented this session)

All 14 files below were created from scratch. **10 tests pass.**

#### Core Layer (`ingestion/core/`)

| File | What it does |
|------|-------------|
| `config.py` (33 lines) | `Settings` class via `pydantic-settings`, loads from `.env`. Singleton `settings` object imported everywhere. Keys: `database_url`, `ollama_base_url`, `embedding_model`, `user_agent` (required by Wikipedia API), `request_delay_seconds`, `max_retries`, `chunk_size_structured` (512), `chunk_size_narrative` (800), `chunk_overlap` (80), `embedding_batch_size` (32). |
| `models.py` (75 lines) | 3 enums (`SourceType`, `ContentType`, `KBPartition`), 3 dataclasses (`RawDocument` with `xxhash` fingerprint property, `Chunk` with optional embedding, `IngestionResult` with stats + `summarise()`). |
| `logging.py` (23 lines) | `structlog` config with ISO timestamps + console renderer. `setup_logging()` and `get_logger(name)`. |

#### Extractors (`ingestion/extractors/`)

| File | What it does |
|------|-------------|
| `base.py` (24 lines) | Abstract `BaseExtractor` — `extract() -> AsyncIterator[RawDocument]` + `health_check() -> bool`. |
| `jolpica.py` (221 lines) | `JolpicaExtractor(start_year=1950, end_year=2024)`. Fetches from `https://api.jolpi.ca/ergast/f1`. Endpoints: `/drivers`, `/constructors`, `/{year}/results`, `/{year}/qualifying` (1994+), `/{year}/driverStandings`, `/{year}/constructorStandings`. Pagination via `_get_all_pages()` with `limit=100`. Rate limiting with `asyncio.sleep()`. Tenacity retry (3 attempts, exponential backoff). Each API response item becomes one `RawDocument` with JSON-serialized `raw_content`. |
| `wikipedia.py` (220 lines) | `WikipediaExtractor()`. 58 predefined articles across 4 categories: 25 drivers, 10 constructors, 13 circuits, 10 topics. Fetches per-section (not whole articles) via Wikipedia API. Uses `User-Agent` header from `settings.user_agent` (Wikipedia returns 403 without it). `_clean_wikitext()` strips templates, unwraps links, removes refs/HTML. Skips boilerplate sections (References, See Also, etc.) and short sections (<50 chars). 0.2s delay between sections, `REQUEST_DELAY_SECONDS` between articles. |

#### Transformer (`ingestion/transformers/`)

| File | What it does |
|------|-------------|
| `chunker.py` (185 lines) | `Chunker` with `chunk(doc) -> list[Chunk]`. Jolpica docs: `_to_narrative()` converts JSON to prose, then `RecursiveCharacterTextSplitter(512, 80)`. Wikipedia docs: split directly with `RecursiveCharacterTextSplitter(800, 80)`. Five formatters: `_format_race_result`, `_format_qualifying`, `_format_driver`, `_format_constructor`, `_format_standings`. Chunk IDs: `{fingerprint}_{index}`. |

#### Embedder (`ingestion/embedders/`)

| File | What it does |
|------|-------------|
| `ollama.py` (64 lines) | `OllamaEmbedder`. Calls `POST {ollama_base_url}/api/embeddings` with `nomic-embed-text` (768-dim vectors). `embed_batch()` processes in groups of 32 using `asyncio.gather`. Tenacity retry. `health_check()` verifies model availability via `/api/tags`. |

#### Loader (`ingestion/loaders/`)

| File | What it does |
|------|-------------|
| `pgvector.py` (120 lines) | `PgVectorLoader`. SQLAlchemy async engine. `doc_exists(fingerprint)` for dedup check. `upsert(doc, chunks)` — inserts document + bulk-upserts chunks with `ON CONFLICT (chunk_id) DO UPDATE`. `rebuild_index()` drops and recreates IVFFlat index (`lists=100`, `vector_cosine_ops`). `get_chunk_count()` for final reporting. |

#### Pipeline + Healthcheck

| File | What it does |
|------|-------------|
| `pipeline.py` (102 lines) | `run_static(start_year, end_year)` — orchestrates extract→chunk→embed→load with tqdm progress bar, dedup short-circuit, index rebuild at end. CLI via `argparse`: `--phase static|live|all`, `--start-year`, `--end-year`. Entry: `uv run python -m ingestion.pipeline --phase static`. |
| `healthcheck.py` (119 lines) | Pre-flight checks for PostgreSQL (connection + pgvector extension), Ollama (API + model), Jolpica API, Wikipedia API. Wikipedia check uses `User-Agent` header. Exits 0/1. Entry: `uv run python -m ingestion.healthcheck`. |

#### Tests

| File | What it does |
|------|-------------|
| `tests/conftest.py` (10 lines) | Auto-use fixture for `setup_logging()`. |
| `tests/test_extractors.py` (181 lines) | 4 tests: Jolpica driver extraction with mocked HTTP (respx), fingerprint uniqueness, Wikipedia section extraction with mocked API, wikitext cleanup. |
| `tests/test_pipeline.py` (141 lines) | 6 tests: Chunker for race results/drivers/wiki, chunk ID format, fingerprint idempotency, content-fingerprint divergence. |

#### Modified Files

| File | Change |
|------|--------|
| `pyproject.toml` | Added `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |

#### Documentation Created

| File | What it does |
|------|-------------|
| `docs/Phase-1-summary.md` | Comprehensive Phase 1 summary with architecture diagram, file details, data volume estimates, run instructions |
| `explain/notes.md` | Beginner-friendly guide to the entire project for someone who has never worked with Python or built a service |

---

## What Was NOT Done Yet

### Phase 2 — Live KB + Scheduler
- `ingestion/extractors/openf1.py` — OpenF1 API for live session data
- `ingestion/extractors/news.py` — Motorsport.com scraper with URL-based dedup
- `ingestion/scheduler.py` — APScheduler jobs for periodic refresh
- `tests/test_scheduler.py`
- Tables `sync_state` and `job_runs` exist in schema but no code uses them yet

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

---

## Important Technical Notes

- **Port:** PostgreSQL is on port **5433** (not default 5432) in docker-compose and .env `DATABASE_URL`
- **Python version:** >=3.13 (pinned in pyproject.toml)
- **Embedding dimensions:** 768 (nomic-embed-text) — must match `vector(768)` in schema
- **Qualifying data:** Only available from 1994 onwards — extractor skips earlier years
- **Deduplication:** Fingerprint = `xxhash.xxh64` of `raw_content`; checked before chunking/embedding to avoid wasted compute
- **Index rebuild:** IVFFlat index is dropped and recreated after each full ingestion run
- **Dependencies:** All locked in `uv.lock`, install with `uv sync`; dev deps via `uv sync --extra dev`
- **Test framework:** pytest + pytest-asyncio (auto mode) + respx for HTTP mocking
- **Wikipedia User-Agent:** Wikipedia API returns 403 without a proper `User-Agent` header. Added `user_agent` to `Settings` and used in `WikipediaExtractor` and `check_wikipedia()` healthcheck. Value: `"F1Chatbot/0.1 (https://github.com/f1-chatbot; f1chatbot@example.com)"`
- **No code pushed yet** — all changes are local, uncommitted

---

## How to Resume

```bash
# Start services
docker compose up -d
docker compose exec ollama ollama pull nomic-embed-text

# Verify
uv run python -m ingestion.healthcheck

# Run ingestion (if not done yet)
uv run python -m ingestion.pipeline --phase static

# Run tests
uv run pytest tests/ -v

# Next: Start Phase 2 from docs/PHASE_2.md
```

---

## Git State

- **Branch:** `main`
- **Last commit:** `f98657a chore: project scaffold, packages, docker, db schema, env`
- **Uncommitted changes:** All Phase 1 implementation files (14 new Python files + 1 modified `pyproject.toml` + 2 docs files + 1 explain file + 1 `.claude/LAST-MEMORY.md`)
- **Nothing has been committed or pushed for Phase 1 work**
- **Second commit needed:** `be8acae feat: bootstrap the static knowledge base with all historical F1 data` already exists but only contains data files. All Phase 1 code is uncommitted.
