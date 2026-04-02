# Prerequisites

Work through every section in order. By the end of this file you will have:
- A new Git repo with the full project folder structure
- Python 3.12 environment with all packages installed
- Docker Compose running PostgreSQL (with pgvector) and Ollama
- Both AI models pulled and ready locally
- `.env` configured with all required variables
- All external APIs verified as reachable
- A passing pre-flight checklist

Only then should you open `PHASE_1.md`.

---

## 1. System Requirements

Verify your machine meets these before installing anything.

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | macOS 12+, Ubuntu 22.04+, Windows 11 (WSL2) | macOS or Ubuntu native |
| RAM | 8 GB | 16 GB — Ollama + Postgres + API all run together |
| Disk | 20 GB free | 30 GB — Ollama models are 4–8 GB |
| CPU | 4 cores | 8 cores — faster local inference |
| GPU | Not required | NVIDIA CUDA or Apple Metal — Ollama uses it automatically if present |

> **Windows users:** All commands in this plan assume a Unix shell.
> Use WSL2 (Ubuntu) throughout — do not use PowerShell or CMD.

---

## 2. Install Required Tools

### 2.1 Git

**macOS:**
```bash
brew install git
```

**Ubuntu:**
```bash
sudo apt update && sudo apt install -y git
```

**Verify:**
```bash
git --version
# git version 2.x.x
```

---

### 2.2 Python 3.12

**macOS:**
```bash
brew install python@3.12
```

**Ubuntu:**
```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

**All platforms (alternative):** https://www.python.org/downloads/

**Verify:**
```bash
python3.12 --version
# Python 3.12.x
```

---

### 2.3 uv (Python package and project manager)

`uv` replaces pip and poetry — faster, and handles Python version pinning,
virtual environments, and dependency locking in one tool.

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your terminal after installing, then verify:
```bash
uv --version
# uv 0.4.x or higher
```

---

### 2.4 Docker Desktop (includes Docker Compose V2)

Used to run PostgreSQL and Ollama as containers — no local installation of
either is needed beyond Docker itself.

**macOS / Windows:** https://www.docker.com/products/docker-desktop

**Ubuntu:**
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

**Verify:**
```bash
docker --version
# Docker version 26.x.x or higher

docker compose version
# Docker Compose version v2.x.x or higher
```

> This plan uses `docker compose` (V2, no hyphen). If you only have
> `docker-compose` (V1), upgrade before continuing.

---

### 2.5 curl

Used for smoke tests and manual API testing. Usually pre-installed.

**Verify:**
```bash
curl --version
```

If missing: `brew install curl` (macOS) or `sudo apt install curl` (Ubuntu).

---

## 3. Create the Project

### 3.1 Create the repo

```bash
mkdir f1-chatbot
cd f1-chatbot
git init
```

### 3.2 Initialise the Python project

```bash
uv init .
uv python pin 3.12
rm hello.py        # remove uv's placeholder file
```

This produces:
```
f1-chatbot/
├── .python-version   ← pins Python 3.12 for the project
├── pyproject.toml    ← dependency manifest (populated in section 4)
└── README.md
```

### 3.3 Create the full folder structure

```bash
mkdir -p ingestion/core \
         ingestion/extractors \
         ingestion/transformers \
         ingestion/embedders \
         ingestion/loaders \
         agent \
         api/routes \
         db/migrations \
         tests
```

### 3.4 Create `__init__.py` files

```bash
touch ingestion/__init__.py \
      ingestion/core/__init__.py \
      ingestion/extractors/__init__.py \
      ingestion/transformers/__init__.py \
      ingestion/embedders/__init__.py \
      ingestion/loaders/__init__.py \
      agent/__init__.py \
      api/__init__.py \
      api/routes/__init__.py \
      tests/__init__.py
