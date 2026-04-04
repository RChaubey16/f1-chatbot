# Last Session Memory — F1 Chatbot

**Last updated:** 2026-04-04
**Session scope:** Phase 3 — FastAPI RAG Agent (complete)

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
- **Phase 3** (DONE): FastAPI RAG agent + query routing

**All three phases are complete and committed on `feature/phase-3`.**

---

## Phase 3 — What Was Built

### Architecture

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
         │         ┌──────────▼──────────┐
         │         │  Tools              │
         │         │  get_current_       │
         │         │  standings()        │
         │         └──────────┬──────────┘
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

### Files Created

#### Agent Layer — `agent/`

| File | Purpose |
|------|---------|
| `agent/prompts.py` | `ROUTER_PROMPT` and `SYSTEM_PROMPT` templates |
| `agent/router.py` | Query intent classifier (HISTORICAL/CURRENT/MIXED) via Ollama LLM |
| `agent/retriever.py` | Hybrid dense (pgvector) + sparse (pg full-text) retriever with RRF merge |
| `agent/tools.py` | 3 structured lookup tools for live/structured data |
| `agent/agent.py` | Core reasoning loop — routes, retrieves, streams |

#### API Layer — `api/`

| File | Purpose |
|------|---------|
| `api/main.py` | FastAPI app, lifespan, CORS |
| `api/schemas.py` | `ChatRequest` / `ChatResponse` Pydantic models |
| `api/routes/chat.py` | `POST /chat` (JSON) + `GET /chat/stream` (SSE) |
| `api/routes/health.py` | `GET /health` |

#### Tests — `tests/test_agent.py` (7 tests)

| Test | What it covers |
|------|---------------|
| `test_retriever_rrf_merge` | RRF score merging logic |
| `test_router_classifies_historical` | Router returns HISTORICAL intent |
| `test_router_classifies_current` | Router returns CURRENT intent |
| `test_router_defaults_to_mixed_on_unknown` | Router falls back to MIXED |
| `test_agent_historical_uses_static_partition` | Agent queries static KB only |
| `test_agent_current_skips_retriever` | Agent uses tools, skips RAG retriever |
| `test_agent_mixed_uses_both_partitions` | Agent uses both retriever + tools |

---

## Test Results

**30 tests, all passing.**

| File | Tests | Status |
|------|------:|--------|
| `tests/test_agent.py` | 7 | ✅ All pass |
| `tests/test_extractors.py` | 10 | ✅ All pass |
| `tests/test_pipeline.py` | 6 | ✅ All pass |
| `tests/test_scheduler.py` | 7 | ✅ All pass |

Run: `/home/ruturaj-hp/.local/bin/uv sync --extra dev && /home/ruturaj-hp/.local/bin/uv run python -m pytest tests/ -v`

---

## Important Technical Notes

- **Port:** PostgreSQL is on port **5433** (not default 5432) in docker-compose and `.env` `DATABASE_URL`
- **Python version:** >=3.13 (pinned in pyproject.toml)
- **Embedding dimensions:** 768 (nomic-embed-text) — must match `vector(768)` in schema
- **LLM for chat:** `mistral` via Ollama
- **LLM for routing:** same Ollama instance, `ROUTER_PROMPT` elicits one-word response
- **Qualifying data:** Only available from 1994 onwards — Jolpica extractor skips earlier years
- **Deduplication:**
  - Static/structured data: fingerprint = `xxhash.xxh64` of `raw_content`
  - News articles: URL stored in `metadata->>'url'`, checked via `loader.url_exists()`
- **Index rebuild:** IVFFlat index is dropped and recreated after static ingestion only (not live runs)
- **uv dev deps:** `uv sync` alone does NOT install pytest. Must use `uv sync --extra dev`
- **Async generator mocking:** Use `MagicMock(side_effect=fn)` not `AsyncMock(return_value=...)` for async generators
- **Wikipedia User-Agent:** Wikipedia API returns 403 without a proper `User-Agent` header
- **Dependencies:** All locked in `uv.lock`, install with `uv sync --extra dev`

---

## Database Tables

| Table | Used Since | Purpose |
|-------|-----------|---------|
| `documents` | Phase 1 | One row per raw document, dedup via fingerprint |
| `chunks` | Phase 1 | Text chunks with 768-dim embeddings |
| `sync_state` | Phase 2 | `last_synced_at` per source for incremental sync |
| `job_runs` | Phase 2 | Audit log — one row per scheduler job execution |

---

## Git State

- **Branch:** `feature/phase-3`
- **Worktree:** `/home/ruturaj-hp/projects/f1-chatbot/.worktrees/phase-3`
- **Recent commits:**
  - `f7945b4` docs: add Phase-3-summary.md
  - `c93618e` feat: phase 3 — FastAPI RAG agent with hybrid search and streaming
  - `f6a3476` feat: add phase 3 stubs and worktree gitignore
  - `886a5c4` chore: update sessions count to match the on-going season
  - `d5e0e21` chore: increase intervals between API calls to OpenF1 to avoid rate limits

---

## How to Resume

```bash
# Start services
docker compose up -d
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull mistral

# Verify
uv run python -m ingestion.healthcheck

# Run ingestion (if not done yet)
uv run python -m ingestion.pipeline --phase static
uv run python -m ingestion.pipeline --phase live

# Start background scheduler
uv run python -m ingestion.scheduler

# Start the API server
uv run uvicorn api.main:app --reload

# Run tests
/home/ruturaj-hp/.local/bin/uv sync --extra dev
/home/ruturaj-hp/.local/bin/uv run python -m pytest tests/ -v
```

---

## What Remains (Optional / Future)

- Weekly `prune_live_partition()` job wired into scheduler
- `Dockerfile` for containerised API deployment
- Frontend / chat UI
- Merge `feature/phase-3` into `main`
