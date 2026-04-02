# Phase 1 Summary — Static KB Ingestion (Jolpica + Wikipedia)

## Overview

Phase 1 bootstraps the static knowledge base with all historical F1 data
(1950–2024). The system can answer any question about F1 history by performing
vector similarity search over embedded chunks stored in PostgreSQL with
pgvector. The implementation follows an **Extract → Transform → Embed → Load**
pipeline architecture, fully async, with structured logging, retry logic, and
fingerprint-based deduplication.

---

## Architecture

```
                         ┌──────────────────┐
                         │   CLI Entry Point │
                         │  ingestion/       │
                         │  pipeline.py      │
                         └────────┬─────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                    │
    ┌─────────▼────────┐ ┌───────▼────────┐ ┌────────▼───────┐
    │ JolpicaExtractor │ │ WikipediaExtr. │ │ (future Phase  │
    │ (1950–2024 API)  │ │ (58 articles)  │ │  2 extractors) │
    └─────────┬────────┘ └───────┬────────┘ └────────────────┘
              │                   │
              └─────────┬─────────┘
                        │ RawDocument stream
                        ▼
              ┌─────────────────────┐
              │  Chunker            │
              │  (JSON→prose, split)│
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
              ┌─────────────────────┐
              │  PostgreSQL + pgvector │
              │  (768-dim vectors)     │
              └────────────────────────┘
```

---

## Files Created

### Core Layer — `ingestion/core/`

These modules form the shared foundation used by every pipeline stage.

| File | Lines | Purpose |
|------|------:|---------|
| `config.py` | 30 | Centralised settings via `pydantic-settings` |
| `models.py` | 75 | Domain models and enums shared across all stages |
| `logging.py` | 23 | Structured logging setup with `structlog` |

#### `ingestion/core/config.py`

A single `Settings` class (inherits `pydantic_settings.BaseSettings`) that loads
all configuration from `.env`. Exposes:

- **Database:** `database_url` (PostgreSQL + asyncpg connection string)
- **Ollama:** `ollama_base_url`, `embedding_model`
- **Ingestion tuning:** `request_delay_seconds`, `max_retries`,
  `chunk_size_structured` (512), `chunk_size_narrative` (800),
  `chunk_overlap` (80), `embedding_batch_size` (32)

A module-level singleton `settings = Settings()` is imported everywhere — no
`os.getenv` calls scattered around the codebase.

#### `ingestion/core/models.py`

Defines the data contracts for the entire pipeline:

- **Enums:**
  - `SourceType` — `jolpica | wikipedia | openf1 | news`
  - `ContentType` — `race_result | qualifying_result | standings | driver_profile | constructor_profile | narrative`
  - `KBPartition` — `static | live`
- **Dataclasses:**
  - `RawDocument` — output of extractors; includes a `fingerprint` property
    computed as `xxhash.xxh64` of `raw_content` for deduplication
  - `Chunk` — a text fragment with optional embedding vector, linked to its
    parent document via `doc_fingerprint`
  - `IngestionResult` — accumulates pipeline statistics
    (`docs_fetched`, `docs_skipped_duplicate`, `chunks_created`,
    `chunks_embedded`, `chunks_upserted`, `errors`) with a `summarise()` method

#### `ingestion/core/logging.py`

Configures `structlog` with:
- ISO-8601 timestamps
- Log-level enrichment
- Context-variable merging
- Console renderer for human-readable output

Provides `get_logger(name)` factory used by all modules.

---

### Extractors — `ingestion/extractors/`

Extractors are async generators that yield `RawDocument` objects one at a time,
enabling the pipeline to start chunking and embedding while extraction continues.

| File | Lines | Purpose |
|------|------:|---------|
| `base.py` | 24 | Abstract base class defining the extractor contract |
| `jolpica.py` | 221 | Fetches structured F1 data from Jolpica API |
| `wikipedia.py` | 218 | Fetches narrative content from Wikipedia articles |

#### `ingestion/extractors/base.py`