```

### 3.5 Create `.gitignore`

```bash
cat > .gitignore << 'EOF'
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.DS_Store
EOF
```

---

## 4. Install Python Packages

### 4.1 Populate `pyproject.toml`

Replace the contents of `pyproject.toml` with:

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
  "aiohttp==3.10.0",
  "beautifulsoup4==4.12.3",
  "lxml==5.3.0",
  "wikipedia-api==0.7.1",
  "sqlalchemy[asyncio]==2.0.35",
  "asyncpg==0.31.0",
  "aiosqlite==0.20.0",
  "pgvector==0.3.2",
  "langchain-text-splitters==0.3.11",
  "apscheduler==3.10.4",
  "tenacity>=9.0.0",
  "structlog==24.4.0",
  "tqdm==4.66.5",
  "xxhash==3.5.0",
]

[project.optional-dependencies]
dev = [
  "pytest==8.3.0",
  "pytest-asyncio==0.24.0",
  "respx==0.21.1",
]

[tool.hatch.build.targets.wheel]
packages = ["ingestion", "agent", "api"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 4.2 Install all packages

```bash
uv sync --all-extras
```

### 4.3 Verify key packages are importable

```bash
uv run python -c "
import fastapi, pgvector, sqlalchemy
import langchain_text_splitters, apscheduler, structlog
print('All packages OK')
"
# All packages OK
```

---

## 5. Environment Variables

### 5.1 Create `.env.example`

```bash
cat > .env.example << 'EOF'
# PostgreSQL
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
MAX_RETRIES=3
CHUNK_SIZE_STRUCTURED=512
CHUNK_SIZE_NARRATIVE=800
CHUNK_OVERLAP=80
EMBEDDING_BATCH_SIZE=32

# Scheduler (Phase 2)
LIVE_REFRESH_INTERVAL_HOURS=6
NEWS_REFRESH_INTERVAL_HOURS=3
EOF
```

### 5.2 Create your working `.env`

```bash
cp .env.example .env
```

The defaults work as-is for local Docker Compose development.
No API keys are needed — everything runs locally via Ollama.

---

## 6. Docker Compose Setup

### 6.1 Create `docker-compose.yml`

```bash
cat > docker-compose.yml << 'EOF'
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
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U f1"]
      interval: 5s
      timeout: 5s
      retries: 5

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:11434/api/tags || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
  ollama_models:
EOF
```

> The `api` service is added in Phase 3 when the FastAPI app is built.
> For Phases 1 and 2, only `postgres` and `ollama` are needed.

### 6.2 Create the database schema file

```bash
cat > db/schema.sql << 'EOF'
CREATE EXTENSION IF NOT EXISTS vector;

-- Tracks every raw document fetched, used for deduplication
CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL PRIMARY KEY,
    fingerprint  TEXT UNIQUE NOT NULL,
    source       TEXT NOT NULL,
    content_type TEXT NOT NULL,
    partition    TEXT NOT NULL,
    metadata     JSONB DEFAULT '{}',
    fetched_at   TIMESTAMPTZ DEFAULT NOW(),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks derived from documents, with embeddings
CREATE TABLE IF NOT EXISTS chunks (
    id              SERIAL PRIMARY KEY,
    chunk_id        TEXT UNIQUE NOT NULL,
    doc_fingerprint TEXT NOT NULL REFERENCES documents(fingerprint),
    content         TEXT NOT NULL,
    source          TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    partition       TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}',
    embedding       vector(768),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Tracks last sync time per source for incremental ingestion (Phase 2)
CREATE TABLE IF NOT EXISTS sync_state (
    source         TEXT PRIMARY KEY,
    last_synced_at TIMESTAMPTZ,
    metadata       JSONB DEFAULT '{}'
);

-- Audit log for scheduled ingestion jobs (Phase 2)
CREATE TABLE IF NOT EXISTS job_runs (
    id            SERIAL PRIMARY KEY,
    job_id        TEXT NOT NULL,
    started_at    TIMESTAMPTZ DEFAULT NOW(),
    finished_at   TIMESTAMPTZ,
    docs_upserted INT DEFAULT 0,
    errors        JSONB DEFAULT '[]',
    success       BOOLEAN DEFAULT FALSE
);

-- Full-text search column for hybrid retrieval (Phase 3)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

-- Vector similarity index (rebuild after bulk ingestion with correct list count)
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Full-text search index
CREATE INDEX IF NOT EXISTS chunks_content_tsv_idx
    ON chunks USING GIN (content_tsv);
EOF
```

### 6.3 Start the containers

```bash
docker compose up postgres ollama -d
```

Wait ~15 seconds for both containers to become healthy, then verify:

```bash
docker compose ps
# NAME        STATUS
# postgres    healthy
# ollama      running (or healthy)
```

### 6.4 Verify PostgreSQL and the schema

```bash
# Confirm pgvector extension installed
docker exec -it $(docker ps -qf "name=postgres") \
  psql -U f1 -d f1kb -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
