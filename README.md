# F1 Chatbot

An AI-powered Formula 1 knowledge base and chatbot built with RAG (Retrieval-Augmented Generation). The system ingests historical and live F1 data from multiple sources, generates semantic embeddings locally via Ollama, and stores them in PostgreSQL with pgvector — serving a conversational F1 assistant powered by Gemini 2.5 Flash with a Next.js frontend.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
  - [1. Clone and configure environment](#1-clone-and-configure-environment)
  - [2. Start infrastructure](#2-start-infrastructure)
  - [3. Pull Ollama embedding model](#3-pull-ollama-embedding-model)
  - [4. Install Python dependencies](#4-install-python-dependencies)
  - [5. Verify connectivity](#5-verify-connectivity)
  - [6. Run the ingestion pipeline](#6-run-the-ingestion-pipeline)
  - [7. Start the API server](#7-start-the-api-server)
  - [8. Start the frontend](#8-start-the-frontend)
- [Environment Variables](#environment-variables)
- [Data Sources](#data-sources)
- [Ingestion Pipeline](#ingestion-pipeline)
  - [Extraction](#extraction)
  - [Chunking](#chunking)
  - [Embedding](#embedding)
  - [Storage](#storage)
- [Agent and Retrieval](#agent-and-retrieval)
  - [Intent Router](#intent-router)
  - [Hybrid Retriever](#hybrid-retriever)
  - [LLM (Gemini)](#llm-gemini)
- [API Endpoints](#api-endpoints)
- [Frontend](#frontend)
- [Live Scheduler](#live-scheduler)
- [Database Schema](#database-schema)
- [Running Tests](#running-tests)
- [Development Roadmap](#development-roadmap)

---

## Overview

F1 Chatbot builds a semantic knowledge base covering Formula 1 history from 1950 to 2024, extended with live session data and news. It ingests structured race data (results, qualifying, standings, driver/constructor profiles), live OpenF1 telemetry data, Motorsport.com news, and narrative Wikipedia articles — transforming them into overlapping text chunks, embedding each chunk with a locally-running Ollama model, and indexing the vectors in PostgreSQL for fast similarity search.

At query time a Gemini-powered agent classifies the user's intent, runs hybrid retrieval (dense vector + full-text search with Reciprocal Rank Fusion), and streams a grounded answer back to a Next.js chat UI.

Example questions the chatbot can answer:

- *"Who won the 2008 World Drivers' Championship and by how many points?"*
- *"What were Ayrton Senna's championship years and teams?"*
- *"Who is currently leading the drivers' standings?"*
- *"What happened in the last race?"*

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                           Data Sources                               │
│  Jolpica API · OpenF1 API · Wikipedia · Motorsport.com news          │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Ingestion Pipeline                              │
│                                                                      │
│   Extract  →  Chunk  →  Embed (Ollama)  →  Load (pgvector)          │
│                                                                      │
│   Static (1950–2024): one-shot    Live: APScheduler every 3–6h      │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   PostgreSQL + pgvector                              │
│     documents · chunks · sync_state · job_runs                      │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    FastAPI Agent Layer                               │
│                                                                      │
│  Router (Gemini) → Intent classification (HISTORICAL/CURRENT/MIXED) │
│  Retriever → Dense (pgvector cosine) + Sparse (tsvector) + RRF      │
│  LLM (Gemini 2.5 Flash) → Streaming answer generation               │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Next.js Frontend                                  │
│     Chat UI (streaming) · Live Standings Panel                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language (backend) | Python 3.13 |
| Web framework | FastAPI 0.115 + Uvicorn |
| Database | PostgreSQL 16 + pgvector |
| ORM / async DB | SQLAlchemy 2 (async) + AsyncPG |
| Embeddings | Ollama (`nomic-embed-text`, 768-dim) |
| LLM | Google Gemini 2.5 Flash (API) |
| HTTP clients | HTTPX, aiohttp |
| Text splitting | LangChain Text Splitters |
| Web scraping | BeautifulSoup4 + lxml |
| Wikipedia client | wikipedia-api |
| Job scheduling | APScheduler |
| Retry logic | Tenacity |
| Logging | structlog |
| Fingerprinting | xxhash |
| Containerisation | Docker Compose |
| Testing (backend) | pytest + pytest-asyncio + respx |
| Package manager (backend) | uv |
| Language (frontend) | TypeScript |
| Frontend framework | Next.js 16 + React 19 |
| Styling | Tailwind CSS v4 |
| Component primitives | Base UI + shadcn |
| Testing (frontend) | Vitest + Testing Library |
| Package manager (frontend) | pnpm |

---

## Project Structure

```
f1-chatbot/
├── ingestion/                  # Data ingestion pipeline
│   ├── core/
│   │   ├── config.py           # Pydantic settings from .env
│   │   ├── models.py           # Shared data models (Document, Chunk, enums)
│   │   └── logging.py          # Structured logging setup
│   ├── extractors/
│   │   ├── base.py             # Abstract base extractor
│   │   ├── jolpica.py          # Ergast-compatible F1 API extractor (static)
│   │   ├── wikipedia.py        # Wikipedia article extractor (static)
│   │   ├── openf1.py           # OpenF1 API extractor (live sessions)
│   │   └── news.py             # Motorsport.com news scraper (live)
│   ├── transformers/
│   │   └── chunker.py          # Source-aware text chunking
│   ├── embedders/
│   │   └── ollama.py           # Local embedding via Ollama
│   ├── loaders/
│   │   └── pgvector.py         # PostgreSQL + pgvector storage
│   ├── pipeline.py             # Orchestration entry point (static ingestion)
│   ├── scheduler.py            # APScheduler live refresh jobs
│   └── healthcheck.py          # Connectivity verification
├── agent/                      # RAG agent
│   ├── agent.py                # Core reasoning loop (streaming + sync)
│   ├── llm.py                  # Gemini API client (generate + stream)
│   ├── prompts.py              # System instructions and prompt templates
│   ├── retriever.py            # Hybrid dense+sparse retriever with RRF
│   ├── router.py               # Intent classifier (HISTORICAL/CURRENT/MIXED)
│   └── tools.py                # Live standings tool
├── api/                        # FastAPI application
│   ├── main.py                 # App factory, CORS, lifespan
│   ├── schemas.py              # Request/response models
│   └── routes/
│       ├── chat.py             # POST /chat · GET /chat/stream
│       ├── health.py           # GET /health
│       └── standings.py        # GET /standings/drivers · /standings/constructors
├── frontend/                   # Next.js chat interface
│   ├── app/                    # App Router pages and layouts
│   ├── components/
│   │   ├── chat/               # ChatPanel, MessageBubble, ChatInput, SourceChip
│   │   ├── layout/             # Navbar, SplitLayout
│   │   └── standings/          # StandingsTabs, StandingsPanel, StandingsRow
│   ├── hooks/
│   │   ├── useChat.ts          # Chat state and streaming
│   │   └── useStandings.ts     # Standings data fetching
│   └── __tests__/              # Vitest component and hook tests
├── db/
│   └── schema.sql              # PostgreSQL schema + indexes
├── tests/                      # pytest test suite
├── main.py                     # Application entry point
├── Dockerfile                  # API container image
├── docker-compose.yml          # PostgreSQL, Ollama, and API services
├── pyproject.toml              # Project metadata + dependencies
└── .env.example                # Environment variable template
```

---

## Prerequisites

- **Docker** and **Docker Compose** (for PostgreSQL, Ollama, and the API)
- **Python 3.13** (managed via `.python-version`) — only needed for local development outside Docker
- **uv** — fast Python package manager (`pip install uv` or see [uv docs](https://docs.astral.sh/uv/))
- **Node.js** + **pnpm** — for the frontend (`npm install -g pnpm`)
- **Google Gemini API key** — for LLM inference and intent routing

---

## Getting Started

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd f1-chatbot
cp .env.example .env
```

Edit `.env` and set your Gemini API key:

```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash
FRONTEND_URL=http://localhost:3000
```

The remaining defaults work out of the box with the provided Docker Compose configuration.

### 2. Start infrastructure

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 16** with pgvector on port `5433` (host) → `5432` (container). The schema is initialised automatically from `db/schema.sql`.
- **Ollama** on port `11434` for local embedding.
- **API** on port `8000` — the FastAPI backend.

Wait for all services to become healthy:

```bash
docker compose ps
```

### 3. Pull Ollama embedding model

```bash
docker exec -it f1-chatbot-ollama-1 ollama pull nomic-embed-text
```

### 4. Install Python dependencies

Only needed for local development (e.g. running ingestion or tests outside Docker):

```bash
uv sync
```

### 5. Verify connectivity

```bash
uv run python -m ingestion.healthcheck
```

Expected output confirms:
- PostgreSQL reachable and pgvector extension installed
- Ollama reachable and `nomic-embed-text` model present
- Jolpica API reachable
- Wikipedia API reachable

### 6. Run the ingestion pipeline

Ingest the full historical knowledge base (1950–2024):

```bash
uv run python -m ingestion.pipeline --phase static
```

Optional flags:

```bash
# Ingest a specific year range (useful for testing)
uv run python -m ingestion.pipeline --phase static --start-year 2020 --end-year 2024

# Run all phases (static + live)
uv run python -m ingestion.pipeline --phase all
```

The pipeline logs progress with structured output. Ingestion is **idempotent** — re-running it will skip documents that have already been processed (via content fingerprinting).

### 7. Start the API server

The API runs automatically inside Docker (`docker compose up`). For local development:

```bash
uv run uvicorn api.main:app --reload --port 8000
```

### 8. Start the frontend

```bash
cd frontend
pnpm install
pnpm dev
```

The chat interface will be available at `http://localhost:3000`.

---

## Environment Variables

All backend configuration is loaded from `.env` via Pydantic Settings. Copy `.env.example` to `.env` to get started.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://f1:f1secret@localhost:5432/f1kb` | Full async connection string |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama service URL |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Model used for generating embeddings |
| `GEMINI_API_KEY` | _(required)_ | Google Gemini API key for LLM inference |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model for routing and answer generation |
| `FRONTEND_URL` | _(empty)_ | CORS allowed origin for the frontend (e.g. Vercel URL) |
| `REQUEST_DELAY_SECONDS` | `0.5` | Delay between API requests to avoid rate limiting |
| `MAX_RETRIES` | `3` | Maximum retry attempts for failed requests |
| `CHUNK_SIZE_STRUCTURED` | `512` | Characters per chunk for structured (Jolpica) data |
| `CHUNK_SIZE_NARRATIVE` | `800` | Characters per chunk for narrative (Wikipedia) data |
| `CHUNK_OVERLAP` | `80` | Overlap in characters between consecutive chunks |
| `EMBEDDING_BATCH_SIZE` | `32` | Number of chunks embedded per batch |
| `LIVE_REFRESH_INTERVAL_HOURS` | `6` | Scheduler interval for OpenF1 live data refresh |
| `NEWS_REFRESH_INTERVAL_HOURS` | `3` | Scheduler interval for news scraping |

---

## Data Sources

### Jolpica API (Ergast-compatible) — static

Provides structured F1 data as JSON for the full historical record (1950–2024):

- **Drivers** — name, nationality, date of birth, career span
- **Constructors** — team name, nationality, seasons active
- **Race results** — position, driver, constructor, time, points
- **Qualifying results** — Q1/Q2/Q3 times per driver per race
- **Driver standings** — championship standings after each round
- **Constructor standings** — team standings after each round

### Wikipedia — static

Narrative articles covering 42 key F1 topics including prominent drivers, constructor histories, iconic circuits, and general F1 history. Articles are extracted section-by-section with wikitext templates, references, and hyperlinks stripped to produce clean prose.

### OpenF1 API — live

Provides real-time and recent session data for the current season including session results and driver lap data. Refreshed every 6 hours by the background scheduler.

### Motorsport.com — live

F1 news articles scraped from Motorsport.com. Articles are deduplicated by URL and content fingerprint. Refreshed every 3 hours by the background scheduler.

---

## Ingestion Pipeline

The pipeline is fully asynchronous (`async`/`await` throughout) and follows a linear Extract → Transform → Embed → Load flow.

### Extraction

All extractors inherit from `BaseExtractor` and yield `RawDocument` objects.

**`JolpicaExtractor`** — fetches paginated JSON from the Jolpica API with automatic pagination, configurable rate-limit delay, and exponential backoff retries via Tenacity.

**`WikipediaExtractor`** — fetches F1 Wikipedia articles per-section with wikitext cleaning.

**`OpenF1Extractor`** — fetches live session data from the OpenF1 API, supporting incremental sync via a `since` timestamp.

**`NewsExtractor`** — scrapes Motorsport.com F1 news, deduplicating by URL before embedding.

### Chunking

**`Chunker`** applies different strategies depending on the source type:

| Source | Strategy | Chunk size |
|---|---|---|
| Jolpica race results | JSON → formatted prose | 512 chars |
| Jolpica driver/constructor | JSON → key-value prose | 512 chars |
| Jolpica standings | JSON → ranked list prose | 512 chars |
| Wikipedia / News | Raw cleaned text | 800 chars |

All chunks use 80-character overlap to preserve context across boundaries, powered by LangChain's `RecursiveCharacterTextSplitter`.

### Embedding

**`OllamaEmbedder`** converts text chunks into 768-dimensional dense vectors using `nomic-embed-text` running locally in the Ollama container. Processing happens in configurable batches (default: 32) with async HTTP requests and retry logic.

### Storage

**`PgVectorLoader`** persists documents and chunks to PostgreSQL:

1. Computes an `xxhash64` fingerprint of each document's raw content
2. Skips documents whose fingerprint already exists (idempotent re-runs)
3. Inserts the document and all its chunks in a single transaction
4. Rebuilds the IVFFlat vector index after bulk ingestion for optimal query performance

---

## Agent and Retrieval

### Intent Router

The `Router` uses Gemini to classify each query into one of three intents:

| Intent | Description | Retrieval strategy |
|---|---|---|
| `HISTORICAL` | Questions about past seasons or records | Static partition only |
| `CURRENT` | Questions about the live season | Live standings tool only |
| `MIXED` | Questions spanning both | Static + live partitions + standings |

### Hybrid Retriever

The `Retriever` combines two search strategies and merges them with Reciprocal Rank Fusion (RRF):

- **Dense search** — cosine similarity over `nomic-embed-text` embeddings via pgvector (`<=>` operator)
- **Sparse search** — PostgreSQL full-text search over the generated `content_tsv` tsvector column (`plainto_tsquery`)

Each search returns up to 20 candidates; RRF (k=60) re-ranks and the top-k (default 6) chunks are passed as context to the LLM.

### LLM (Gemini)

**`agent/llm.py`** wraps the Gemini API with:
- `generate()` — single-shot for intent routing
- `stream()` — SSE streaming for answer generation
- Exponential backoff retry on HTTP 429

The agent caps context at 12,000 characters (~3,000 tokens) before sending to Gemini.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service health check |
| `POST` | `/chat` | Synchronous chat — returns full answer + sources + intent + latency |
| `GET` | `/chat/stream?query=...` | Streaming chat — Server-Sent Events (`data: {"token": "..."}`) |
| `GET` | `/standings/drivers` | Current season driver standings from Jolpica |
| `GET` | `/standings/constructors` | Current season constructor standings from Jolpica |

### Chat request/response

```json
// POST /chat
{ "query": "Who won the 2008 championship?", "max_chunks": 6 }

// Response
{
  "answer": "Lewis Hamilton won...",
  "sources": [{ "content_type": "RACE_RESULT", "source": "JOLPICA", "metadata": {} }],
  "intent": "HISTORICAL",
  "latency_ms": 1234.5
}
```

---

## Frontend

The Next.js 16 frontend (React 19, Tailwind CSS v4) provides a split-panel interface:

- **Left panel — Chat**: streaming message bubbles, source attribution chips, chat input with submit
- **Right panel — Standings**: driver and constructor standings tabs with live data from `/standings/*`

Key hooks:
- `useChat` — manages message history and consumes the SSE streaming endpoint
- `useStandings` — fetches and caches driver/constructor standings

Run tests with:

```bash
cd frontend
pnpm test
```

---

## Live Scheduler

The `ingestion/scheduler.py` runs two background jobs via APScheduler (embedded in the FastAPI process):

| Job | Interval | Source | Description |
|---|---|---|---|
| `openf1_refresh` | Every 6h | OpenF1 API | Fetches live session data since last sync |
| `news_scrape` | Every 3h | Motorsport.com | Scrapes and ingests new F1 news articles |

Each run is logged to the `job_runs` table. Incremental sync state (last synced timestamp per source) is persisted in `sync_state`.

---

## Database Schema

Four tables are defined in `db/schema.sql`:

**`documents`** — one row per raw document ingested

| Column | Type | Description |
|---|---|---|
| `id` | SERIAL PK | Auto-increment ID |
| `fingerprint` | TEXT UNIQUE | xxhash64 of raw content |
| `source` | ENUM | `JOLPICA`, `WIKIPEDIA`, `OPENF1`, `NEWS` |
| `content_type` | ENUM | `RACE_RESULT`, `QUALIFYING_RESULT`, `STANDINGS`, `DRIVER_PROFILE`, `CONSTRUCTOR_PROFILE`, `NARRATIVE` |
| `partition` | ENUM | `STATIC` (historical) or `LIVE` (real-time) |
| `metadata` | JSONB | Arbitrary source metadata |
| `fetched_at` | TIMESTAMPTZ | When the source was fetched |
| `created_at` | TIMESTAMPTZ | Row creation time |

**`chunks`** — one row per text chunk with its embedding

| Column | Type | Description |
|---|---|---|
| `id` | SERIAL PK | Auto-increment ID |
| `chunk_id` | TEXT UNIQUE | `{fingerprint}_{index}` |
| `doc_fingerprint` | TEXT FK | Reference to parent document |
| `content` | TEXT | The text chunk |
| `embedding` | vector(768) | pgvector embedding column |
| `content_type` | ENUM | Inherited from parent document |
| `partition` | ENUM | Inherited from parent document |
| `source` | ENUM | Inherited from parent document |
| `metadata` | JSONB | Chunk-level metadata |
| `content_tsv` | TSVECTOR | Generated column for full-text search |
| `created_at` | TIMESTAMPTZ | Row creation time |

**Indexes:**
- IVFFlat index on `embedding` for cosine similarity search (`lists=100`)
- GIN index on `content_tsv` for full-text search

**`sync_state`** — tracks incremental sync progress per source (updated each scheduler run)

**`job_runs`** — audit log for scheduled ingestion jobs (started_at, finished_at, docs_upserted, errors, success)

---

## Running Tests

**Backend:**

```bash
uv run pytest tests/
```

The test suite covers:
- **Extractor tests** — mocked HTTP responses via respx for Jolpica, Wikipedia, OpenF1, and news extractors
- **Chunker tests** — transformation of structured JSON to prose and text splitting correctness
- **Pipeline tests** — end-to-end pipeline integration with mocked external dependencies
- **Agent tests** — router classification, retriever, and agent run logic
- **API tests** — FastAPI route responses
- **Standings tests** — standings endpoint with mocked Jolpica responses

**Frontend:**

```bash
cd frontend
pnpm test
```

---

## Development Roadmap

| Phase | Status | Description |
|---|---|---|
| **Phase 1 — Static KB** | Done | Project scaffold, Docker, schema, Jolpica and Wikipedia extractors, chunking, embedding, pgvector storage |
| **Phase 2 — Live Updates** | Done | APScheduler-driven periodic refresh, OpenF1 extractor, Motorsport.com news scraper, `sync_state` and `job_runs` tracking |
| **Phase 3 — Hybrid Retrieval** | Done | Dense (pgvector cosine) + sparse (tsvector full-text) search merged with Reciprocal Rank Fusion |
| **Phase 4 — API + Agent** | Done | FastAPI endpoints, intent router, Gemini 2.5 Flash LLM, streaming SSE chat, live standings tool |
| **Frontend** | Done | Next.js 16 + React 19 split-panel UI with streaming chat and live standings |
