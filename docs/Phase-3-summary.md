# Phase 3 Summary — FastAPI RAG Agent + Query Routing

## Overview

Phase 3 builds the reasoning layer on top of the knowledge base: a FastAPI
service that accepts a user question, classifies its intent, retrieves grounded
context via hybrid search, and streams an answer from Gemini 2.5 Flash.
Phase 1 and 2 components (retriever, scheduler, embedder, loader) are reused
without modification.

**LLM split:** Ollama runs inside Docker for embeddings only
(`nomic-embed-text`). All LLM inference (routing + answer generation) uses the
Gemini API so responses are fast (~5s) regardless of local hardware.

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
      │     Router      │  Classifies intent via Gemini API
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
         │   Gemini 2.5 Flash  │
         │   (Google API)      │
         │   SYSTEM_INSTRUCTION│
         │   + ANSWER_PROMPT   │
         └─────────┬───────────┘
                   │ streamed tokens (SSE)
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

| File | Purpose |
|------|---------|
| `prompts.py` | `ROUTER_SYSTEM`, `ROUTER_PROMPT`, `SYSTEM_INSTRUCTION`, `ANSWER_PROMPT` |
| `router.py` | Query intent classifier via Gemini API |
| `retriever.py` | Hybrid dense + sparse retriever with RRF merge |
| `tools.py` | 3 structured lookup tools for live/structured data |
| `agent.py` | Core reasoning loop — routes, retrieves, streams |
| `llm.py` | Thin Gemini API client (generate + SSE stream, retry on 429) |

#### `agent/llm.py`

Wraps the Gemini REST API using `httpx` (no extra SDK dependency).

```python
async def generate(system: str, prompt: str) -> str: ...
async def stream(system: str, prompt: str) -> AsyncGenerator[str, None]: ...
```

- `generate` — single blocking call, used by the router for classification
- `stream` — SSE streaming via `streamGenerateContent?alt=sse`, used by the agent for answer generation
- Both functions retry up to 3 times with exponential backoff (5s → 10s → 20s) on HTTP 429 rate-limit responses
- URL built from `settings.gemini_model` and `settings.gemini_api_key`

#### `agent/prompts.py`

Four constants used across the agent:

- **`ROUTER_SYSTEM`** — system instruction telling Gemini to respond with exactly one word
- **`ROUTER_PROMPT`** — user turn with the query and classification rules; includes the current year (2026) so past seasons are correctly classified as HISTORICAL
- **`SYSTEM_INSTRUCTION`** — system instruction for answer generation: use only the provided context, be concise, cite sources
- **`ANSWER_PROMPT`** — user turn with `{question}` and `{context}` placeholders; question is placed before context so the model knows what to look for

Placeholders are filled with `.replace("{key}", value)` (not `str.format()`) to prevent `KeyError` if chunk content contains `{...}`.

#### `agent/router.py`

`Router` classifies the user's query intent before retrieval.

**Three intent classes:**

| Class | Examples | Strategy |
|---|---|---|
| `HISTORICAL` | "Who won the 1988 championship?" | Hybrid RAG over static KB only |
| `CURRENT` | "What are the 2026 standings?" | Live API tool call only |
| `MIXED` | "How does Hamilton compare to Schumacher?" | RAG over both partitions + standings |

**Classification approach:**
- Calls `agent.llm.generate(ROUTER_SYSTEM, ROUTER_PROMPT)` via Gemini
- Strips punctuation from the first word of the response, uppercases, maps to `Intent` enum
- Defaults to `Intent.MIXED` on any unexpected value or exception (never crashes the request)

#### `agent/retriever.py`

`Retriever` combines two search signals and merges them via Reciprocal Rank Fusion (RRF).

**Dense retrieval (pgvector cosine similarity):**
```sql
SELECT chunk_id, content, source, content_type, partition, metadata,
       1 - (embedding <=> CAST(:emb AS vector)) AS similarity
FROM chunks
WHERE partition = ANY(:parts) AND embedding IS NOT NULL
ORDER BY embedding <=> CAST(:emb AS vector)
LIMIT :lim
```
Note: `CAST(:emb AS vector)` is used instead of `:emb::vector` to avoid a
PostgreSQL syntax error caused by asyncpg interpreting `::` as part of the
named parameter.

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

