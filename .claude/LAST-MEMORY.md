# Last Session Memory — F1 Chatbot

**Last updated:** 2026-04-04
**Session scope:** Phase 3 — Bug fixes, Gemini integration, Docker fixes, new tests

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
- **Phase 3** (DONE): FastAPI RAG agent + query routing + Gemini LLM

**All three phases are complete and committed on `main`.**

---

## Current Architecture

```
User question
     │
     ▼
FastAPI POST /chat  /  GET /chat/stream  /  GET /health
     │
     ▼
Router (Gemini 2.5 Flash) → HISTORICAL / CURRENT / MIXED
     │
     ├── HISTORICAL/MIXED → Retriever (hybrid pgvector + full-text, RRF merge)
     └── CURRENT/MIXED    → get_current_standings() tool (OpenF1 API)
     │
     ▼
Gemini 2.5 Flash (answer generation, SSE streaming)
     │
     ▼
StreamingResponse (SSE) or ChatResponse JSON
```

**LLM split:**
- **Ollama** (Docker): embeddings only — `nomic-embed-text` (768-dim)
- **Gemini 2.5 Flash** (Google API): all LLM inference — routing + answer generation

---

## Key Files

### Agent Layer — `agent/`

| File | Purpose |
|------|---------|
| `agent/llm.py` | Gemini API client — `generate()` + `stream()`, SSE, retry on 429 |
| `agent/prompts.py` | `ROUTER_SYSTEM`, `ROUTER_PROMPT`, `SYSTEM_INSTRUCTION`, `ANSWER_PROMPT` |
| `agent/router.py` | Intent classifier via `gemini.generate()` — HISTORICAL/CURRENT/MIXED |
| `agent/retriever.py` | Hybrid dense (pgvector) + sparse (pg full-text) retriever, RRF merge |
| `agent/tools.py` | `get_current_standings()`, `get_race_results()`, `get_driver_stats()` |
| `agent/agent.py` | Core reasoning loop — routes, retrieves, streams via `gemini.stream()` |

### API Layer — `api/`

| File | Purpose |
|------|---------|
| `api/main.py` | FastAPI app, lifespan (Agent + Scheduler), CORS |
| `api/schemas.py` | `ChatRequest` / `ChatResponse` / `Source` Pydantic models |
| `api/routes/chat.py` | `POST /chat` (JSON) + `GET /chat/stream` (SSE), try/except for 500s |
| `api/routes/health.py` | `GET /health` — postgres + ollama status + chunk counts |

### Tests — 51 total, all passing

| File | Tests |
|------|------:|
| `tests/test_agent.py` | 11 |
| `tests/test_api.py` | 8 (new this session) |
| `tests/test_tools.py` | 9 (new this session) |
| `tests/test_extractors.py` | 10 |
| `tests/test_pipeline.py` | 6 |
| `tests/test_scheduler.py` | 7 |

---

## Important Technical Notes

### Database
- **Port:** PostgreSQL is on port **5433** on the host (maps to 5432 in container)
- **Embedding dimensions:** 768 (nomic-embed-text) — must match `vector(768)` in schema
- **4 tables:** `documents`, `chunks`, `sync_state`, `job_runs`
- **15,745 static chunks, 1,847 live chunks** in DB (as of this session)

### Gemini
- **Model:** `gemini-2.5-flash` (free tier: 10 RPM, 500 req/day)
- **`gemini-1.5-flash`** and **`gemini-2.0-flash`** not available on this API key's free tier
- **Retry logic:** 3 attempts, exponential backoff 5s → 10s → 20s on 429
- **Streaming URL:** must include `?alt=sse` — without it Gemini returns a JSON array, not SSE lines
- **API key** in `.env` as `GEMINI_API_KEY`

### Docker
- **Critical:** API container needs `environment:` block in docker-compose to override `.env`'s `localhost` URLs with Docker service hostnames (`postgres:5432`, `ollama:11434`) — without this the API can't reach either service
- **Ollama healthcheck:** uses `["CMD", "ollama", "list"]` — the image has no `curl`
- **Dockerfile:** needs `gcc` + `python3-dev` (aiohttp compiles from source on ARM64); two-stage `uv sync` (first `--no-install-project` for dep caching, then full sync after `COPY . .`)
- **Ollama in Docker is CPU-only** on macOS (no Metal GPU access) — models ≥3B are too slow; embeddings are fast enough since they're small

### Retriever SQL fix
- `CAST(:emb AS vector)` — NOT `:emb::vector` (PostgreSQL cast syntax conflicts with SQLAlchemy named params in asyncpg)

### Prompts
- Use `.replace("{key}", value)` — NOT `str.format()` — chunk content can contain `{...}` causing KeyError
- Router prompt includes current year ("The current year is 2026") so past seasons are correctly classified as HISTORICAL

### Dev deps
- `uv sync` alone does NOT install pytest — must use `uv sync --extra dev`

---

## Environment Variables (`.env`)

```
DATABASE_URL=postgresql+asyncpg://f1:f1secret@localhost:5433/f1kb
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
GEMINI_API_KEY=<key>
GEMINI_MODEL=gemini-2.5-flash
```

Docker compose overrides `DATABASE_URL` and `OLLAMA_BASE_URL` with service hostnames.

---

## Git State

- **Branch:** `main`
- **Recent commits:**
  - `feat: switch LLM inference to Gemini, fix Docker networking and retriever`
  - `32b3295` Merge pull request #1 from RChaubey16/feature/phase-3

---

## How to Resume

```bash
# Start services
docker compose up -d

# Pull Ollama embedding model (first time / after volume wipe)
docker compose exec ollama ollama pull nomic-embed-text

# Verify
curl http://localhost:8000/health

# Run ingestion (if DB is empty)
uv run python -m ingestion.pipeline --phase static
uv run python -m ingestion.pipeline --phase live

# Test a query
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Who won the 2024 championship?"}'

# Run tests
uv sync --extra dev
uv run python -m pytest tests/ -v
```

---

## What Remains (Optional / Future)

- Weekly `prune_live_partition()` job wired into scheduler
- Frontend / chat UI
- `/health` endpoint Gemini status check
- Rate limit handling improvements (queue, per-user throttle)
