# F1 AI Chatbot — Build Plan

## Overview

A RAG-powered F1 chatbot that can answer questions about the full history of
Formula One as well as current season events. The backend is a Python FastAPI
service acting as a RAG agent; the knowledge base lives in PostgreSQL with the
pgvector extension. All embeddings and generation use free, open-source models
running locally via Ollama.

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Vector store | PostgreSQL + pgvector | Single DB for vectors and metadata |
| Embeddings | `nomic-embed-text` via Ollama | 768-dim, runs locally, free |
| LLM | `mistral` or `llama3` via Ollama | Swap freely; no API key needed |
| Backend | Python 3.12, FastAPI | Async throughout |
| Scheduler | APScheduler | Live KB refresh jobs |
| Frontend | Next.js 14 (App Router) | Planned — not in this build plan |
| Infra | Docker Compose | Postgres + Ollama + API all containerised |
| Env/deps | `uv` | Fast, modern Python package manager |

---

## Starting Point

This plan assumes you are starting from scratch — no existing repo, no
database, no code. The very first thing to do is open `PREREQUISITES.md`.
Section 0 walks you through creating the repo and full folder structure
before anything else is touched.

## Before You Start

| File | Purpose |
|---|---|
| [PREREQUISITES.md](./PREREQUISITES.md) | Create the repo, install all tools, verify everything is working |

## Phases

| Phase | Plan | Completion Report | What gets built |
|---|---|---|---|
| 1 | [PHASE_1.md](./PHASE_1.md) | [PHASE_1_DONE.md](./PHASE_1_DONE.md) | Project scaffold + Static KB ingestion (Jolpica + Wikipedia) |
| 2 | [PHASE_2.md](./PHASE_2.md) | [PHASE_2_DONE.md](./PHASE_2_DONE.md) | Live KB ingestion (OpenF1 + News scraper) + scheduler |
| 3 | [PHASE_3.md](./PHASE_3.md) | [PHASE_3_DONE.md](./PHASE_3_DONE.md) | FastAPI RAG agent, hybrid search, query routing |

> **Workflow:** Read the plan file → build → fill in the completion report → proceed to next phase.
> Do not start a phase until the previous phase's completion report is fully filled in.

Each phase is fully self-contained and results in working, runnable code before
the next phase begins.

---

## Repository Layout (final state after all phases)

```
f1-chatbot/
├── docker-compose.yml
├── .env.example
├── pyproject.toml
│
├── ingestion/                  # Phases 1 & 2
│   ├── core/
│   │   ├── config.py
│   │   ├── models.py
│   │   └── logging.py
│   ├── extractors/
│   │   ├── base.py
│   │   ├── jolpica.py          # Phase 1
│   │   ├── wikipedia.py        # Phase 1
│   │   ├── openf1.py           # Phase 2
│   │   └── news.py             # Phase 2
│   ├── transformers/
│   │   └── chunker.py
│   ├── embedders/
│   │   └── ollama.py
│   ├── loaders/
│   │   └── pgvector.py
│   ├── pipeline.py             # Orchestrates extract → chunk → embed → load
│   └── scheduler.py            # Phase 2
│
├── agent/                      # Phase 3
│   ├── retriever.py            # Hybrid search (pgvector + BM25)
│   ├── router.py               # Classifies query → RAG vs live API vs structured
│   ├── tools.py                # Structured query tools (standings, results)
│   ├── agent.py                # Core reasoning loop
│   └── prompts.py
│
├── api/                        # Phase 3
│   ├── main.py
│   ├── routes/
│   │   ├── chat.py
│   │   └── health.py
│   └── schemas.py
│
├── db/
│   ├── migrations/
│   └── schema.sql
│
└── tests/
    ├── test_extractors.py
    ├── test_pipeline.py
    └── test_agent.py
```

---

## Data Sources Summary

| Source | Phase | Partition | Content |
|---|---|---|---|
| Jolpica API | 1 | Static | Race results, qualifying, standings, drivers, constructors — 1950–2024 |
| Wikipedia | 1 | Static | Driver bios, team histories, circuit articles, F1 history narratives |
| OpenF1 API | 2 | Live | Current season session data, lap times, tyre stints, telemetry |
| Motorsport.com | 2 | Live | News articles, race previews, team updates |

---

## Environment Variables (`.env.example`)

```bash
# Postgres
POSTGRES_USER=f1
POSTGRES_PASSWORD=f1secret
POSTGRES_DB=f1kb
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://f1:f1secret@localhost:5432/f1kb

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
LLM_MODEL=mistral

# Ingestion
REQUEST_DELAY_SECONDS=0.5
CHUNK_SIZE_STRUCTURED=512
CHUNK_SIZE_NARRATIVE=800
CHUNK_OVERLAP=80
EMBEDDING_BATCH_SIZE=32

# Scheduler (Phase 2)
LIVE_REFRESH_INTERVAL_HOURS=6
NEWS_REFRESH_INTERVAL_HOURS=3
```

---

## Docker Compose (full — all phases)

```yaml
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
    # On first run: docker exec -it ollama ollama pull nomic-embed-text
    #               docker exec -it ollama ollama pull mistral

  api:
    build: .
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - ollama
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

volumes:
  pgdata:
  ollama_models:
```

---

## Getting Started (after all phases are complete)

```bash
# 1. Start infrastructure
docker compose up postgres ollama -d

# 2. Pull models into Ollama
docker exec -it f1-chatbot-ollama-1 ollama pull nomic-embed-text
docker exec -it f1-chatbot-ollama-1 ollama pull mistral

# 3. Install Python deps
uv sync

# 4. Run DB migrations
uv run python -m db.migrate

# 5. Run Phase 1 ingestion (static KB — takes ~20–40 min first run)
uv run python -m ingestion.pipeline --phase static

# 6. Run Phase 2 ingestion (live KB)
uv run python -m ingestion.pipeline --phase live

# 7. Start API
docker compose up api
```