#### `agent/tools.py`

Three async functions for structured lookups, bypassing vector search entirely:

**`get_current_standings() -> str`**
- GETs `https://api.openf1.org/v1/position?session_key=latest`
- Returns numbered list: `"1. Driver #44 — P1\n2. Driver #1 — P2\n..."`
- Graceful fallback: `"Current standings unavailable."`

**`get_race_results(year: int, gp: str) -> str`**
- GETs `https://api.jolpi.ca/ergast/f1/{year}/results.json?limit=100`
- Filters races where `gp` appears in race name, circuit ID, or locality
- Returns top-3 finishers; graceful fallback on error or no match

**`get_driver_stats(driver_name: str) -> str`**
- Queries `chunks` table for `content_type = 'driver_profile'` matching the name
- Returns the full driver profile text chunk; graceful fallback if not found

#### `agent/agent.py`

`Agent` orchestrates routing, retrieval, tool calls, and LLM streaming via Gemini.

**`_prepare_context(query, top_k=6) -> (Intent, list[RetrievedChunk], str)`**

1. Classifies intent via `Router.classify(query)`
2. Retrieves chunks based on intent:
   - `HISTORICAL` → `partitions=["static"]`
   - `MIXED` → `partitions=["static", "live"]`
   - `CURRENT` → no retrieval
3. Calls `get_current_standings()` for `CURRENT` or `MIXED` intent
4. Builds context string, truncated to `_MAX_CONTEXT_CHARS = 12_000` characters

**`async run(query) -> AsyncGenerator[str, None]`** (streaming)

Builds prompt, calls `gemini.stream(SYSTEM_INSTRUCTION, prompt)`, yields tokens.

**`async run_sync(query, max_chunks=6) -> dict`**

Collects the full streamed answer and returns:
```python
{
    "answer": str,
    "sources": [{"content_type": ..., "source": ..., "metadata": ...}],
    "intent": str,
    "latency_ms": float
}
```

---

### API Layer — `api/`

| File | Purpose |
|------|---------|
| `schemas.py` | Pydantic request/response models |
| `routes/chat.py` | POST /chat + GET /chat/stream endpoints |
| `routes/health.py` | GET /health — infra status check |
| `main.py` | FastAPI app with lifespan + scheduler integration |

#### `api/routes/chat.py`

**`POST /chat`**
```
Body:     { "query": "...", "max_chunks": 6 }
Response: { "answer": "...", "sources": [...], "intent": "HISTORICAL", "latency_ms": 1234.5 }
```
Wrapped in try/except — exceptions surface as `{"detail": "..."}` with HTTP 500
rather than a generic "Internal Server Error" with no body.

**`GET /chat/stream?query=...`**
```
Response: text/event-stream
data: {"token": "Max"}
data: {"token": " Verstappen"}
data: [DONE]
```

#### `api/routes/health.py`

**`GET /health`**
```json
{
  "status": "ok",
  "postgres": "ok",
  "ollama": "ok",
  "chunks_static": 15745,
  "chunks_live": 1847,
  "last_live_refresh": null
}
```
Checks postgres (chunk counts) and Ollama (embedding model health). Note: health
does not check the Gemini API — Gemini errors surface at query time with a 500.

---

### Infrastructure

#### `Dockerfile`

```dockerfile
FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Key decisions:
- `gcc` + `python3-dev` required: `aiohttp` has no pre-built wheel for `linux/aarch64` + Python 3.13 and must compile from source
- Two-stage `uv sync`: first stage installs dependencies (layer cached), second stage (after `COPY . .`) installs the project itself so `hatchling` can find `README.md`

#### `docker-compose.yml`

```yaml
services:
  postgres:   # pgvector/pgvector:pg16, port 5433
  ollama:     # ollama/ollama:latest, port 11434 — embeddings only
  api:
    environment:
      DATABASE_URL: postgresql+asyncpg://f1:f1secret@postgres:5432/f1kb
      OLLAMA_BASE_URL: http://ollama:11434
      # GEMINI_API_KEY and GEMINI_MODEL come from .env via env_file
