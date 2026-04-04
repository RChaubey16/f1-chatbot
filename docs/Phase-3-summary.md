# Phase 3 Summary — FastAPI RAG Agent + Query Routing

## Overview

Phase 3 builds the reasoning layer on top of the knowledge base: a FastAPI
service that accepts a user question, classifies its intent, retrieves grounded
context via hybrid search, and streams an answer from a local Ollama LLM.
Phase 1 and 2 components (retriever, scheduler, embedder, loader) are reused
without modification.

---

## Architecture

```
User question
     │
     ▼
┌─────────────────────────────────┐
│   FastAPI  POST /chat           │
│           GET  /chat/stream     │
│           GET  /health          │
└──────────────┬──────────────────┘
               │
               ▼
      ┌─────────────────┐
      │     Router      │  Classifies intent via Ollama LLM
      └────────┬────────┘
               │
     ┌─────────┼──────────────┐
     │         │              │
HISTORICAL   MIXED        CURRENT
     │         │              │
     ▼         ▼              │
┌──────────────────┐          │
│    Retriever     │          │
│  Hybrid search   │          │
│  pgvector dense  │          │
│  + pg full-text  │          │
│  merged via RRF  │          │
└────────┬─────────┘          │
         │                    │
         │         ┌──────────▼──────────┐
         │         │  Tools              │
         │         │  get_current_       │
         │         │  standings()        │
         │         └──────────┬──────────┘
         │                    │
         └─────────┬──────────┘
                   │ context string
                   ▼
         ┌─────────────────────┐
         │   Ollama LLM        │
         │   (mistral)         │
         │   SYSTEM_PROMPT     │
         │   + context         │
         └─────────┬───────────┘
                   │ streamed tokens
                   ▼
         ┌─────────────────────┐
         │  StreamingResponse  │
         │  (SSE)  or          │
         │  ChatResponse JSON  │
         └─────────────────────┘
```

---

## Files Created

### Agent Layer — `agent/`

| File | Lines | Purpose |
|------|------:|---------|
| `prompts.py` | ~24 | `ROUTER_PROMPT` and `SYSTEM_PROMPT` templates |
| `router.py` | ~80 | Query intent classifier via Ollama LLM |
| `retriever.py` | ~149 | Hybrid dense + sparse retriever with RRF merge |
| `tools.py` | ~90 | 3 structured lookup tools for live/structured data |
| `agent.py` | ~185 | Core reasoning loop — routes, retrieves, streams |

#### `agent/prompts.py`

Two prompt templates used across the agent:

- **`ROUTER_PROMPT`** — instructs the LLM to classify a query into exactly one
  of `HISTORICAL`, `CURRENT`, or `MIXED`. One-word response only.
- **`SYSTEM_PROMPT`** — instructs the LLM to answer using only the provided
  context and cite sources. Has a `{context}` placeholder filled at runtime.

#### `agent/router.py`

`Router` classifies the user's query intent before retrieval so the agent uses
the most appropriate data source.

**Three intent classes:**

| Class | Examples | Strategy |
|---|---|---|
| `HISTORICAL` | "Who won the 1988 championship?" | Hybrid RAG over static KB only |
| `CURRENT` | "What are the standings today?" | Live API tool call |
| `MIXED` | "How does Hamilton compare to Schumacher?" | RAG over both partitions + standings |

**Classification approach:**
- POSTs to Ollama `/api/generate` with `stream: false`
- Uses `settings.llm_model` (default: `mistral`)
- Parses the `response` field, uppercases, maps to `Intent` enum
- Defaults to `Intent.MIXED` on any unexpected value or HTTP error
- Logs a warning and returns `MIXED` on empty LLM response

**Key implementation details:**
- Empty-response guard before `Intent(raw)` to avoid misleading `ValueError`
- Exception catch narrowed to `(ValueError, httpx.HTTPError)` — does not swallow
  programming errors
- `health_check()` verifies `llm_model` is present in Ollama's model list
- Supports `async with Router() as r:` via `__aenter__`/`__aexit__`

#### `agent/retriever.py`

`Retriever` combines two search signals and merges them via Reciprocal Rank
Fusion (RRF).

**Dense retrieval (pgvector cosine similarity):**
```sql
SELECT chunk_id, content, source, content_type, partition, metadata,
       1 - (embedding <=> :emb::vector) AS similarity
FROM chunks
WHERE partition = ANY(:parts) AND embedding IS NOT NULL
ORDER BY embedding <=> :emb::vector
LIMIT :lim
```

**Sparse retrieval (PostgreSQL full-text):**
```sql
SELECT chunk_id, content, source, content_type, partition, metadata,
       ts_rank(content_tsv, plainto_tsquery('english', :q)) AS rank
FROM chunks
WHERE content_tsv @@ plainto_tsquery('english', :q)
  AND partition = ANY(:parts)
ORDER BY rank DESC
LIMIT :lim
```

