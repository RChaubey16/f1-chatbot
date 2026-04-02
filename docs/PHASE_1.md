# Phase 1 — Static KB Ingestion (Jolpica + Wikipedia)

## Goal

Bootstrap the static knowledge base with all historical F1 data. By the end of
this phase the system can answer any question about F1 history from 1950 to 2024
by doing a vector similarity search over embedded chunks stored in PostgreSQL.

**Completion criteria:**
- PostgreSQL + pgvector running via Docker
- Ollama running `nomic-embed-text` locally
- Full Jolpica race data (1950–2024) ingested and embedded
- Key Wikipedia articles (drivers, teams, circuits, topics) ingested and embedded
- A CLI script that can re-run ingestion idempotently (duplicate-safe)

---

## Step 1 — Project Scaffold

### 1.1 Init project with `uv`

```bash
uv init f1-chatbot
cd f1-chatbot
uv python pin 3.12
```

### 1.2 `pyproject.toml` dependencies

```toml
[project]
name = "f1-chatbot"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
  "fastapi==0.115.0",
  "uvicorn[standard]==0.30.0",
  "pydantic==2.8.0",
  "pydantic-settings==2.4.0",
  "python-dotenv==1.0.1",
  "httpx==0.27.0",
  "beautifulsoup4==4.12.3",
  "lxml==5.3.0",
  "sqlalchemy[asyncio]==2.0.35",
  "asyncpg==0.31.0",
  "pgvector==0.3.2",
  "langchain-text-splitters==0.3.11",
  "tenacity>=9.0.0",
  "structlog==24.4.0",
  "tqdm==4.66.5",
  "xxhash==3.5.0",
  "wikipedia-api==0.7.1",
]
```

### 1.3 Docker Compose (Phase 1 — Postgres + Ollama only)

```yaml
# docker-compose.yml
version: "3.9"

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: f1
      POSTGRES_PASSWORD: f1secret
      POSTGRES_DB: f1kb
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/schema.sql:/docker-entrypoint-initdb.d/schema.sql

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama

volumes:
  pgdata:
  ollama_models:
```

---

## Step 2 — Database Schema

### File: `db/schema.sql`

This schema runs automatically when the Postgres container starts for the first
time (mounted as an init script).

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Tracks every document we've seen, used for deduplication.
CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL PRIMARY KEY,
    fingerprint  TEXT UNIQUE NOT NULL,       -- xxhash of raw content
    source       TEXT NOT NULL,              -- jolpica | openf1 | wikipedia | news
    content_type TEXT NOT NULL,
    partition    TEXT NOT NULL,              -- static | live
    metadata     JSONB DEFAULT '{}',
    fetched_at   TIMESTAMPTZ DEFAULT NOW(),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks derived from documents, with their embeddings.