```

The `environment` block overrides the `localhost`-based URLs in `.env` with
Docker service hostnames. Without this the API container cannot reach postgres
or Ollama (localhost inside a container refers to the container itself).

Ollama healthcheck uses `["CMD", "ollama", "list"]` — the `ollama/ollama` image
does not include `curl`.

---

## Files Modified

### `ingestion/core/config.py`

Replaced `llm_model` with Gemini settings:

```python
# Gemini (LLM inference)
gemini_api_key: str = ""
gemini_model: str = "gemini-2.5-flash"
```

`GEMINI_API_KEY` and `GEMINI_MODEL` env vars are picked up automatically via
pydantic-settings.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | `""` | Google AI Studio API key (required) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama for embeddings |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Postgres connection string |

Get a free Gemini API key at https://aistudio.google.com/apikey.

---

## Tests

| File | Tests | Status |
|------|------:|--------|
| `tests/test_agent.py` | 11 | ✅ All pass |
| `tests/test_api.py` | 8 | ✅ All pass |
| `tests/test_tools.py` | 9 | ✅ All pass |
| `tests/test_extractors.py` | 10 | ✅ All pass |
| `tests/test_pipeline.py` | 6 | ✅ All pass |
| `tests/test_scheduler.py` | 7 | ✅ All pass |
| **Total** | **51** | ✅ All pass |

### Agent tests (`test_agent.py`)

- **RRF tests (4)** — pure Python, no I/O: merge, empty dense, empty sparse, both empty
- **Router tests (4)** — mock `agent.router.gemini.generate`: HISTORICAL, CURRENT, unknown label → MIXED, exception → MIXED
- **Agent intent routing tests (3)** — mock `agent.agent.gemini.stream`: static-only retrieval, CURRENT skips retriever, MIXED uses both partitions

### API tests (`test_api.py`)

FastAPI routes tested via `httpx.AsyncClient` with `ASGITransport`. Agent set
directly on `app.state.agent` (lifespan not triggered by ASGITransport).

- POST /chat: happy path, max_chunks passthrough, default max_chunks, missing query → 422
- GET /chat/stream: SSE format, missing query → 422
- GET /health: postgres+ollama ok; postgres error → `status: error`

### Tools tests (`test_tools.py`)

`get_current_standings` and `get_race_results` tested with `respx` mocks:
success, empty data, HTTP error, network error, malformed response, match by name/locality.

---

## How to Run

```bash
# 1. Add your Gemini API key to .env
echo "GEMINI_API_KEY=your_key_here" >> .env

# 2. Start all services
docker compose up -d

# 3. Pull Ollama embedding model (first time only)
docker compose exec ollama ollama pull nomic-embed-text

# 4. Run ingestion (if not done yet)
uv run python -m ingestion.pipeline --phase static
uv run python -m ingestion.pipeline --phase live

# 5. Check health
curl http://localhost:8000/health

# 6. Non-streaming query
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Who won the 2024 championship?"}'

# 7. Streaming query
curl -N "http://localhost:8000/chat/stream?query=What+are+the+current+standings"

# 8. Run tests
uv sync --extra dev
uv run python -m pytest tests/ -v
```

---

## Performance

| Metric | Observed |
|---|---|
| End-to-end (POST /chat) | ~5s |
| Router classification | ~1s |
| Vector search (top-6) | < 200ms |
| Gemini generation | ~3–4s |

Gemini 2.5 Flash free tier: 10 requests/min, 500 requests/day. The client
retries automatically on 429 with exponential backoff (5s → 10s → 20s, max 3
attempts).

---

## Completion Criteria Status

- [x] FastAPI app starts cleanly via `docker compose up`
- [x] `GET /health` returns status for postgres, ollama, and chunk counts
- [x] `POST /chat` with a historical query returns a grounded answer with sources
- [x] `POST /chat` with a current-standings query routes to live tool (not RAG)
- [x] `GET /chat/stream` streams SSE tokens correctly
- [x] Router correctly classifies HISTORICAL / CURRENT / MIXED
- [x] All 51 tests pass