# Returns one row: vector | 0.x.x

# Confirm all four tables were created
docker exec -it $(docker ps -qf "name=postgres") \
  psql -U f1 -d f1kb -c "\dt"
# Returns: chunks, documents, job_runs, sync_state
```

---

## 7. Pull Ollama Models

One-time download of ~4.4 GB total. Ensure a stable connection before running.

```bash
# Embedding model (~274 MB)
docker exec -it $(docker ps -qf "name=ollama") ollama pull nomic-embed-text

# LLM for generation and query routing (~4.1 GB)
docker exec -it $(docker ps -qf "name=ollama") ollama pull mistral
```

| Model | Size | Purpose |
|---|---|---|
| `nomic-embed-text` | ~274 MB | Chunk and query embeddings (768 dims) |
| `mistral` | ~4.1 GB | Answer generation + query intent classification |

### Verify both models are listed

```bash
docker exec -it $(docker ps -qf "name=ollama") ollama list
# mistral:latest          ...   4.1 GB
# nomic-embed-text:latest ...   274 MB
```

### Smoke-test the embedding model

```bash
curl -s http://localhost:11434/api/embeddings \
  -d '{"model": "nomic-embed-text", "prompt": "Formula One"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Dims: {len(d[\"embedding\"])}')"
# Dims: 768
```

### Smoke-test the LLM

```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model": "mistral", "prompt": "Who won the 2020 F1 championship? One sentence.", "stream": false}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['response'])"
# Lewis Hamilton won the 2020 F1 World Drivers Championship...
```

---

## 8. Verify External API Access

Both APIs are free with no authentication required. Confirm they are
reachable from your machine:

```bash
# Jolpica — historical F1 data (Ergast-compatible, 1950–2024)
curl -s "https://api.jolpi.ca/ergast/f1/2024/results.json?limit=1" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Jolpica OK —', d['MRData']['total'], 'total results')"
# Jolpica OK — 1052 total results

# OpenF1 — live and recent session data
curl -s "https://api.openf1.org/v1/sessions?year=2024" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OpenF1 OK —', len(d), 'sessions')"
# OpenF1 OK — 22 sessions
```

If either call fails or times out, check your network connection or VPN
before continuing.

---

## 9. Initial Git Commit

```bash
git add .
git commit -m "chore: project scaffold, packages, docker, db schema, env"
```

---

## 10. Pre-flight Checklist

Go through every item below. All must be checked before opening `PHASE_1.md`.

**Tools installed:**
- [ ] `git --version` → 2.x+
- [ ] `python3.12 --version` → 3.12.x
- [ ] `uv --version` → 0.4.x+
- [ ] `docker --version` → 26.x+
- [ ] `docker compose version` → V2

**Project structure:**
- [ ] All folders exist: `ingestion/`, `agent/`, `api/`, `db/`, `tests/`
- [ ] All `__init__.py` files exist
- [ ] `pyproject.toml` contains all dependencies
- [ ] `uv sync` completed without errors
- [ ] Package import check passes (section 4.3)

**Environment:**
- [ ] `.env.example` created
- [ ] `.env` created and all variables set

**Docker:**
- [ ] `docker compose ps` shows `postgres` as healthy
- [ ] `docker compose ps` shows `ollama` as running
- [ ] pgvector extension confirmed (`vector` row returned)
- [ ] All four tables confirmed (`\dt` shows chunks, documents, job_runs, sync_state)

**Ollama:**
- [ ] `nomic-embed-text` listed in `ollama list`
- [ ] `mistral` listed in `ollama list`
- [ ] Embedding smoke-test returns `Dims: 768`
- [ ] LLM smoke-test returns a coherent sentence

**External APIs:**
- [ ] Jolpica returns `Jolpica OK — ...`
- [ ] OpenF1 returns `OpenF1 OK — ...`

**Git:**
- [ ] Initial commit made

---

All items checked? **Proceed to `PHASE_1.md`.**

---

## Estimated Setup Time

| Step | Time |
|---|---|
| Install Git, Python, uv, Docker | 10–20 min |
| Create project structure + packages | 5 min |
| `docker compose up` + schema | 2–3 min |
| Pull Ollama models | 10–30 min (network dependent) |
| Smoke tests + pre-flight checklist | 5 min |
| **Total** | **~30–60 min** |