**RRF merge:**
```python
score[chunk_id] += 1 / (k + rank + 1)   # k=60
```
Chunks appearing in both lists get additive score boosts. The merged, sorted list
is truncated to `top_k` (default 6).

**Interface:**
```python
async def retrieve(
    query: str,
    partitions: list[str] = ["static", "live"],
    top_k: int = 6,
) -> list[RetrievedChunk]
```

#### `agent/tools.py`

Three async functions the agent calls for structured lookups, bypassing vector
search entirely:

**`get_current_standings() -> str`**
- GETs `https://api.openf1.org/v1/position?session_key=latest`
- Returns numbered list: `"1. Driver #44 — P1\n2. Driver #1 — P2\n..."`
- Graceful fallback: `"Current standings unavailable."`

**`get_race_results(year: int, gp: str) -> str`**
- GETs `https://api.jolpi.ca/ergast/f1/{year}/results.json?limit=100`
- Filters races where `gp` (lowercased) appears in race name, circuit ID, or locality
- Returns top-3 finishers: `"Results for 2019 Monaco:\n1. Hamilton (Mercedes)\n..."`
- Graceful fallback on HTTP error or no match

**`get_driver_stats(driver_name: str) -> str`**
```sql
SELECT content FROM chunks
WHERE content_type = 'driver_profile'
  AND metadata->>'name' ILIKE '%{driver_name}%'
LIMIT 1
```
- Returns the full driver profile text chunk
- Graceful fallback: `"No stats found for {driver_name}."`
- Creates and disposes engine within the function call

#### `agent/agent.py`

`Agent` is the core reasoning loop. It orchestrates routing, retrieval, tool
calls, prompt construction, and LLM streaming.

**`_prepare_context(query, top_k=6) -> (Intent, list[RetrievedChunk], str)`**

Shared by both `run()` and `run_sync()`:
1. Classifies intent via `Router.classify(query)`
2. Retrieves chunks based on intent:
   - `HISTORICAL` → `partitions=["static"]`
   - `MIXED` → `partitions=["static", "live"]`
   - `CURRENT` → no retrieval
3. Calls `get_current_standings()` for `CURRENT` or `MIXED` intent
4. Builds context string, truncated to `_MAX_CONTEXT_CHARS = 12_000` characters
5. Returns `(intent, chunks, context_str)`

**`async run(query) -> AsyncGenerator[str, None]`** (streaming)

Builds the prompt from `SYSTEM_PROMPT.format(context=context_str)` then streams
from Ollama `/api/generate` with `"stream": true`. Yields each `response` token
until `"done": true`. Skips empty lines and handles malformed JSON gracefully.

**`async run_sync(query, max_chunks=6) -> dict`**

Calls `_prepare_context(query, top_k=max_chunks)` then collects the full
streamed answer. Returns:
```python
{
    "answer": str,
    "sources": [{"content_type": ..., "source": ..., "metadata": ...}],
    "intent": str,       # Intent.value
    "latency_ms": float  # end-to-end wall time
}
```

**Resource management:**
- `close()` awaits `router.close()` and `retriever.close()`
- `__aenter__`/`__aexit__` for `async with Agent() as agent:` usage

---

### API Layer — `api/`

| File | Lines | Purpose |
|------|------:|---------|
| `schemas.py` | ~20 | Pydantic request/response models |
| `routes/chat.py` | ~35 | POST /chat + GET /chat/stream endpoints |
| `routes/health.py` | ~75 | GET /health — infra status check |
| `main.py` | ~45 | FastAPI app with lifespan + scheduler integration |

#### `api/schemas.py`

Pydantic v2 models:

```python
class ChatRequest(BaseModel):
    query: str
    max_chunks: int = 6

class Source(BaseModel):
    content_type: str
    source: str
    metadata: dict

class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    intent: str
    latency_ms: float
```

#### `api/routes/chat.py`

**`POST /chat`**
```
Body:     { "query": "...", "max_chunks": 6 }
Response: { "answer": "...", "sources": [...], "intent": "HISTORICAL", "latency_ms": 1234.5 }
```
Calls `agent.run_sync(body.query, max_chunks=body.max_chunks)`.
Agent is read from `request.app.state.agent` — no per-request instantiation.

**`GET /chat/stream?query=...`**
```
Response: text/event-stream
data: {"token": "Lewis"}
data: {"token": " Hamilton"}
data: [DONE]
```
Returns `StreamingResponse` wrapping an async generator that iterates
`agent.run(query)` and yields SSE-formatted events.

#### `api/routes/health.py`

**`GET /health`**
```json
{
  "status": "ok",
  "postgres": "ok",
  "ollama": "ok",
  "chunks_static": 9800,
  "chunks_live": 1200,
  "last_live_refresh": "2024-03-25T10:00:00Z"
}
```

- **postgres**: runs `SELECT COUNT(*) FROM chunks WHERE partition=...` for both
  partitions. Engine is created per-request and disposed in a `finally` block to
  prevent connection pool leaks even when SQL queries raise.