CREATE TABLE IF NOT EXISTS chunks (
    id             SERIAL PRIMARY KEY,
    chunk_id       TEXT UNIQUE NOT NULL,     -- "{doc_fingerprint}_{index}"
    doc_fingerprint TEXT NOT NULL REFERENCES documents(fingerprint),
    content        TEXT NOT NULL,
    source         TEXT NOT NULL,
    content_type   TEXT NOT NULL,
    partition      TEXT NOT NULL,
    metadata       JSONB DEFAULT '{}',
    embedding      vector(768),              -- nomic-embed-text = 768 dims
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- IVFFlat index for approximate nearest-neighbour search.
-- Create AFTER bulk ingestion (drop and recreate if re-ingesting).
-- lists = sqrt(total_rows) is a good starting point.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Full-text search index for hybrid BM25-style keyword search (Phase 3).
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX IF NOT EXISTS chunks_content_tsv_idx
    ON chunks USING GIN (content_tsv);
```

---

## Step 3 — Core Layer

### File: `ingestion/core/config.py`

Loads all settings from `.env` using pydantic-settings. All other modules
import from here — no `os.getenv` calls scattered around.

**Key settings to expose:**
- `DATABASE_URL`
- `OLLAMA_BASE_URL`, `EMBEDDING_MODEL`
- `REQUEST_DELAY_SECONDS`, `MAX_RETRIES`
- `CHUNK_SIZE_STRUCTURED` (512), `CHUNK_SIZE_NARRATIVE` (800), `CHUNK_OVERLAP` (80)
- `EMBEDDING_BATCH_SIZE` (32)

### File: `ingestion/core/models.py`

Pydantic models shared across all pipeline stages:

```
RawDocument
  - source: SourceType          # jolpica | wikipedia | openf1 | news
  - content_type: ContentType   # race_result | driver_profile | narrative | ...
  - partition: KBPartition      # static | live
  - raw_content: str
  - metadata: dict
  - fingerprint: str            # property — xxhash of raw_content

Chunk
  - chunk_id: str               # f"{doc_fingerprint}_{index}"
  - doc_fingerprint: str
  - content: str
  - source, content_type, partition, metadata
  - embedding: list[float] | None

IngestionResult
  - docs_fetched, docs_skipped_duplicate
  - chunks_created, chunks_embedded, chunks_upserted
  - errors: list[str]
  - summarise() -> str
```

### File: `ingestion/core/logging.py`

Configure `structlog` with ISO timestamps and console renderer. All extractors
and pipeline stages use `get_logger(__name__)`.

---

## Step 4 — Extractors

### 4.1 Base extractor

### File: `ingestion/extractors/base.py`

Abstract base class with two methods:
- `extract() -> AsyncIterator[RawDocument]` — yields documents one at a time
- `health_check() -> bool`

Yielding one document at a time is important: it lets the pipeline start
chunking and embedding while extraction is still running, rather than waiting
for the full source to be exhausted before doing anything.

---

### 4.2 Jolpica extractor

### File: `ingestion/extractors/jolpica.py`

**What it fetches:**

| Endpoint | RawDocument content_type |
|---|---|
| `/drivers` | `driver_profile` |
| `/constructors` | `constructor_profile` |
| `/{year}/results` | `race_result` |
| `/{year}/qualifying` | `qualifying_result` |
| `/{year}/driverStandings` | `standings` |
| `/{year}/constructorStandings` | `standings` |

**Pagination:** Jolpica returns paginated JSON (`limit` + `offset`). Implement
`_get_all_pages(path)` that loops until `offset >= total`.

**Rate limiting:** `asyncio.sleep(REQUEST_DELAY_SECONDS)` after every request.
Wrap all HTTP calls with `tenacity` retry (3 attempts, exponential backoff).

**Constructor params:**
- `start_year: int = 1950`
- `end_year: int = 2024`
- `include_lap_times: bool = False` (very high volume — off by default)

---

### 4.3 Wikipedia extractor

### File: `ingestion/extractors/wikipedia.py`

**Strategy:** Fetch per-section, not whole articles. Each section becomes its
own `RawDocument`. This gives the chunker semantically coherent units to work
with rather than arbitrary mid-article slices.

**Article lists to maintain as constants at the top of the file:**

```python
DRIVER_ARTICLES = [
    "Michael Schumacher", "Ayrton Senna", "Alain Prost",
    "Lewis Hamilton", "Max Verstappen", "Sebastian Vettel",
    "Fernando Alonso", "Niki Lauda", "Jim Clark",
    "Juan Manuel Fangio", "Jackie Stewart", "Nigel Mansell",
    # ... extend freely
]

CONSTRUCTOR_ARTICLES = [
    "Scuderia Ferrari", "McLaren", "Mercedes AMG Petronas F1 Team",
    "Red Bull Racing", "Williams Racing",
    # ...
]

CIRCUIT_ARTICLES = [
    "Circuit de Monaco", "Silverstone Circuit", "Monza Circuit",
    "Spa-Francorchamps", "Suzuka International Racing Course",
    # ...
]

TOPIC_ARTICLES = [
    "Formula One", "Formula One car", "History of Formula One",
    "Formula One regulations", "DRS (Formula One)",
    # ...
]
```

**Wikipedia API calls:**
1. `action=query&prop=extracts&exintro=true&explaintext=true` — intro section
2. `action=parse&prop=sections` — get section list
3. `action=parse&section={index}&prop=wikitext` — per section text

**Wikitext cleanup** (static method `_clean_wikitext`):
- Strip `{{templates}}`
- Unwrap `[[link|text]]` → `text`
- Remove `<ref>` tags
- Normalise whitespace

**Rate limiting:** 0.2s between section fetches, `REQUEST_DELAY_SECONDS`
between articles.

---

## Step 5 — Transform + Chunk

### File: `ingestion/transformers/chunker.py`

**Key insight:** structured JSON embeds poorly. Convert it to readable prose
before chunking so embeddings capture semantic meaning.

**Source-aware chunking strategy:**

| Source | Pre-processing | Splitter | Chunk size |
|---|---|---|---|
| Jolpica (structured) | `_to_narrative(doc)` converts JSON → prose | `RecursiveCharacterTextSplitter` | 512 / overlap 80 |
| Wikipedia (narrative) | Light cleanup only | `RecursiveCharacterTextSplitter` | 800 / overlap 80 |

**`_to_narrative` converters to implement:**

```
_format_race_result(data, meta)
  → "Race: Monaco Grand Prix 2019\nCircuit: Circuit de Monaco\n
     P1: Lewis Hamilton (Mercedes) — 1:43:28 [25 pts]\n
     P2: Sebastian Vettel (Ferrari) — +2.654s [18 pts]\n..."

_format_qualifying(data, meta)
  → "Qualifying: Monaco Grand Prix 2019\n
     P1: Lewis Hamilton | Q1: 1:12.1 Q2: 1:11.3 Q3: 1:10.166\n..."

_format_driver(data)
  → "Driver: Lewis Hamilton\nNationality: British\nDOB: 1985-01-07\n
     Permanent number: #44"

_format_constructor(data)
  → "Constructor: Mercedes\nNationality: German"

_format_standings(data, meta)
  → "2019 Driver Standings (Final)\n
     1. Lewis Hamilton — 413 pts\n
     2. Valtteri Bottas — 326 pts\n..."
```

**Output:** `chunker.chunk(doc: RawDocument) -> list[Chunk]`

---

## Step 6 — Embedder

### File: `ingestion/embedders/ollama.py`

Calls Ollama's local embedding endpoint:
`POST http://ollama:11434/api/embeddings`

```json
{ "model": "nomic-embed-text", "prompt": "<chunk content>" }
```

**Batch method:** `embed_batch(chunks: list[Chunk]) -> list[Chunk]`
- Process in batches of `EMBEDDING_BATCH_SIZE` (default 32)
- Use `asyncio.gather` for concurrent requests within a batch
- Wrap with tenacity retry
- Return same chunks with `.embedding` populated

**Dimensions:** `nomic-embed-text` produces 768-dim vectors. This must match
the `vector(768)` column in the schema.

---

## Step 7 — Loader (pgvector)

### File: `ingestion/loaders/pgvector.py`

Responsible for upserts into PostgreSQL. Two tables: `documents` and `chunks`.

**Deduplication logic:**
1. Before inserting a document, check `documents` table for `fingerprint`
2. If found → skip document and all its chunks (`docs_skipped_duplicate++`)
3. If not found → insert document, then bulk-upsert its chunks

**Chunk upsert:**
```sql
INSERT INTO chunks (chunk_id, doc_fingerprint, content, source,
                    content_type, partition, metadata, embedding)
VALUES (...)
ON CONFLICT (chunk_id) DO UPDATE
  SET embedding = EXCLUDED.embedding,
      metadata  = EXCLUDED.metadata;
```

**After full ingestion** (called once at end of pipeline run):
```sql
-- Rebuild IVFFlat index with correct list count
DROP INDEX IF EXISTS chunks_embedding_idx;
CREATE INDEX chunks_embedding_idx
  ON chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

---

## Step 8 — Pipeline Orchestrator

### File: `ingestion/pipeline.py`

Ties all stages together. Accept a `--phase` CLI flag (`static` | `live` | `all`).

```python
async def run_static():
    extractors = [JolpicaExtractor(), WikipediaExtractor()]
    for extractor in extractors:
        async for raw_doc in extractor.extract():
            chunks = chunker.chunk(raw_doc)
            chunks = await embedder.embed_batch(chunks)
            result = await loader.upsert(raw_doc, chunks)
            log_progress(result)
```

**Progress reporting:** use `tqdm` for a live progress bar during long runs.
Log `IngestionResult.summarise()` at the end of each source.

**CLI entry point:**
```bash
uv run python -m ingestion.pipeline --phase static
uv run python -m ingestion.pipeline --phase static --start-year 2000  # partial run
```

---

## Step 9 — Health Check Script

### File: `ingestion/healthcheck.py`

Before running ingestion, verify:
- Postgres is reachable and pgvector extension is installed
- Ollama is reachable and `nomic-embed-text` model is available
- Jolpica API responds
- Wikipedia API responds

Exit with clear error messages if any check fails.

```bash
uv run python -m ingestion.healthcheck
```

---

## Expected Data Volume (Phase 1)

| Source | Est. raw documents | Est. chunks |
|---|---|---|
| Jolpica — race results | ~1,100 (races × top 10) | ~3,500 |
| Jolpica — qualifying | ~1,100 | ~3,500 |
| Jolpica — standings | ~150 | ~500 |
| Jolpica — drivers | ~850 | ~900 |
| Jolpica — constructors | ~210 | ~220 |
| Wikipedia articles | ~70 articles × ~8 sections | ~1,200 |
| **Total** | | **~9,800 chunks** |

At 32 chunks/batch and ~0.1s per batch (local Ollama), expect roughly
**30–45 minutes** for a full Phase 1 run.

---

## Testing

### File: `tests/test_extractors.py`

- Mock HTTP responses for Jolpica and Wikipedia
- Assert correct `content_type` and `partition` on output documents
- Assert `fingerprint` changes when content changes (dedup works)

### File: `tests/test_pipeline.py`

- Run pipeline with a small fixture dataset (5 races, 2 wiki articles)
- Assert correct row counts in `documents` and `chunks` tables (use SQLite in tests)
- Assert re-running is idempotent (counts don't change on second run)

---

## Phase 1 Done When

- [ ] `docker compose up postgres ollama` starts cleanly
- [ ] `uv run python -m ingestion.healthcheck` passes all checks
- [ ] `uv run python -m ingestion.pipeline --phase static` runs to completion
- [ ] `SELECT COUNT(*) FROM chunks;` returns ~9,000+ rows
- [ ] Running the pipeline a second time inserts 0 new rows (idempotent)
- [ ] All tests pass