Abstract `BaseExtractor` with two methods:
- `extract() -> AsyncIterator[RawDocument]` — yields documents for streaming
- `health_check() -> bool` — verifies upstream reachability

#### `ingestion/extractors/jolpica.py`

`JolpicaExtractor` fetches from the Jolpica REST API
(`https://api.jolpi.ca/ergast/f1`), which is an Ergast-compatible data source
covering all F1 seasons from 1950 to 2024.

**Endpoints consumed:**

| Endpoint | ContentType | Scope |
|----------|-------------|-------|
| `/drivers` | `driver_profile` | All ~850 drivers |
| `/constructors` | `constructor_profile` | All ~210 constructors |
| `/{year}/results` | `race_result` | ~1,100 races |
| `/{year}/qualifying` | `qualifying_result` | ~1,100 sessions (1994+) |
| `/{year}/driverStandings` | `standings` | 75 seasons |
| `/{year}/constructorStandings` | `standings` | 75 seasons |

**Key implementation details:**
- **Pagination:** `_get_all_pages(path)` loops with `limit=100` and `offset`
  until `offset >= total`
- **Rate limiting:** `asyncio.sleep(REQUEST_DELAY_SECONDS)` between pages
- **Retry:** All HTTP calls wrapped with `tenacity` (3 attempts, exponential
  backoff)
- **Constructor params:** `start_year` (default 1950), `end_year` (default 2024)

#### `ingestion/extractors/wikipedia.py`

`WikipediaExtractor` fetches per-section content from 58 predefined F1-related
Wikipedia articles across four categories:

| Category | Articles | Examples |
|----------|------:|---------|
| Drivers | 25 | Schumacher, Senna, Hamilton, Verstappen |
| Constructors | 10 | Ferrari, McLaren, Mercedes, Red Bull |
| Circuits | 13 | Monaco, Silverstone, Spa, Suzuka |
| Topics | 10 | Formula One, History, Regulations, DRS |

**Extraction strategy:** Fetches each article section individually (not whole
articles), so the chunker receives semantically coherent units.

**API calls per article:**
1. `action=query&prop=extracts&exintro=true` — intro section
2. `action=parse&prop=sections` — section list
3. `action=parse&section={index}&prop=wikitext` — per-section text

**Wikitext cleanup** (`_clean_wikitext` static method):
- Strips `{{templates}}`
- Unwraps `[[link|display]]` to plain text
- Removes `<ref>` tags and other HTML
- Normalises whitespace

**Filtering:** Skips boilerplate sections (References, External Links, See Also,
etc.) and sections with fewer than 50 characters.

---

### Transformer — `ingestion/transformers/`

| File | Lines | Purpose |
|------|------:|---------|
| `chunker.py` | 185 | Source-aware chunking with JSON-to-prose conversion |

#### `ingestion/transformers/chunker.py`

`Chunker` applies different strategies depending on the data source:

| Source | Pre-processing | Chunk Size | Overlap |
|--------|---------------|-----------|---------|
| Jolpica (structured JSON) | `_to_narrative()` converts JSON to human-readable prose | 512 chars | 80 chars |
| Wikipedia (narrative text) | Light cleanup only | 800 chars | 80 chars |

Both use `langchain_text_splitters.RecursiveCharacterTextSplitter`.

**Narrative converters** (structured JSON to readable prose):

- `_format_race_result(data, meta)` — produces:
  ```
  Race: Monaco Grand Prix 2019
  Circuit: Circuit de Monaco
  P1: Lewis Hamilton (Mercedes) — 1:43:28.437 [25 pts]
  P2: Sebastian Vettel (Ferrari) — +2.654 [18 pts]
  ```
- `_format_qualifying(data, meta)` — position, driver, Q1/Q2/Q3 times
- `_format_driver(data)` — name, nationality, DOB, permanent number
- `_format_constructor(data)` — name, nationality
- `_format_standings(data, meta)` — ranked list with points