- **ollama**: calls `OllamaEmbedder().health_check()`, client closed in `finally`.
- **last_live_refresh**: queries `sync_state WHERE source='openf1'`.
- **status**: `"ok"` only if both postgres and ollama are `"ok"`.
- Never raises HTTP 500 — all infra failures return `"error"` in their field.

#### `api/main.py`

FastAPI app using the modern `lifespan` context manager (not deprecated
`on_event` hooks):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = Agent()
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    try:
        app.state.scheduler.shutdown(wait=False)
    except Exception:
        log.warning("Scheduler was not running on shutdown")
    await app.state.agent.close()
```

Includes both routers: `chat_router.router` and `health_router.router`.

---

### Infrastructure

#### `Dockerfile`

```dockerfile
FROM python:3.13-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY . .
CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Uses `python:3.13-slim` to match `requires-python = ">=3.13"` in `pyproject.toml`.

#### `docker-compose.yml` — api service added

```yaml
api:
  build: .
  env_file: .env
  ports:
    - "8000:8000"
  depends_on:
    postgres:
      condition: service_healthy
    ollama:
      condition: service_healthy
  command: uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

---

## Files Modified

### `ingestion/core/config.py`

Added one new setting:

```python
# Agent LLM (Phase 3)
llm_model: str = "mistral"
```

Used by `Router` and `Agent` for Ollama chat generation. Configurable via `LLM_MODEL` env var.

---

## Tests

| File | Tests added | Total tests |
|------|------------:|------------:|
| `tests/test_agent.py` | +6 | 7 |
| **Cumulative total** | | **30** |

### Agent tests (`test_agent.py`)

**Pre-existing (from stubs):**
- **`test_retriever_rrf_merge`** — pure Python, no I/O. Verifies chunks
  appearing in both dense and sparse results get higher RRF scores than
  single-list chunks.

**Router tests (3 new):**
- **`test_router_classifies_historical`** — mocks Ollama via `respx` to return
  `"HISTORICAL"`; asserts `classify()` returns `Intent.HISTORICAL`
- **`test_router_classifies_current`** — mocks return `"CURRENT"`
- **`test_router_defaults_to_mixed_on_unknown`** — mocks return `"BLAH"`;
  asserts fallback to `Intent.MIXED`

**Agent intent routing tests (3 new):**
- **`test_agent_historical_uses_static_partition`** — mocks `router.classify`
  to return `HISTORICAL` and patches `httpx.AsyncClient` for Ollama streaming;
  asserts `retriever.retrieve` was called with `partitions=["static"]`
- **`test_agent_current_skips_retriever`** — mocks `CURRENT` intent; asserts
  `retriever.retrieve` was never called and `get_current_standings` was awaited
- **`test_agent_mixed_uses_both_partitions`** — mocks `MIXED` intent; asserts
  `retriever.retrieve` called with `partitions=["static", "live"]`

**All 30 tests pass.**

---

## Database Tables Used (Phase 3)

No new tables. Phase 3 reads from all four existing tables:

| Table | Phase 3 usage |
|-------|--------------|
| `chunks` | Dense + sparse search via `Retriever`; chunk counts in `/health` |
| `documents` | Indirectly via chunk metadata |
| `sync_state` | `last_live_refresh` timestamp read by `/health` |
| `job_runs` | No direct usage (written by Phase 2 scheduler, still running) |

---

## Performance Targets

| Metric | Target |
|---|---|
| Non-streaming response | < 5s end-to-end |
| First token (streaming) | < 2s |
| Vector search (top-6) | < 200ms |
| Router classification | < 1s |

Local Ollama on CPU is the bottleneck for generation. Use `mistral:7b-instruct-q4_K_M`
(quantised) for faster CPU inference if latency is too high.

---

## How to Run

```bash
# 1. Start all services (postgres + ollama + api)
docker compose up -d

# 2. Pull models (first time only)
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull mistral

# 3. Run ingestion (if not done yet)
uv run python -m ingestion.pipeline --phase static
uv run python -m ingestion.pipeline --phase live

# 4. Check health
curl http://localhost:8000/health

# 5. Non-streaming query
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Who won the 1988 championship?"}'

# 6. Streaming query
curl -N "http://localhost:8000/chat/stream?query=What+are+the+current+standings"

# 7. Run tests
uv sync --extra dev
uv run python -m pytest tests/ -v
```

---

## Completion Criteria Status

- [x] FastAPI app starts cleanly via `docker compose up`
- [x] `GET /health` returns status for postgres, ollama, and chunk counts
- [x] `POST /chat` with a historical query returns a grounded answer with sources
- [x] `POST /chat` with a current-standings query routes to live tool (not RAG)
- [x] `GET /chat/stream` streams SSE tokens correctly
- [x] Router correctly classifies HISTORICAL / CURRENT / MIXED
- [x] All 30 tests pass (30 total: 7 agent + 10 extractor + 6 pipeline + 7 scheduler)
