# F1 Chatbot

An AI-powered Formula 1 knowledge base and chatbot built with RAG (Retrieval-Augmented Generation). The system ingests historical F1 data from multiple sources, generates semantic embeddings locally via Ollama, and stores them in PostgreSQL with pgvector — forming the foundation for a conversational F1 assistant.

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
- [Environment Variables](#environment-variables)
- [Data Sources](#data-sources)
- [Ingestion Pipeline](#ingestion-pipeline)
  - [Extraction](#extraction)
  - [Chunking](#chunking)
  - [Embedding](#embedding)
  - [Storage](#storage)
- [Database Schema](#database-schema)
- [Running Tests](#running-tests)
- [Development Roadmap](#development-roadmap)

---

## Overview

F1 Chatbot builds a semantic knowledge base covering Formula 1 history from 1950 to 2024. It ingests structured race data (results, qualifying, standings, driver/constructor profiles) and narrative Wikipedia articles, transforms them into overlapping text chunks, embeds each chunk using a locally-running language model, and indexes the vectors in PostgreSQL for fast similarity search.

The knowledge base is designed to serve as the retrieval layer for a conversational agent that can answer questions such as:

- *"Who won the 2008 World Drivers' Championship and by how many points?"*
- *"What were Ayrton Senna's championship years and teams?"*
- *"List all circuits that hosted the British Grand Prix."*

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Data Sources                          │
│        Jolpica API (Ergast-compatible)  ·  Wikipedia         │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                    Ingestion Pipeline                        │
│                                                              │
│   Extract  →  Chunk  →  Embed (Ollama)  →  Load (pgvector)  │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              PostgreSQL + pgvector                           │
│    documents · chunks · sync_state · job_runs                │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   [Planned] API + Agent                      │
│    FastAPI routes  →  LLM (Mistral)  →  Chat responses       │
└──────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| Web framework | FastAPI 0.115 + Uvicorn |
| Database | PostgreSQL 16 + pgvector |
| ORM / async DB | SQLAlchemy 2 (async) + AsyncPG |
| Embeddings | Ollama (`nomic-embed-text`, 768-dim) |
| LLM (planned) | Ollama (`mistral`) |
| HTTP clients | HTTPX, aiohttp |
| Text splitting | LangChain Text Splitters |
| Web scraping | BeautifulSoup4 + lxml |
| Wikipedia client | wikipedia-api |
| Job scheduling | APScheduler |
| Retry logic | Tenacity |
| Logging | structlog |
| Fingerprinting | xxhash |
| Containerisation | Docker Compose |
| Testing | pytest + pytest-asyncio + respx |
| Package manager | uv |

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
│   │   ├── jolpica.py          # Ergast-compatible F1 API extractor
│   │   └── wikipedia.py        # Wikipedia article extractor
│   ├── transformers/
│   │   └── chunker.py          # Source-aware text chunking
│   ├── embedders/
│   │   └── ollama.py           # Local embedding via Ollama
│   ├── loaders/
│   │   └── pgvector.py         # PostgreSQL + pgvector storage
│   ├── pipeline.py             # Orchestration entry point
│   └── healthcheck.py          # Connectivity verification
├── api/                        # [Planned] FastAPI routes
├── agent/                      # [Planned] LLM agent
├── db/
│   └── schema.sql              # PostgreSQL schema + indexes
├── tests/                      # pytest test suite
├── main.py                     # Application entry point
├── pyproject.toml              # Project metadata + dependencies
├── docker-compose.yml          # PostgreSQL and Ollama services
└── .env.example                # Environment variable template
```

---

## Prerequisites

- **Docker** and **Docker Compose** (for PostgreSQL and Ollama)
- **Python 3.13** (managed via `.python-version`)
- **uv** — fast Python package manager (`pip install uv` or see [uv docs](https://docs.astral.sh/uv/))

---

## Getting Started

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd f1-chatbot
cp .env.example .env
```

The defaults in `.env.example` work out of the box with the provided Docker Compose configuration. Edit `.env` only if you need to change ports or credentials.

### 2. Start infrastructure

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 16** with pgvector on port `5433` (host) → `5432` (container). The schema is initialised automatically from `db/schema.sql`.
- **Ollama** on port `11434` for local embedding and inference.

Wait for both services to become healthy:

```bash
docker compose ps
```

### 3. Pull Ollama embedding model

```bash
docker exec -it f1-chatbot-ollama-1 ollama pull nomic-embed-text
```

Optionally pull the LLM model for future chat functionality:

```bash
docker exec -it f1-chatbot-ollama-1 ollama pull mistral
```

### 4. Install Python dependencies

```bash
uv sync
```

### 5. Verify connectivity

Run the health check to confirm all services are reachable and the embedding model is available:

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

---

## Environment Variables

All configuration is loaded from `.env` via Pydantic Settings. Copy `.env.example` to `.env` to get started.

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_USER` | `f1` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `f1secret` | PostgreSQL password |
| `POSTGRES_DB` | `f1kb` | PostgreSQL database name |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `DATABASE_URL` | `postgresql+asyncpg://f1:f1secret@localhost:5432/f1kb` | Full async connection string |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama service URL |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Model used for generating embeddings |
| `LLM_MODEL` | `mistral` | LLM model for chat generation (Phase 4) |
| `REQUEST_DELAY_SECONDS` | `0.5` | Delay between API requests to avoid rate limiting |
| `MAX_RETRIES` | `3` | Maximum retry attempts for failed requests |
| `CHUNK_SIZE_STRUCTURED` | `512` | Characters per chunk for structured (Jolpica) data |
| `CHUNK_SIZE_NARRATIVE` | `800` | Characters per chunk for narrative (Wikipedia) data |
| `CHUNK_OVERLAP` | `80` | Overlap in characters between consecutive chunks |
| `EMBEDDING_BATCH_SIZE` | `32` | Number of chunks embedded per batch |
| `LIVE_REFRESH_INTERVAL_HOURS` | `6` | Scheduler interval for live data refresh (Phase 2) |
| `NEWS_REFRESH_INTERVAL_HOURS` | `3` | Scheduler interval for news refresh (Phase 2) |

---

## Data Sources

### Jolpica API (Ergast-compatible)

Provides structured F1 data as JSON:

- **Drivers** — name, nationality, date of birth, career span
- **Constructors** — team name, nationality, seasons active
- **Race results** — position, driver, constructor, time, points (every race 1950–2024)
- **Qualifying results** — Q1/Q2/Q3 times per driver per race
- **Driver standings** — championship standings after each round
- **Constructor standings** — team standings after each round

### Wikipedia

Narrative articles covering 42 key F1 topics including prominent drivers (Hamilton, Schumacher, Senna, Prost, and others), constructor histories (Ferrari, Mercedes, Red Bull, McLaren, and others), iconic circuits (Monaco, Silverstone, Monza, and others), and general F1 history.

Articles are extracted section-by-section, with wikitext templates, references, and hyperlinks stripped to produce clean prose.

---

## Ingestion Pipeline

The pipeline is fully asynchronous (Python `async`/`await` throughout) and follows a linear Extract → Transform → Embed → Load flow.

### Extraction

**`JolpicaExtractor`** — fetches paginated JSON from the Jolpica API with:
- Automatic pagination through all results
- Configurable rate-limit delay between requests
- Exponential backoff retries via Tenacity (handles HTTP 429)
- Structured logging with request context

**`WikipediaExtractor`** — fetches F1 Wikipedia articles with:
- Per-section extraction for granular retrieval
- Wikitext cleaning (removes `{{templates}}`, `[[links]]`, `<references>`)
- User-Agent header as required by the Wikipedia API

### Chunking

**`Chunker`** applies different strategies depending on the source type:

| Source | Strategy | Chunk size |
|---|---|---|
| Jolpica race results | JSON → formatted prose | 512 chars |
| Jolpica driver/constructor | JSON → key-value prose | 512 chars |
| Jolpica standings | JSON → ranked list prose | 512 chars |
| Wikipedia | Raw cleaned text | 800 chars |

All chunks use 80-character overlap to preserve context across boundaries. Chunking is powered by LangChain's `RecursiveCharacterTextSplitter`.

Example structured → prose transformation:

```
Race result:     P1: Lewis Hamilton (Mercedes) — 1:43:28.437 [25 pts]
Driver profile:  Driver: Lewis Hamilton, Nationality: British, DOB: 1985-01-07
Standings:       1. Lewis Hamilton — 433 pts
```

### Embedding

**`OllamaEmbedder`** converts text chunks into 768-dimensional dense vectors using the `nomic-embed-text` model running locally in the Ollama container. Processing happens in configurable batches (default: 32) with async HTTP requests and retry logic.

### Storage

**`PgVectorLoader`** persists documents and chunks to PostgreSQL:

1. Computes an `xxhash64` fingerprint of each document's raw content
2. Skips documents whose fingerprint already exists (idempotent re-runs)
3. Inserts the document and all its chunks in a single transaction
4. Rebuilds the IVFFlat vector index after bulk ingestion for optimal query performance

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

**`sync_state`** — tracks incremental sync progress per source (Phase 2)

**`job_runs`** — audit log for scheduled ingestion jobs (Phase 2)

---

## Running Tests

```bash
uv run pytest tests/
```

The test suite covers:
- **Extractor tests** — mocked HTTP responses via respx for Jolpica and Wikipedia extractors
- **Chunker tests** — transformation of structured JSON to prose and text splitting correctness
- **Pipeline tests** — end-to-end pipeline integration with mocked external dependencies

---

## Development Roadmap

| Phase | Status | Description |
|---|---|---|
| **Phase 1 — Static KB** | Done | Project scaffold, Docker, schema, Jolpica and Wikipedia extractors, chunking, embedding, pgvector storage |
| **Phase 2 — Live Updates** | Planned | APScheduler-driven periodic refresh of current-season data, `sync_state` tracking, OpenF1 integration |
| **Phase 3 — Hybrid Retrieval** | Planned | Combine vector similarity search with full-text search (tsvector already in schema) for improved relevance |
| **Phase 4 — API + Agent** | Planned | FastAPI query endpoints, LLM agent (Mistral) with multi-turn conversation, source attribution in responses |