**Chunk IDs:** Generated as `{doc_fingerprint}_{index}` for deterministic,
deduplication-safe identification.

---

### Embedder — `ingestion/embedders/`

| File | Lines | Purpose |
|------|------:|---------|
| `ollama.py` | 64 | Batch embedding via local Ollama instance |

#### `ingestion/embedders/ollama.py`

`OllamaEmbedder` calls the local Ollama API
(`POST /api/embeddings`) using the `nomic-embed-text` model, which produces
**768-dimensional** vectors matching the `vector(768)` column in the database
schema.

**Key features:**
- **Batching:** Processes chunks in groups of `EMBEDDING_BATCH_SIZE` (default 32)
- **Concurrency:** Uses `asyncio.gather` for parallel requests within each batch
- **Retry:** `tenacity` with 3 attempts and exponential backoff
- **Health check:** Verifies Ollama is running and the embedding model is loaded

---

### Loader — `ingestion/loaders/`

| File | Lines | Purpose |
|------|------:|---------|
| `pgvector.py` | 120 | PostgreSQL upserts with fingerprint-based deduplication |

#### `ingestion/loaders/pgvector.py`

`PgVectorLoader` manages persistence to PostgreSQL via SQLAlchemy async engine.

**Deduplication logic:**
1. Check `documents` table for existing `fingerprint`
2. If found: skip document and all its chunks
3. If not found: insert document, then bulk-upsert chunks

**Chunk upsert** uses `ON CONFLICT (chunk_id) DO UPDATE` to safely handle
re-ingestion — only `embedding` and `metadata` are updated on conflict.

**Index management:**
- `rebuild_index()` drops and recreates the IVFFlat index after bulk ingestion
- Uses `vector_cosine_ops` with `lists = 100` for approximate nearest-neighbour
  search

---

### Pipeline Orchestrator — `ingestion/pipeline.py`

| File | Lines | Purpose |
|------|------:|---------|
| `pipeline.py` | 102 | Ties all stages together with CLI entry point |

Implements `run_static()` which:
1. Instantiates all components (chunker, embedder, loader)
2. Iterates over extractors (Jolpica, Wikipedia)
3. For each `RawDocument`: checks dedup, chunks, embeds, upserts
4. Tracks progress with `tqdm`
5. Rebuilds IVFFlat index after completion
6. Reports final chunk count and statistics

**CLI interface:**
```bash
uv run python -m ingestion.pipeline --phase static
uv run python -m ingestion.pipeline --phase static --start-year 2000  # partial run
```

Supports `--phase` (`static | live | all`) and `--start-year`/`--end-year` flags.

---

### Health Check — `ingestion/healthcheck.py`

| File | Lines | Purpose |
|------|------:|---------|
| `healthcheck.py` | 117 | Pre-flight verification of all external dependencies |

Checks four services before ingestion:

| Service | Verification |
|---------|-------------|
| PostgreSQL | Connection + pgvector extension presence |
| Ollama | API reachable + `nomic-embed-text` model loaded |
| Jolpica API | HTTP 200 on `/drivers.json?limit=1` |
| Wikipedia API | HTTP 200 on `action=query&meta=siteinfo` |

Exits with code 0 (all pass) or 1 (any fail) with clear error messages.

```bash
uv run python -m ingestion.healthcheck
```

---

### Tests

| File | Lines | Tests | Purpose |
|------|------:|------:|---------|
| `tests/test_extractors.py` | 181 | 4 | Extractor output validation with mocked HTTP |
| `tests/test_pipeline.py` | 141 | 6 | Chunker logic and fingerprint behaviour |
| `tests/conftest.py` | 10 | — | Shared test setup (auto-initialises logging) |

#### `tests/test_extractors.py`

- **`test_jolpica_extracts_drivers`** — mocks Jolpica API, verifies driver
  documents have correct `source`, `content_type`, `partition`, and parsed content
- **`test_jolpica_fingerprint_changes_with_content`** — confirms different
  content produces different fingerprints (dedup correctness)
- **`test_wikipedia_extracts_sections`** — mocks Wikipedia API (intro, sections,
  wikitext), verifies documents are yielded with correct metadata
- **`test_wikipedia_clean_wikitext`** — verifies template removal, link
  unwrapping, and ref-tag stripping

#### `tests/test_pipeline.py`

- **`test_chunk_race_result`** — verifies race JSON is converted to prose
  containing "Monaco Grand Prix" and driver positions
- **`test_chunk_driver_profile`** — verifies driver JSON becomes readable text
  with name and nationality
- **`test_chunk_wikipedia`** — verifies narrative content is split correctly
- **`test_chunk_ids_use_fingerprint`** — confirms chunk IDs follow
  `{fingerprint}_{index}` format
- **`test_idempotent_fingerprint`** — same content always produces same
  fingerprint
- **`test_different_content_different_fingerprint`** — different content produces
  different fingerprints

**All 10 tests pass.**

---

## Files Modified

| File | Change |
|------|--------|
| `pyproject.toml` | Added `[tool.pytest.ini_options]` section with `asyncio_mode = "auto"` |

---

## Pre-existing Files (from scaffold)

These were created before Phase 1 implementation and remain unchanged:

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata + 29 pinned dependencies |
| `docker-compose.yml` | PostgreSQL (pgvector:pg16, port 5433) + Ollama (port 11434) |
| `db/schema.sql` | `documents` + `chunks` tables, pgvector extension, IVFFlat + GIN indexes |
| `.env` / `.env.example` | Environment configuration for all services |
| `ingestion/__init__.py` | Package init (empty) |
| `ingestion/core/__init__.py` | Package init (empty) |
| `ingestion/extractors/__init__.py` | Package init (empty) |
| `ingestion/transformers/__init__.py` | Package init (empty) |
| `ingestion/embedders/__init__.py` | Package init (empty) |
| `ingestion/loaders/__init__.py` | Package init (empty) |
| `tests/__init__.py` | Package init (empty) |

---

## Statistics

| Metric | Value |
|--------|------:|
| **New Python files** | 14 |
| **Total lines of code** | ~1,600 |
| **Classes defined** | 11 |
| **Enums defined** | 3 |
| **Dataclasses defined** | 3 |
| **Test functions** | 10 |
| **External APIs consumed** | 3 (Jolpica, Wikipedia, Ollama) |
| **Database tables used** | 2 (`documents`, `chunks`) |

---

## Expected Data Volume

| Source | Est. Raw Documents | Est. Chunks |
|--------|--------------------|-------------|
| Jolpica — race results | ~1,100 | ~3,500 |
| Jolpica — qualifying | ~1,100 | ~3,500 |
| Jolpica — standings | ~150 | ~500 |
| Jolpica — drivers | ~850 | ~900 |
| Jolpica — constructors | ~210 | ~220 |
| Wikipedia articles | ~58 articles x ~8 sections | ~1,200 |
| **Total** | **~3,400+ documents** | **~9,800 chunks** |

Estimated full ingestion time: **30–45 minutes** at 32 chunks/batch with local
Ollama.

---

## How to Run

```bash
# 1. Start infrastructure
docker compose up -d

# 2. Pull the embedding model (first time only)
docker compose exec ollama ollama pull nomic-embed-text

# 3. Verify all services
uv run python -m ingestion.healthcheck

# 4. Run full static ingestion
uv run python -m ingestion.pipeline --phase static

# 5. Run tests
uv run pytest tests/ -v
```

---

## Completion Criteria Status

- [x] PostgreSQL + pgvector running via Docker
- [x] Ollama running `nomic-embed-text` locally
- [x] Full Jolpica race data (1950-2024) ingestion implemented
- [x] Key Wikipedia articles (drivers, teams, circuits, topics) ingestion implemented
- [x] CLI script that can re-run ingestion idempotently (fingerprint-based dedup)
- [x] All 10 tests passing
