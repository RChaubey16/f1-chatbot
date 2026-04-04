# F1 Chatbot — A Beginner's Guide to Everything Built So Far

This document explains every piece of the project from the ground up. If you have
never written Python, never used a database, or never built a backend service —
this is for you.

---

## Table of Contents

1. [What Is This Project?](#1-what-is-this-project)
2. [How Does a Chatbot "Know" Things? (RAG Explained)](#2-how-does-a-chatbot-know-things-rag-explained)
3. [The Tech Stack — What Tools Are We Using and Why?](#3-the-tech-stack--what-tools-are-we-using-and-why)
4. [Project Structure — What Lives Where?](#4-project-structure--what-lives-where)
5. [The Configuration Layer — How the App Reads Settings](#5-the-configuration-layer--how-the-app-reads-settings)
6. [The Data Models — How We Represent Information in Code](#6-the-data-models--how-we-represent-information-in-code)
7. [The Extractors — How We Fetch Raw Data](#7-the-extractors--how-we-fetch-raw-data)
8. [The Chunker — How We Break Text Into Bite-Sized Pieces](#8-the-chunker--how-we-break-text-into-bite-sized-pieces)
9. [The Embedder — How We Turn Text Into Numbers](#9-the-embedder--how-we-turn-text-into-numbers)
10. [The Loader — How We Store Everything in the Database](#10-the-loader--how-we-store-everything-in-the-database)
11. [The Pipeline — How Everything Runs Together](#11-the-pipeline--how-everything-runs-together)
12. [The Scheduler — Keeping Live Data Fresh Automatically](#12-the-scheduler--keeping-live-data-fresh-automatically)
13. [The Gemini LLM Client](#13-the-gemini-llm-client)
14. [The Prompts — How We Instruct the LLM](#14-the-prompts--how-we-instruct-the-llm)
15. [The Router — Classifying Query Intent](#15-the-router--classifying-query-intent)
16. [The Retriever — Hybrid Search and RRF](#16-the-retriever--hybrid-search-and-rrf)
17. [The Tools — Structured Data Lookups](#17-the-tools--structured-data-lookups)
18. [The Agent — The Reasoning Loop](#18-the-agent--the-reasoning-loop)
19. [The FastAPI Layer — Serving the Chatbot](#19-the-fastapi-layer--serving-the-chatbot)
20. [The Health Check — Making Sure Everything Is Online](#20-the-health-check--making-sure-everything-is-online)
21. [The Tests — How We Verify Our Code Works](#21-the-tests--how-we-verify-our-code-works)
22. [Docker — Running Services Without Installing Them](#22-docker--running-services-without-installing-them)
23. [The Database Schema — How Data Is Organised on Disk](#23-the-database-schema--how-data-is-organised-on-disk)
24. [Key Python Concepts Used in This Project](#24-key-python-concepts-used-in-this-project)
25. [How to Run the Project](#25-how-to-run-the-project)
26. [Glossary](#26-glossary)

---

## 1. What Is This Project?

This is a chatbot that can answer questions about Formula 1 racing — from the
first championship in 1950 right through to live coverage of the current season.
For example:

- "Who won the 2019 Monaco Grand Prix?"
- "How many championships did Michael Schumacher win?"
- "Tell me about the history of the Silverstone Circuit."
- "What happened in the last race weekend?"

To answer these questions, the chatbot needs a **knowledge base** — a searchable
store of F1 facts. All three phases are now complete:

- **Phase 1 (Static KB):** Historical data 1950–2024 — race results, qualifying,
  standings, driver/constructor profiles, Wikipedia articles.
- **Phase 2 (Live KB):** Current-season data — live session results from the
  OpenF1 API and recent news from Motorsport.com, refreshed automatically on a
  schedule.
- **Phase 3 (RAG Agent + API):** A FastAPI web service that accepts a question,
  classifies its intent, retrieves grounded context via hybrid search, and streams
  an answer from Gemini 2.5 Flash (Google's free-tier cloud API).

Phases 1 and 2 follow the same four ingestion steps:

1. **Fetching** data from external sources (APIs and web scraping)
2. **Breaking** that data into small, digestible chunks
3. **Converting** those chunks into mathematical representations (vectors)
4. **Storing** everything in a database that can search by meaning

---

## 2. How Does a Chatbot "Know" Things? (RAG Explained)

A chatbot by itself (like ChatGPT or Mistral) has general knowledge from its
training data, but it doesn't know specific, detailed F1 statistics. To give it
that knowledge, we use a technique called **RAG** — Retrieval-Augmented
Generation.

Here's how RAG works in plain English:

```
User asks: "Who won the 2019 Monaco Grand Prix?"
         │
         ▼
┌─────────────────────────────────┐
│ Step 1: RETRIEVE                │
│ Search our database for chunks  │
│ of text related to "2019 Monaco │
│ Grand Prix winner"              │
└────────────┬────────────────────┘
             │ Found: "Race: Monaco Grand Prix 2019
             │         P1: Lewis Hamilton (Mercedes)"
             ▼
┌─────────────────────────────────┐
│ Step 2: AUGMENT                 │
│ Attach the retrieved facts to   │
│ the user's question as context  │
└────────────┬────────────────────┘
             │ "Given this context: [Race: Monaco GP 2019,
             │  P1: Lewis Hamilton...], answer: Who won?"
             ▼
┌─────────────────────────────────┐
│ Step 3: GENERATE                │
│ The AI model reads the context  │
│ and writes a natural answer     │
└────────────┬────────────────────┘
             │
             ▼
"Lewis Hamilton won the 2019 Monaco Grand Prix,
 driving for Mercedes."
```

**Phases 1 and 2 build the "RETRIEVE" part** — the searchable knowledge base,
both historical and live. **Phase 3 adds the "AUGMENT" and "GENERATE" parts** —
the router classifies the query, the retriever fetches relevant chunks, and
Gemini 2.5 Flash streams the final answer.

---

## 3. The Tech Stack — What Tools Are We Using and Why?

If you're new to programming, you'll encounter many tool names. Here's what each
one is and why we need it.

### Programming Language

| Tool | What It Is | Why We Use It |
|------|-----------|---------------|
| **Python 3.13** | A programming language known for readability | Most popular language for AI/ML and data work. Huge ecosystem of libraries. |

### Package & Environment Management

| Tool | What It Is | Why We Use It |
|------|-----------|---------------|
| **uv** | A Python package manager (like npm for JavaScript) | Installs libraries, manages virtual environments, runs scripts. Very fast. |
| **pyproject.toml** | A configuration file | Lists all the libraries our project needs (like a shopping list of dependencies). |
| **uv.lock** | A lock file | Records the exact version of every library installed, so everyone gets identical setups. |

### Infrastructure (Things That Run in the Background)

| Tool | What It Is | Why We Use It |
|------|-----------|---------------|
| **Docker** | Runs software in isolated containers | We don't install PostgreSQL or Ollama directly — Docker runs them for us in little virtual boxes. |
| **docker-compose.yml** | A recipe file for Docker | Tells Docker: "start a PostgreSQL database, an Ollama embedder, and the API server, with these settings." |
| **PostgreSQL** | A relational database (stores structured data in tables) | Stores our F1 knowledge — documents and their chunks. |
| **pgvector** | A PostgreSQL add-on for vector search | Lets PostgreSQL search by *meaning*, not just exact text matches. |
| **Ollama** | Runs AI models locally inside Docker | Used **only for embeddings** (`nomic-embed-text`). Converts text into 768-dimensional vectors. All chat/reasoning uses Gemini instead. |
| **Gemini 2.5 Flash** | Google's cloud LLM (free tier) | Used for **all LLM inference** — routing queries and generating answers. Free tier: 10 requests/min, 500 requests/day. |

### Python Libraries (Code Others Wrote That We Reuse)

| Library | What It Does | Where We Use It |
|---------|-------------|-----------------|
| **pydantic** / **pydantic-settings** | Validates data and loads config from `.env` files | `config.py` — loads settings like database URL, chunk sizes |
| **httpx** | Makes HTTP requests (like a browser, but in code) | Extractors — calls the Jolpica/Wikipedia/OpenF1 APIs; `agent/llm.py` — calls the Gemini REST API |
| **tenacity** | Retries failed operations automatically | Extractors + embedder — if an API call fails, try again up to 3 times |
| **xxhash** | Generates fast fingerprints (hashes) of text | Models — creates a unique ID for each document's content for deduplication |
| **langchain-text-splitters** | Splits long text into smaller overlapping chunks | Chunker — breaks documents into pieces that fit the AI's context window |
| **sqlalchemy** | Talks to databases using Python code | Loader — inserts documents and chunks into PostgreSQL |
| **asyncpg** | Fast PostgreSQL driver for async Python | Used by SQLAlchemy under the hood for database connections |
| **structlog** | Structured logging (better than `print()`) | All modules — logs what's happening with timestamps and context |
| **tqdm** | Shows progress bars in the terminal | Pipeline — shows how many documents have been processed |
| **beautifulsoup4** / **lxml** | Parses HTML | News extractor — extracts article body, headline, and date from Motorsport.com pages |
| **apscheduler** | Runs jobs on a schedule | Scheduler — fires the OpenF1 refresh and news scrape jobs every few hours |
| **fastapi** | Web framework for building APIs | `api/` — defines the `/chat` and `/health` HTTP endpoints |
| **uvicorn** | ASGI web server | Runs the FastAPI app (like Apache/nginx but for async Python) |
| **pytest** | Testing framework | Runs our test suite to verify code works |
| **respx** | Mocks HTTP requests in tests | Tests — pretends to be the Jolpica/Wikipedia/OpenF1/Ollama API so tests don't need the internet |

---

## 4. Project Structure — What Lives Where?

```
f1-chatbot/
│
├── .env                          # Secret settings (database password, etc.)
├── .env.example                  # Template showing what .env should look like
├── pyproject.toml                # List of dependencies + project metadata
├── docker-compose.yml            # Instructions for Docker to start services
├── main.py                       # Placeholder entry point (not used yet)
│
├── db/
│   └── schema.sql                # SQL commands that create the database tables
│
├── ingestion/                    # *** PHASES 1 & 2 — The full ingestion system ***
│   ├── __init__.py               # Marks this folder as a Python "package"
│   │
│   ├── core/                     # Shared foundations
│   │   ├── __init__.py
│   │   ├── config.py             # Reads settings from .env
│   │   ├── models.py             # Data shapes (RawDocument, Chunk, etc.)
│   │   └── logging.py            # Logging setup
│   │
│   ├── extractors/               # Step 1: Fetch raw data
│   │   ├── __init__.py
│   │   ├── base.py               # Template that all extractors must follow
│   │   ├── jolpica.py            # [Phase 1] Fetches historical F1 data from Jolpica API
│   │   ├── wikipedia.py          # [Phase 1] Fetches F1 articles from Wikipedia
│   │   ├── openf1.py             # [Phase 2] Fetches live session data from OpenF1 API
│   │   └── news.py               # [Phase 2] Scrapes F1 news from Motorsport.com
│   │
│   ├── transformers/             # Step 2: Break data into chunks
│   │   ├── __init__.py
│   │   └── chunker.py            # Splits text, converts JSON to prose
│   │
│   ├── embedders/                # Step 3: Convert text to numbers (vectors)
│   │   ├── __init__.py
│   │   └── ollama.py             # Calls local Ollama for embeddings
│   │
│   ├── loaders/                  # Step 4: Save to database
│   │   ├── __init__.py
│   │   └── pgvector.py           # Inserts into PostgreSQL (+ url_exists, prune_live)
│   │
│   ├── pipeline.py               # Orchestrates steps 1-4 (static + live phases)
│   ├── scheduler.py              # [Phase 2] APScheduler — auto-refreshes live data
│   └── healthcheck.py            # Verifies all services are running
│
├── Dockerfile                    # [Phase 3] Builds the API container image
│
├── tests/                        # Automated tests (51 total)
│   ├── __init__.py
│   ├── conftest.py               # Shared test setup
│   ├── test_extractors.py        # Tests for all four extractors (10 tests)
│   ├── test_pipeline.py          # Tests for the chunker (6 tests)
│   ├── test_scheduler.py         # [Phase 2] Tests for scheduler jobs (7 tests)
│   ├── test_agent.py             # [Phase 3] Tests for router, retriever, agent (11 tests)
│   ├── test_api.py               # [Phase 3] Tests for FastAPI routes (8 tests)
│   └── test_tools.py             # [Phase 3] Tests for tool functions (9 tests)
│
├── agent/                        # *** PHASE 3 — The reasoning layer ***
│   ├── __init__.py
│   ├── llm.py                    # Gemini API client — generate() + stream(), retry on 429
│   ├── prompts.py                # ROUTER_SYSTEM, ROUTER_PROMPT, SYSTEM_INSTRUCTION, ANSWER_PROMPT
│   ├── router.py                 # Query intent classifier (HISTORICAL/CURRENT/MIXED) via Gemini
│   ├── retriever.py              # Hybrid dense + sparse search with RRF merge
│   ├── tools.py                  # Structured lookups: standings, race results, driver stats
│   └── agent.py                  # Core reasoning loop — routes, retrieves, streams via Gemini
│
├── api/                          # *** PHASE 3 — The web service ***
│   ├── __init__.py
│   ├── main.py                   # FastAPI app with lifespan + scheduler integration
│   ├── schemas.py                # ChatRequest / ChatResponse Pydantic models
│   └── routes/
│       ├── chat.py               # POST /chat + GET /chat/stream (SSE)
│       └── health.py             # GET /health — infra status check
│
├── docs/                         # Planning and summary documents
│   ├── PLAN.md
│   ├── PHASE_1.md
│   ├── PHASE_2.md
│   ├── PHASE_3.md
│   ├── Phase-1-summary.md        # Detailed technical summary — Phase 1
│   ├── Phase-2-summary.md        # Detailed technical summary — Phase 2
│   └── Phase-3-summary.md        # Detailed technical summary — Phase 3
│
└── explain/
    └── notes.md                  # This file!
```

### What is `__init__.py`?

You'll see these empty files everywhere. In Python, a folder only becomes a
**package** (importable from other files) if it contains an `__init__.py`.
Without it, Python won't recognise the folder as part of your project.

Think of it like a door — without `__init__.py`, the room exists but Python
can't walk into it.

---

## 5. The Configuration Layer — How the App Reads Settings

**File:** `ingestion/core/config.py`

Every application has settings that can change between environments — database
passwords, server addresses, tuning parameters. Hardcoding these into your
program is bad practice because:

- You'd need to change code to switch from a test database to a production database
- You might accidentally commit passwords to Git

Instead, we store settings in a `.env` file (which is never committed to Git)
and load them with code.

### The `.env` File

```
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://f1:f1secret@localhost:5433/f1kb

# Ollama (embeddings only — runs inside Docker)
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text

# Gemini (LLM inference — get a free key at https://aistudio.google.com/apikey)
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Ingestion tuning
CHUNK_SIZE_STRUCTURED=512
CHUNK_SIZE_NARRATIVE=800
EMBEDDING_BATCH_SIZE=32
```

Each line is a `KEY=value` pair.

### How `config.py` Reads It

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://f1:f1secret@localhost:5432/f1kb"
    ollama_base_url: str = "http://localhost:11434"
    chunk_size_structured: int = 512
    # ... more settings

settings = Settings()   # <-- reads .env file automatically
```

**What's happening here:**

1. `class Settings` defines what settings we expect and their **types** (`str`,
   `int`, `float`)
2. Each field has a **default value** (used if the `.env` file doesn't set it)
3. `Settings()` automatically reads the `.env` file and fills in the values
4. If `.env` says `CHUNK_SIZE_STRUCTURED=512`, it maps to
   `settings.chunk_size_structured` (Python converts the name from UPPER_CASE
   to lower_case automatically)

The line `settings = Settings()` at module level creates a **singleton** — one
shared settings object that every other file imports:

```python
from ingestion.core.config import settings

print(settings.database_url)  # "postgresql+asyncpg://f1:f1secret@localhost:5433/f1kb"
```

---

## 6. The Data Models — How We Represent Information in Code

**File:** `ingestion/core/models.py`

Before writing any logic, we define the **shape** of our data. This is like
designing a form before filling it out — you decide what fields exist, what type
of data goes in each field, and which fields are required.

### Enums — Fixed Sets of Choices

```python
class SourceType(str, enum.Enum):
    JOLPICA = "jolpica"
    WIKIPEDIA = "wikipedia"
    OPENF1 = "openf1"
    NEWS = "news"
```

An **enum** (short for "enumeration") is a fixed list of valid options. Instead
of using raw strings like `"jolpica"` everywhere (which could be misspelled as
`"jolpika"`), we use `SourceType.JOLPICA`. If you misspell it, Python throws an
error immediately instead of silently using the wrong value.

We have three enums:

| Enum | Options | Purpose |
|------|---------|---------|
| `SourceType` | jolpica, wikipedia, openf1, news | Where the data came from |
| `ContentType` | race_result, qualifying_result, standings, driver_profile, constructor_profile, narrative | What kind of data it is |
| `KBPartition` | static, live | Is it historical (static) or changing (live)? |

### Dataclasses — Structured Containers for Data

```python
@dataclass
class RawDocument:
    source: SourceType
    content_type: ContentType
    partition: KBPartition
    raw_content: str
    metadata: dict = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return xxhash.xxh64(self.raw_content.encode()).hexdigest()
```

A **dataclass** is Python's way of saying "here's a container with named fields."
It's like a labelled box:

```
┌──────────────────────────────────────────┐
│ RawDocument                              │
│                                          │
│  source:       SourceType.JOLPICA        │
│  content_type: ContentType.RACE_RESULT   │
│  partition:    KBPartition.STATIC        │
│  raw_content:  '{"raceName": "Monaco..'  │
│  metadata:     {"year": 2019}            │
│  fingerprint:  "a3f8c2e1b9d04567"        │
│                  (auto-computed)          │
└──────────────────────────────────────────┘
```

#### What Is a Fingerprint?

The `fingerprint` property computes a **hash** of the content using xxhash.
A hash is like a unique ID generated from the content itself:

- `"Lewis Hamilton won"` might hash to `"a3f8c2e1"`
- `"Max Verstappen won"` might hash to `"7b2d9f0e"`
- `"Lewis Hamilton won"` will always hash to `"a3f8c2e1"` — same input, same output

This is how we **deduplicate** — if we've already processed a document with
fingerprint `"a3f8c2e1"`, we skip it instead of storing it twice.

### The Three Models

| Model | Produced By | Consumed By | Purpose |
|-------|------------|-------------|---------|
| `RawDocument` | Extractors | Chunker | One complete document from an API |
| `Chunk` | Chunker | Embedder, Loader | A small piece of text ready for storage |
| `IngestionResult` | Loader | Pipeline | Statistics about what was processed |

---

## 7. The Extractors — How We Fetch Raw Data

Extractors reach out to external APIs over the internet, download data, and
package it into `RawDocument` objects.

### What Is an API?

An **API** (Application Programming Interface) is a way for programs to talk to
each other. When you type a URL like `https://api.jolpi.ca/ergast/f1/drivers.json`
into a browser, you get back structured data (JSON) instead of a web page.

JSON looks like this:
```json
{
  "driverId": "hamilton",
  "givenName": "Lewis",
  "familyName": "Hamilton",
  "nationality": "British"
}
```

Our code does the same thing a browser does — sends a request to a URL and reads
the response — but automatically, in a loop, for thousands of endpoints.

### The Base Extractor — A Contract

**File:** `ingestion/extractors/base.py`

```python
class BaseExtractor(abc.ABC):
    @abc.abstractmethod
    async def extract(self) -> AsyncIterator[RawDocument]:
        ...

    @abc.abstractmethod
    async def health_check(self) -> bool:
        ...
```

This is an **abstract base class** — it says "any extractor must have an
`extract()` method and a `health_check()` method." It doesn't provide the
implementation; it just defines the **contract**. The actual Jolpica and
Wikipedia extractors fill in the details.

This is useful because the pipeline doesn't care which extractor it's using.
It just calls `extractor.extract()` and gets documents back. You can add a new
data source by writing a new extractor that follows this contract.

### The Jolpica Extractor

**File:** `ingestion/extractors/jolpica.py`

Fetches structured F1 data from the Jolpica API (an Ergast-compatible service)
covering 1950–2024.

**What it fetches:**

| Data | API Endpoint | Example URL |
|------|-------------|-------------|
| All F1 drivers ever | `/drivers` | `api.jolpi.ca/ergast/f1/drivers.json` |
| All constructors (teams) | `/constructors` | `api.jolpi.ca/ergast/f1/constructors.json` |
| Race results per year | `/{year}/results` | `api.jolpi.ca/ergast/f1/2019/results.json` |
| Qualifying results per year | `/{year}/qualifying` | `api.jolpi.ca/ergast/f1/2019/qualifying.json` |
| Driver standings per year | `/{year}/driverStandings` | `api.jolpi.ca/ergast/f1/2019/driverStandings.json` |
| Constructor standings per year | `/{year}/constructorStandings` | `api.jolpi.ca/ergast/f1/2019/constructorStandings.json` |

**Key concepts in the code:**

#### Pagination

APIs often limit how many results they return at once (e.g., 100 per request).
To get all 850+ drivers, we need to make multiple requests:

```
Request 1: /drivers.json?limit=100&offset=0    → drivers 1-100
Request 2: /drivers.json?limit=100&offset=100   → drivers 101-200
Request 3: /drivers.json?limit=100&offset=200   → drivers 201-300
...and so on until we've got them all
```

The `_get_all_pages()` method handles this loop automatically.

#### Rate Limiting

If we send 1,000 requests per second, the API server might block us. So we add a
small delay between requests:

```python
await asyncio.sleep(settings.request_delay_seconds)  # waits 0.5 seconds
```

#### Retry with Tenacity

Networks are unreliable. A request might fail because of a timeout or a temporary
server error. Instead of crashing, we retry:

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def _get(self, url, params=None):
    resp = await self._client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()
```

This says: "If `_get` fails, wait 1 second and try again. If it fails again,
wait longer (exponential backoff). Give up after 3 total attempts."

#### Async Generators — `yield` Instead of `return`

Normal functions compute a result and return it all at once. An **async
generator** produces results one at a time using `yield`:

```python
async def extract(self):
    for driver in all_drivers:
        yield RawDocument(...)   # <-- sends one document, then continues
```

This means the pipeline can start processing the first document while the
extractor is still fetching the rest. It's like an assembly line — you don't
wait for all parts to arrive before starting work on the first one.

### The Wikipedia Extractor

**File:** `ingestion/extractors/wikipedia.py`

Fetches narrative (prose) content from 58 hand-picked F1-related Wikipedia
articles.

**Article categories:**

| Category | Count | Examples |
|----------|------:|---------|
| Drivers | 25 | Michael Schumacher, Ayrton Senna, Lewis Hamilton |
| Constructors | 10 | Ferrari, McLaren, Red Bull Racing |
| Circuits | 13 | Monaco, Silverstone, Spa-Francorchamps |
| Topics | 10 | Formula One, History, Regulations, DRS |

**How it works for each article:**

1. Fetch the **introduction** (the first few paragraphs before any section headings)
2. Fetch the **section list** (e.g., "History", "Career", "Championships")
3. For each section:
   - Skip boilerplate like "References" or "External links"
   - Fetch the **wikitext** (Wikipedia's markup language)
   - **Clean** the wikitext by removing templates, links, refs, and HTML

#### Wikitext Cleanup Example

Wikipedia stores articles in a markup language, not plain English:

**Before cleanup:**
```
Hamilton has won {{as of|2024}} seven [[FIA Formula One World Championship|World
Championships]]<ref>{{cite web|url=...}}</ref>, tying [[Michael Schumacher]].
```

**After cleanup:**
```
Hamilton has won seven World Championships, tying Michael Schumacher.
```

The `_clean_wikitext()` method uses **regular expressions** (patterns for finding
and replacing text) to strip all that markup away.

### The OpenF1 Extractor (Phase 2)

**File:** `ingestion/extractors/openf1.py`

Fetches **live** current-season data from `https://api.openf1.org/v1` — a free,
open API that needs no API key.

**What it fetches:**

| Endpoint | What It Contains | Example |
|----------|-----------------|---------|
| `/sessions` | Every session (FP1, qualifying, race) in the season | "Australian GP 2024 — Race" |
| `/drivers` | Current-season driver roster with car numbers | Driver #1, Max Verstappen |
| `/position` | Final race classification per session | P1: Driver #1, P2: Driver #16 |
| `/stints` | Tyre compound used per stint per driver | Driver #44: Medium laps 1–18, Hard laps 19–57 |
| `/pit` | Pit stop timing per driver | Driver #1: lap 20 — 2.4s |

**Incremental sync** is the key feature here. Instead of re-downloading the
entire season every time the scheduler runs, the extractor accepts a `since`
timestamp:

```
First run (since=None):   fetch all sessions from Jan 1, 2024
Second run (since=Apr 1): fetch only sessions after Apr 1 → much faster
```

The scheduler stores the last-sync timestamp in the `sync_state` database table
and passes it to the extractor on subsequent runs.

**Error handling per endpoint:** If fetching `/stints` fails for one session, it
logs a warning and moves on to `/pit` — one bad endpoint doesn't abort the whole
session.

### The News Extractor (Phase 2)

**File:** `ingestion/extractors/news.py`

Scrapes F1 news articles from `https://www.motorsport.com/f1/news/`.

**How it works, step by step:**

```
1. Fetch the index page (the main F1 news listing)
2. Find all article links — looks for <a> tags inside article cards
   (falls back to any link containing /f1/news/ if layout changes)
3. For each article URL:
   a. Check if this URL is already in the database → skip if yes
   b. Fetch the full article page
   c. Extract: headline, publication date, author, body text, keywords
   d. Strip boilerplate: nav bars, ads, "related articles" sections
   e. Yield one RawDocument with the article body as raw_content
```

**Why URL-based dedup instead of fingerprint dedup?**

News articles can be updated after publication (correcting typos, adding
follow-up). If the content changes, the fingerprint changes — so we'd store the
article twice. URLs, however, are stable identifiers. We check the URL first:

```python
# Before fetching: does this URL already exist in the DB?
if await loader.url_exists(url):
    skip  # already ingested this article
```

**Graceful degradation:** If Motorsport.com changes its HTML layout and the
scraper can't find any article links, it logs a warning and returns 0 documents
instead of crashing. The scheduler job keeps running.

---

## 8. The Chunker — How We Break Text Into Bite-Sized Pieces

**File:** `ingestion/transformers/chunker.py`

### Why Chunk?

AI models have a limited **context window** — the amount of text they can
process at once. A 10,000-word Wikipedia article is too big for both:

- **Embedding** — the AI that converts text to a vector works best on short,
  focused passages
- **Retrieval** — when someone asks "Who won Monaco 2019?", we want to find
  the specific paragraph with the answer, not an entire article about Monaco

So we split documents into overlapping chunks:

```
Original document (2,000 characters):
┌───────────────────────────────────────────────────────┐
│ The Monaco Grand Prix is a Formula One motor race     │
│ held each year on the streets of Monte Carlo...       │
│ [lots more text]                                      │
│ ...Hamilton won the 2019 race by 2.6 seconds.         │
└───────────────────────────────────────────────────────┘

After chunking (800 chars each, 80 char overlap):
┌──────────────────────────────┐
│ Chunk 0: "The Monaco Grand   │
│ Prix is a Formula One..."    │
└──────────────────────┬───────┘
                       │ 80 chars overlap
               ┌───────┴──────────────────┐
               │ Chunk 1: "...streets of  │
               │ Monte Carlo. The circuit" │
               └──────────────────┬───────┘
                                  │ overlap
                          ┌───────┴──────────────────┐
                          │ Chunk 2: "...Hamilton won │
                          │ the 2019 race by 2.6..."  │
                          └───────────────────────────┘
```

**Why overlap?** Without overlap, a sentence at the boundary of two chunks
would be cut in half. Overlap ensures that every sentence appears fully in at
least one chunk.

### Two Chunk Sizes

| Data Type | Chunk Size | Overlap | Why |
|-----------|-----------|---------|-----|
| Structured (Jolpica JSON) | 512 chars | 80 chars | Already concise — smaller chunks keep each result focused |
| Narrative (Wikipedia) | 800 chars | 80 chars | Prose needs more context to make sense |

### JSON-to-Prose Conversion

Jolpica data arrives as JSON (a machine-readable format). Storing raw JSON in
the knowledge base would make search harder because the AI would need to
understand JSON syntax. Instead, the chunker converts it to human-readable prose:

**Before (raw JSON):**
```json
{
  "raceName": "Monaco Grand Prix",
  "season": "2019",
  "Results": [
    {"position": "1", "Driver": {"givenName": "Lewis", "familyName": "Hamilton"},
     "Constructor": {"name": "Mercedes"}, "Time": {"time": "1:43:28.437"},
     "points": "25", "status": "Finished"}
  ]
}
```

**After (prose):**
```
Race: Monaco Grand Prix 2019
Circuit: Circuit de Monaco
P1: Lewis Hamilton (Mercedes) — 1:43:28.437 [25 pts]
```

There are five converters — one for each type of structured data (race results,
qualifying, drivers, constructors, standings).

---

## 9. The Embedder — How We Turn Text Into Numbers

**File:** `ingestion/embedders/ollama.py`

### What Is an Embedding?

Computers don't understand text. They understand numbers. An **embedding** is a
list of numbers (a **vector**) that captures the *meaning* of a piece of text.

```
"Lewis Hamilton won the 2019 Monaco GP"
        │
        ▼  (Ollama + nomic-embed-text model)
        │
[0.023, -0.156, 0.891, 0.003, ..., 0.445]   ← 768 numbers
```

The magic of embeddings is that **similar meanings produce similar numbers**.
So:
- "Hamilton won Monaco 2019" and "Who was the winner of the 2019 Monaco race?"
  would have vectors that are **close** to each other in 768-dimensional space
- "Hamilton won Monaco 2019" and "What are the best pizza toppings?" would have
  vectors that are **far apart**

This is how we search by meaning instead of keywords.

### How Ollama Works

**Ollama** is a tool that runs AI models locally on your computer. We use the
`nomic-embed-text` model, which is specifically designed for creating embeddings.
It outputs 768 numbers per input text.

The embedder calls Ollama's API:

```
POST http://localhost:11434/api/embeddings
Body: {"model": "nomic-embed-text", "prompt": "Lewis Hamilton won..."}

Response: {"embedding": [0.023, -0.156, 0.891, ...]}
```

### Batching — Processing Multiple Chunks at Once

Embedding one chunk at a time would be slow. Instead, we process 32 chunks at
a time using Python's `asyncio.gather`, which sends all 32 requests
simultaneously and waits for all of them to finish:

```python
embeddings = await asyncio.gather(
    self._embed_one(chunk_1.content),
    self._embed_one(chunk_2.content),
    ...
    self._embed_one(chunk_32.content),
)
```

This is like having 32 cashiers at a grocery store instead of 1 — the queue
moves 32x faster.

---

## 10. The Loader — How We Store Everything in the Database

**File:** `ingestion/loaders/pgvector.py`

### What Is PostgreSQL + pgvector?

**PostgreSQL** (often called "Postgres") is a database — software that stores
data in tables (like spreadsheets) and lets you query it.

**pgvector** is an add-on that teaches PostgreSQL to store and search vectors.
Without it, Postgres can only search text with exact matches or keyword search.
With pgvector, it can answer "find the 10 chunks whose meaning is closest to
this question."

### How the Loader Works

For each document:

1. **Check for duplicates:** Look up the document's fingerprint in the
   `documents` table. If it exists, skip everything.
2. **Insert the document:** Store the document's metadata (source, type,
   partition) in the `documents` table.
3. **Upsert chunks:** For each chunk, insert it into the `chunks` table. If a
   chunk with the same ID already exists, update its embedding and metadata.

#### What Is an Upsert?

"Upsert" = "Update or Insert." It's a database operation that says:
- "If this row doesn't exist, insert it"
- "If it already exists, update it instead of failing with a duplicate error"

This makes our pipeline **idempotent** — you can run it multiple times without
creating duplicate data.

### The IVFFlat Index

When the database has 10,000 chunks, searching through all of them to find the
closest vectors is slow. An **index** is a data structure that speeds up searches.

**IVFFlat** (Inverted File with Flat compression) works like a library catalogue:
instead of checking every book in the library, you first go to the right section,
then search within that section. It divides vectors into 100 clusters (lists) and
only searches the nearest clusters.

After all data is loaded, we rebuild the index:

```python
await loader.rebuild_index()
```

This is necessary because the index is most accurate when built after all data
is present.

---

## 11. The Pipeline — How Everything Runs Together

**File:** `ingestion/pipeline.py`

The pipeline is the **conductor** that orchestrates all the pieces. It has two
modes: `static` (historical, Phase 1) and `live` (current season, Phase 2).

```
--phase static                         --phase live
──────────────────────────             ──────────────────────────
Jolpica + Wikipedia extractors         OpenF1 + News extractors
        │                                      │
        └──────────────┬────────────────────────┘
                       │
        for each document from extractor:
               │
               ├─ Is fingerprint already in database?
               │   ├─ YES → skip (already processed)
               │   └─ NO  → continue ↓
               │
               ├─ [News only] Is URL already in database? → skip
               │
               ├─ Chunk the document (Chunker)
               │
               ├─ Embed all chunks (OllamaEmbedder)
               │
               └─ Store in database (PgVectorLoader)

After static ingestion only:
    └─ Rebuild the vector search index
```

### The CLI (Command-Line Interface)

You run the pipeline from the terminal:

```bash
# Ingest all historical data (1950-2024)
uv run python -m ingestion.pipeline --phase static

# Ingest only a specific year range
uv run python -m ingestion.pipeline --phase static --start-year 2000 --end-year 2024

# Ingest live current-season data
uv run python -m ingestion.pipeline --phase live

# Ingest live data only from a specific date onwards
uv run python -m ingestion.pipeline --phase live --since 2024-01-01

# Run both phases back to back
uv run python -m ingestion.pipeline --phase all
```

**What does `uv run python -m ingestion.pipeline` mean?**

- `uv run` — "use the project's virtual environment" (so it finds all installed libraries)
- `python -m ingestion.pipeline` — "run the `pipeline` module inside the `ingestion` package"
- `--phase static` — a command-line argument parsed by `argparse`

### Progress Reporting

The pipeline uses `tqdm` to show a progress bar:

```
Ingesting:  47%|████████████▎              | 1,623/3,400 [12:34<14:02, 2.11doc/s]
```

And at the end, prints a summary:

```
Fetched=3400 Skipped=0 Chunks: created=9820 embedded=9820 upserted=9820 Errors=0
```

---

## 12. The Scheduler — Keeping Live Data Fresh Automatically

**File:** `ingestion/scheduler.py`

The pipeline (above) is something you run manually. But live data needs to update
itself automatically — you don't want to remember to run a command every 6 hours
during a race weekend.

The **scheduler** solves this. It runs two jobs on a timer in the background.

### What Is APScheduler?

**APScheduler** (Advanced Python Scheduler) is a library that lets you say "run
this function every N hours." It's like setting a repeating alarm on your phone,
but for code.

### The Two Jobs

| Job | Function | Default interval | What it does |
|-----|----------|-----------------|--------------|
| `openf1_refresh` | `run_openf1_refresh()` | Every 6 hours | Fetches new sessions, stints, pit data from OpenF1 |
| `news_scrape` | `run_news_scrape()` | Every 3 hours | Scrapes latest F1 articles from Motorsport.com |

Both jobs have two safety settings:
- **`max_instances=1`** — never run the same job twice at the same time (if the
  6-hour run is still going when the next trigger fires, the new trigger is ignored)
- **`coalesce=True`** — if multiple triggers were missed (e.g., computer was off),
  only run the job once when it comes back, not once per missed trigger

### Incremental Sync — Not Re-downloading Everything

Every time a job runs, it needs to know "what's new since last time?" This is
tracked in the `sync_state` database table:

```
sync_state table:
┌──────────┬──────────────────────────┐
│ source   │ last_synced_at           │
├──────────┼──────────────────────────┤
│ openf1   │ 2024-04-01 06:00:00 UTC  │
│ news     │ 2024-04-01 03:00:00 UTC  │
└──────────┴──────────────────────────┘
```

Before each job run, the scheduler reads `last_synced_at` and passes it to the
extractor as `since`. The extractor then only fetches data newer than that
timestamp. After a successful run, `last_synced_at` is updated.

### Audit Log — The `job_runs` Table

Every job execution writes a record to the `job_runs` table:

```
job_runs table:
┌────┬──────────────────┬─────────────┬──────────────┬───────────────┬─────────┐
│ id │ job_id           │ started_at  │ finished_at  │ docs_upserted │ success │
├────┼──────────────────┼─────────────┼──────────────┼───────────────┼─────────┤
│  1 │ openf1_refresh   │ 04-01 06:00 │ 04-01 06:03  │ 42            │ true    │
│  2 │ news_scrape      │ 04-01 09:00 │ 04-01 09:01  │ 18            │ true    │
│  3 │ openf1_refresh   │ 04-01 12:00 │ 04-01 12:03  │ 7             │ true    │
└────┴──────────────────┴─────────────┴──────────────┴───────────────┴─────────┘
```

If a job fails (network down, API unavailable), `success=false` and the error
message is recorded in the `errors` column. The scheduler keeps running and will
try again at the next scheduled interval.

### Running the Scheduler

```bash
# Starts the scheduler and runs it forever (until Ctrl+C)
uv run python -m ingestion.scheduler
```

In Phase 3 the scheduler starts automatically inside the FastAPI web server's
lifespan — you no longer need to launch it separately. Running
`docker compose up` brings up postgres, ollama, and the API (which includes the
scheduler) all at once.

---

## 13. The Gemini LLM Client

**File:** `agent/llm.py`

All LLM inference — both routing and answer generation — goes through a thin
wrapper around the Gemini REST API. We use `httpx` directly (no Google SDK
needed) so the dependency footprint stays small.

### Two Functions

```python
async def generate(system: str, prompt: str) -> str:
    """Single blocking call. Used by the router to classify intent."""
    ...

async def stream(system: str, prompt: str) -> AsyncGenerator[str, None]:
    """SSE streaming. Used by the agent for answer generation."""
    ...
```

`generate` calls `generateContent` and waits for the full response.
`stream` calls `streamGenerateContent?alt=sse` and yields tokens as they arrive.

**Why `?alt=sse`?** Without this query parameter, Gemini returns a JSON array
of all chunks at once — not a stream. The `?alt=sse` flag makes it emit
`data: {...}` lines one at a time in Server-Sent Event format.

### Retry on Rate Limits

The Gemini free tier allows 10 requests per minute. If we exceed that limit,
Gemini responds with HTTP 429. Both `generate` and `stream` retry automatically:

```python
_MAX_RETRIES = 3
_RETRY_DELAY = 5.0   # seconds; doubles each attempt: 5s → 10s → 20s

for attempt in range(_MAX_RETRIES):
    response = await client.post(url, json=body)
    if response.status_code == 429:
        await asyncio.sleep(delay)
        delay *= 2
        continue
    response.raise_for_status()
    ...  # success
```

After 3 failed attempts the function raises an error (surfaced as HTTP 500
to the caller). Under normal usage a question needs 2 Gemini calls — one for
routing, one for answering — so staying under 10 RPM is easy.

### Request Format

Every Gemini request has the same JSON shape:

```python
{
    "system_instruction": {"parts": [{"text": system}]},
    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    "generationConfig": {"temperature": 0.1}
}
```

`system_instruction` is the equivalent of a "system prompt" — instructions
given to the model before the conversation starts. `contents` is the actual
user message. `temperature: 0.1` makes answers more deterministic and
factual (0 = always pick the most likely token; 1 = more creative).

---

## 14. The Prompts — How We Instruct the LLM

**File:** `agent/prompts.py`

Before the LLM can do anything useful, we need to tell it exactly what to do
and in what format. We have four prompt constants.

### `ROUTER_SYSTEM` and `ROUTER_PROMPT` — Classify the Question

`ROUTER_SYSTEM` tells Gemini it is a classifier and must respond with exactly
one word. `ROUTER_PROMPT` is the user turn — it includes the query and
explicit rules:

```
Classify this Formula One query. The current year is 2026. The current F1 season is 2026.

Query: {query}

Rules:
- HISTORICAL: about any season before 2026, race history, past champions, driver/team biographies
- CURRENT: about the 2026 season specifically, live standings, upcoming races
- MIXED: requires both historical context and 2026 season data

One word only:
```

**Why include "The current year is 2026"?** Without this, Gemini might classify
"Who won the 2024 championship?" as CURRENT (it doesn't know what year it is).
With it, the model knows 2024 is a past season and correctly returns HISTORICAL.

**Why a one-word reply?** The router parses the LLM's response as an enum
value. A single word is unambiguous and trivial to parse — no risk of the LLM
burying the answer in a sentence.

### `SYSTEM_INSTRUCTION` and `ANSWER_PROMPT` — Answer Grounded in Facts

`SYSTEM_INSTRUCTION` tells Gemini to answer using only the provided context
and not to hallucinate. `ANSWER_PROMPT` is the user turn:

```
Question: {question}

Context:
{context}

Answer the question using only the context above:
```

The `{context}` placeholder is filled at runtime with the retrieved chunks
(and/or tool results). This is the "AUGMENT" step of RAG — the LLM only sees
the facts we explicitly give it, preventing hallucination.

### Why `.replace()` Instead of `.format()`

The chunk content can contain curly braces — e.g. a JSON snippet like
`{"year": 2019}`. If we use Python's `str.format()`, those braces cause a
`KeyError` because `format()` tries to look up a variable called `year`.

We avoid this by using plain string replacement:

```python
# Safe — only replaces the exact placeholder
prompt = ANSWER_PROMPT.replace("{question}", query).replace("{context}", context_str)

# Dangerous — crashes if any chunk contains {anything}
prompt = ANSWER_PROMPT.format(question=query, context=context_str)
```

---

## 15. The Router — Classifying Query Intent

**File:** `agent/router.py`

Before retrieving anything, the agent needs to know *what kind* of question is
being asked — because different questions need different data sources.

### The Three Intent Classes

| Intent | Example questions | What happens next |
|--------|------------------|-------------------|
| `HISTORICAL` | "Who won the 1988 championship?" | Hybrid RAG over the **static** partition only |
| `CURRENT` | "What are the standings today?" | **Tool call** — no RAG retrieval |
| `MIXED` | "How does Hamilton compare to Schumacher?" | RAG over **both** partitions + tool call |

### How Classification Works

```
User question
      │
      ▼
gemini.generate(system=ROUTER_SYSTEM, prompt=ROUTER_PROMPT)
  → calls POST https://generativelanguage.googleapis.com/...
      │
      ▼
Response text: "HISTORICAL"
      │
      ▼
Strip punctuation, uppercase first word → Intent.HISTORICAL
```

The router strips punctuation from the first word of the response (in case
Gemini adds a period), uppercases it, and maps it to the `Intent` enum.
**If the LLM returns anything unexpected** (e.g., `"I think it's HISTORICAL"`
or a network error), the router defaults to `Intent.MIXED` — the safest
fallback because MIXED retrieves from both partitions and never silently
discards relevant data.

### Key Implementation Details

- Calls `agent.llm.generate()` — no HTTP client to manage in `router.py` itself
- No `close()` method needed — `llm.generate()` opens and closes its own `httpx.AsyncClient` per call
- Exceptions are caught and return `Intent.MIXED`, so the router never crashes a request

---

## 16. The Retriever — Hybrid Search and RRF

**File:** `agent/retriever.py`

For `HISTORICAL` and `MIXED` queries, the retriever finds the most relevant
chunks from the knowledge base. It combines **two different search signals**
and merges them with **Reciprocal Rank Fusion (RRF)**.

### Why Two Search Signals?

Neither search method is perfect on its own:

| Method | Strength | Weakness |
|--------|---------|---------|
| **Dense** (pgvector cosine) | Finds semantically similar text — "Who won Monaco?" matches "Lewis Hamilton was victorious at Monte Carlo" | Can miss exact keywords if the embedding space doesn't cluster them |
| **Sparse** (PostgreSQL full-text) | Finds exact keywords reliably — driver names, circuit names, years | Can't understand synonyms or paraphrased questions |

Combining both catches what either alone would miss.

### Dense Retrieval (Vector Search)

```sql
SELECT chunk_id, content, source, content_type, partition, metadata,
       1 - (embedding <=> CAST(:emb AS vector)) AS similarity
FROM chunks
WHERE partition = ANY(:parts) AND embedding IS NOT NULL
ORDER BY embedding <=> CAST(:emb AS vector)
LIMIT :lim
```

The `<=>` operator (provided by pgvector) computes **cosine distance** between
the query embedding and each stored chunk embedding. Lower distance = more
similar.

**Why `CAST(:emb AS vector)` and not `:emb::vector`?** The `::` shorthand for
PostgreSQL casts conflicts with the `asyncpg` driver's named parameter syntax —
asyncpg interprets `::vector` as part of the parameter name and raises a syntax
error. The longer `CAST(... AS vector)` form avoids this ambiguity.

### Sparse Retrieval (Full-Text Search)

```sql
SELECT chunk_id, content, source, content_type, partition, metadata,
       ts_rank(content_tsv, plainto_tsquery('english', :q)) AS rank
FROM chunks
WHERE content_tsv @@ plainto_tsquery('english', :q)
  AND partition = ANY(:parts)
ORDER BY rank DESC
LIMIT :lim
```

`content_tsv` is a `TSVECTOR` column automatically generated from the chunk's
text. `plainto_tsquery` converts the user's question to a keyword search query.

### RRF Merge — Combining the Two Result Lists

Reciprocal Rank Fusion is a simple but effective algorithm for merging
ranked lists. For each chunk that appears in either result list:

```python
score[chunk_id] += 1 / (k + rank + 1)   # k=60 (dampening constant)
```

A chunk ranked 1st gets score `1/61 ≈ 0.016`. A chunk ranked 10th gets
`1/71 ≈ 0.014`. A chunk that appears in **both** lists gets two additive
score contributions — so chunks that score well on both signals rise to the top.

The merged list is sorted by RRF score and truncated to `top_k` (default 6).

```
Dense results:     [A, B, C, D, E, F]
Sparse results:    [C, A, G, H, I, J]

After RRF:
  A: 1/61 + 1/62 = 0.032   (ranked 1st in both)
  C: 1/63 + 1/61 = 0.032   (3rd dense, 1st sparse)
  B: 1/62           = 0.016  (only in dense)
  G: 1/63           = 0.016  (only in sparse)
  ...
```

---

## 17. The Tools — Structured Data Lookups

**File:** `agent/tools.py`

For `CURRENT` and `MIXED` queries, vector search over narrative text is not
enough — we need precise, up-to-date structured data. The tools module provides
three async functions that bypass the retriever entirely.

### `get_current_standings() -> str`

```
GET https://api.openf1.org/v1/position?session_key=latest
```

Returns the current race position for every driver:

```
1. Driver #44 — P1
2. Driver #1 — P2
3. Driver #16 — P3
...
```

Falls back to `"Current standings unavailable."` if the API is unreachable.

### `get_race_results(year: int, gp: str) -> str`

```
GET https://api.jolpi.ca/ergast/f1/{year}/results.json?limit=100
```

Filters races where `gp` (e.g., `"monaco"`) appears in the race name, circuit
ID, or locality. Returns the top 3 finishers:

```
Results for 2019 Monaco:
1. Hamilton (Mercedes)
2. Bottas (Mercedes)
3. Verstappen (Red Bull)
```

### `get_driver_stats(driver_name: str) -> str`

```sql
SELECT content FROM chunks
WHERE content_type = 'driver_profile'
  AND metadata->>'name' ILIKE '%hamilton%'
LIMIT 1
```

Returns the full driver profile text chunk already stored in the knowledge base
from Phase 1 ingestion. Falls back gracefully if no match is found.

---

## 18. The Agent — The Reasoning Loop

**File:** `agent/agent.py`

The `Agent` class orchestrates everything: it receives a question, decides how
to answer it, gathers the relevant information, and streams the response.

### The `_prepare_context` Step (shared by both endpoints)

```
1. Router.classify(query)             → Intent (HISTORICAL / CURRENT / MIXED)
2. Retriever.retrieve(query, parts)   → list[RetrievedChunk]  (if not CURRENT)
3. get_current_standings()            → standings string       (if CURRENT or MIXED)
4. Build context string               → truncated to 12,000 chars
```

The context string assembles the retrieved chunks and/or standings into a
single block of text that gets injected into `ANSWER_PROMPT`.

### `async run(query)` — Streaming Mode

```
Build prompt with ANSWER_PROMPT.replace("{question}", query)
                                .replace("{context}", context_str)
      │
      ▼
gemini.stream(system=SYSTEM_INSTRUCTION, prompt=prompt)
  → calls POST https://generativelanguage.googleapis.com/.../streamGenerateContent?alt=sse
      │
      ▼
for each SSE line:
    parse JSON → yield token string
    until stream ends
```

This is how `GET /chat/stream` works — each token from Gemini is yielded
immediately, so the browser starts rendering the answer before generation is
done. Typical latency: ~5 seconds for a full answer.

### `async run_sync(query)` — Non-Streaming Mode

Calls `_prepare_context`, then collects all streamed tokens into a single
string. Returns a structured dict:

```python
{
    "answer": "Lewis Hamilton won the 2019 Monaco Grand Prix...",
    "sources": [{"content_type": "race_result", "source": "jolpica", ...}],
    "intent": "HISTORICAL",
    "latency_ms": 2340.5
}
```

### Resource Management

The `Retriever` (a database connection pool) holds open connections.
`Agent.close()` shuts it down. The FastAPI lifespan calls `close()` on
shutdown so no connections leak. The Gemini client (`agent/llm.py`) opens a
fresh `httpx.AsyncClient` per request — no persistent connection to manage.

---

## 19. The FastAPI Layer — Serving the Chatbot

**Files:** `api/main.py`, `api/schemas.py`, `api/routes/chat.py`,
`api/routes/health.py`

### What Is FastAPI?

**FastAPI** is a Python web framework for building HTTP APIs. It handles:
- Routing (which function to call for `POST /chat`)
- Request parsing (reading the JSON body)
- Response serialisation (converting Python dicts to JSON)
- Validation (rejecting badly-formed requests before they reach your code)

It's async-native, which means it plays nicely with our async agent and
retriever code.

### The Endpoints

#### `POST /chat` — Full answer as JSON

```
Request body:
{
  "query": "Who won the 1988 championship?",
  "max_chunks": 6
}

Response:
{
  "answer": "Ayrton Senna won the 1988 Formula One World Championship...",
  "sources": [{"content_type": "standings", "source": "jolpica", ...}],
  "intent": "HISTORICAL",
  "latency_ms": 3210.4
}
```

#### `GET /chat/stream?query=...` — Server-Sent Events (SSE)

```
Response headers: Content-Type: text/event-stream

data: {"token": "Ayrton"}
data: {"token": " Senna"}
data: {"token": " won"}
...
data: [DONE]
```

**What are Server-Sent Events?** SSE is a browser standard for receiving a
stream of events from a server over a single HTTP connection. Unlike WebSockets,
it's one-directional (server → client), which is all we need for a chatbot
response. The browser receives tokens one at a time and can display them as they
arrive, giving the "typing" effect.

#### `GET /health` — Infrastructure Status

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

Checks postgres (runs a `SELECT COUNT(*)`), checks ollama (calls the embedder's
`health_check()`), and reads `sync_state` for the last live refresh timestamp.
**Never raises HTTP 500** — infra failures show as `"error"` in their field so
the response always arrives and is parseable.

### The Lifespan — Startup and Shutdown

FastAPI's `lifespan` context manager replaces the old `on_event("startup")`
pattern. It runs setup code before the server starts accepting requests, and
teardown code after the last request is served:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = Agent()       # create agent (opens DB pool + HTTP client)
    scheduler = create_scheduler()
    scheduler.start()               # start background scheduler
    app.state.scheduler = scheduler
    yield                           # server runs here
    scheduler.shutdown(wait=False)  # stop scheduler on shutdown
    await app.state.agent.close()   # close DB pool + HTTP client
```

The agent is stored on `app.state` so the same instance (and its connection
pool) is reused across all requests — no reconnection overhead per request.

---

## 20. The Health Check — Making Sure Everything Is Online

**File:** `ingestion/healthcheck.py`

Before running a 30-minute ingestion job, it's wise to check that all external
services are reachable. The health check verifies four things:

| Check | What It Tests | How |
|-------|-------------|-----|
| PostgreSQL | Can we connect? Is pgvector installed? | Runs `SELECT 1` and checks for the `vector` extension |
| Ollama | Is it running? Is the right model loaded? | Hits `/api/tags` and checks for `nomic-embed-text` |
| Jolpica API | Is the API reachable? | Fetches one driver (`/drivers.json?limit=1`) |
| Wikipedia API | Is Wikipedia's API up? | Calls `action=query&meta=siteinfo` |

If any check fails, it exits with error code 1 and logs which service is down.

```bash
uv run python -m ingestion.healthcheck
# Output:
# healthcheck.result  service=PostgreSQL    status=OK
# healthcheck.result  service=Ollama        status=OK
# healthcheck.result  service=Jolpica API   status=OK
# healthcheck.result  service=Wikipedia API status=OK
# healthcheck.all_passed
```

---

## 21. The Tests — How We Verify Our Code Works

### What Is Automated Testing?

Instead of manually running the program and eyeballing the output, we write
small programs that **automatically** check that our code behaves correctly.
If someone later changes the code and accidentally breaks something, the tests
will catch it.

### Our Test Suite

**Run with:** `uv run python -m pytest tests/ -v`

We have **51 tests** across six files, all passing.

#### `tests/test_extractors.py` — 10 Tests

These test all four extractors **without hitting the real APIs**. Instead, we use
**mocking** (via the `respx` library) to intercept HTTP requests and return fake
responses:

```python
@respx.mock
async def test_jolpica_extracts_drivers():
    # Set up fake API response
    respx.get("https://api.jolpi.ca/ergast/f1/drivers.json").mock(
        return_value=httpx.Response(200, json={...fake data...})
    )

    # Run the extractor — it thinks it's talking to the real API
    extractor = JolpicaExtractor(start_year=2024, end_year=2024)
    docs = [doc async for doc in extractor.extract()]

    # Verify the output
    assert docs[0].source == SourceType.JOLPICA
```

**Why mock?**
- Tests run in milliseconds instead of minutes
- Tests work without an internet connection
- Tests are deterministic (same fake data every time)

**Phase 1 extractor tests (Jolpica + Wikipedia):**

| Test | What It Verifies |
|------|-----------------|
| `test_jolpica_extracts_drivers` | Jolpica extractor produces documents with correct source, type, and content |
| `test_jolpica_fingerprint_changes_with_content` | Different content produces different fingerprints |
| `test_wikipedia_extracts_sections` | Wikipedia extractor yields narrative documents with proper metadata |
| `test_wikipedia_clean_wikitext` | Wikitext cleanup strips templates, links, and refs correctly |

**Phase 2 extractor tests (OpenF1 + News):**

| Test | What It Verifies |
|------|-----------------|
| `test_openf1_extracts_sessions` | OpenF1 extractor yields a session doc with correct `session_key` and `partition=LIVE` |
| `test_openf1_extracts_stints` | Stint narrative contains tyre compound names |
| `test_openf1_returns_empty_on_no_sessions` | Returns 0 docs without error when API returns empty list |
| `test_news_extracts_articles` | News extractor yields articles with correct source, URL, and body |
| `test_news_skips_known_urls` | Injecting `url_exists_fn=always_true` causes all articles to be skipped |
| `test_news_returns_empty_on_broken_layout` | Index page with no recognisable links yields 0 docs (not a crash) |

#### `tests/test_pipeline.py` — 6 Tests

These test the chunker without any mocking (it's pure logic, no network):

| Test | What It Verifies |
|------|-----------------|
| `test_chunk_race_result` | Race JSON becomes prose containing "Monaco Grand Prix" and driver positions |
| `test_chunk_driver_profile` | Driver JSON becomes "Lewis Hamilton", "British" |
| `test_chunk_wikipedia` | Narrative text is split into chunks |
| `test_chunk_ids_use_fingerprint` | Chunk IDs follow `{fingerprint}_{index}` format |
| `test_idempotent_fingerprint` | Same content always produces the same fingerprint |
| `test_different_content_different_fingerprint` | Different content never collides |

#### `tests/test_scheduler.py` — 7 Tests (Phase 2)

These test the scheduler **without starting a real database or running real jobs**.
They use Python's `unittest.mock` to replace the database calls and pipeline
components with fake versions:

| Test | What It Verifies |
|------|-----------------|
| `test_scheduler_registers_both_jobs` | `create_scheduler()` registers `openf1_refresh` and `news_scrape` |
| `test_scheduler_jobs_have_max_instances_one` | Both jobs have `max_instances=1` (no overlap) |
| `test_scheduler_jobs_have_coalesce` | Both jobs have `coalesce=True` (missed triggers collapsed) |
| `test_scheduler_interval_matches_config` | Trigger intervals match the values in `settings` |
| `test_run_openf1_refresh_writes_job_run` | Job writes a `job_runs` row with `success=True` on clean run |
| `test_run_news_scrape_writes_job_run` | Same for the news job |
| `test_run_openf1_refresh_records_failure` | When DB throws an error, job writes `success=False` and records the error |

#### `tests/test_agent.py` — 11 Tests (Phase 3)

These test the router, retriever RRF logic, and agent intent routing **without
starting Gemini or PostgreSQL**. Gemini calls are patched with `unittest.mock`;
DB calls are also patched.

| Test | What It Verifies |
|------|-----------------|
| `test_retriever_rrf_merge` | Chunks in both dense and sparse results get higher RRF scores than single-list chunks |
| `test_retriever_rrf_empty_dense` | RRF works correctly when dense results are empty |
| `test_retriever_rrf_empty_sparse` | RRF works correctly when sparse results are empty |
| `test_retriever_rrf_both_empty` | RRF returns empty list when both result lists are empty |
| `test_router_classifies_historical` | Mocked Gemini returns `"HISTORICAL"` → `Intent.HISTORICAL` |
| `test_router_classifies_current` | Mocked Gemini returns `"CURRENT"` → `Intent.CURRENT` |
| `test_router_defaults_to_mixed_on_unknown` | Mocked Gemini returns `"BLAH"` → falls back to `Intent.MIXED` |
| `test_router_defaults_to_mixed_on_exception` | Gemini raises an exception → falls back to `Intent.MIXED` |
| `test_agent_historical_uses_static_partition` | `HISTORICAL` intent → retriever called with `partitions=["static"]` |
| `test_agent_current_skips_retriever` | `CURRENT` intent → retriever never called; `get_current_standings` awaited |
| `test_agent_mixed_uses_both_partitions` | `MIXED` intent → retriever called with `partitions=["static", "live"]` |

#### `tests/test_api.py` — 8 Tests (Phase 3)

These test the FastAPI routes using `httpx.AsyncClient` with `ASGITransport`.
Because `ASGITransport` does not trigger the FastAPI lifespan, the agent is set
directly on `app.state.agent` before each test — no real Gemini or database
connection needed.

| Test | What It Verifies |
|------|-----------------|
| `test_post_chat_happy_path` | POST /chat returns answer, sources, intent, latency_ms |
| `test_post_chat_max_chunks_passthrough` | `max_chunks` is forwarded to the agent |
| `test_post_chat_default_max_chunks` | Omitting `max_chunks` uses the default (6) |
| `test_post_chat_missing_query` | Missing `query` field returns HTTP 422 |
| `test_get_stream_sse_format` | GET /chat/stream returns `text/event-stream` with `data: {"token": ...}` lines |
| `test_get_stream_missing_query` | Missing `?query=` returns HTTP 422 |
| `test_health_ok` | GET /health returns `status: ok` with postgres and ollama both ok |
| `test_health_postgres_error` | Postgres exception → `status: error` in the response body |

#### `tests/test_tools.py` — 9 Tests (Phase 3)

These test `get_current_standings` and `get_race_results` with `respx` HTTP
mocks — the real OpenF1 and Jolpica APIs are never called.

| Test | What It Verifies |
|------|-----------------|
| `test_standings_success` | Returns a numbered standings list |
| `test_standings_empty` | Empty API response → graceful fallback string |
| `test_standings_http_error` | HTTP 500 → fallback string |
| `test_standings_network_error` | Connection error → fallback string |
| `test_race_results_success` | Returns top-3 finishers for matching race |
| `test_race_results_match_by_locality` | Matches race by locality (e.g. "Monte Carlo") |
| `test_race_results_no_match` | No matching GP → fallback string |
| `test_race_results_http_error` | HTTP error → fallback string |
| `test_race_results_malformed_response` | Unexpected JSON shape → fallback string |

#### `tests/conftest.py` — Shared Setup

Automatically initialises structured logging before every test. `conftest.py` is
a special pytest file — fixtures defined here are available to all test files.

---

## 22. Docker — Running Services Without Installing Them

### What Is Docker?

Imagine you need PostgreSQL and Ollama running on your machine. You could:
1. Download installers, configure paths, manage versions, troubleshoot conflicts...
2. Or just tell Docker: "run these two services with these settings"

Docker runs software in **containers** — lightweight, isolated environments that
include everything the software needs. It's like running each service in its own
mini-computer.

### Our `docker-compose.yml`

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16     # PostgreSQL 16 with pgvector pre-installed
    ports:
      - "5433:5432"                   # Access on port 5433 from your machine
    volumes:
      - ./db/schema.sql:/docker-entrypoint-initdb.d/001-schema.sql
        # ^ Automatically creates tables when the container first starts

  ollama:
    image: ollama/ollama:latest       # Latest Ollama release — embeddings only
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama   # Persist downloaded AI models
    healthcheck:
      test: ["CMD", "ollama", "list"] # Image has no curl; use ollama CLI instead
      interval: 30s
      timeout: 10s
      retries: 3

  api:
    build: .                          # Builds from the Dockerfile in the project root
    env_file: .env                    # Loads GEMINI_API_KEY and other secrets
    environment:
      # Override localhost URLs from .env with Docker service hostnames.
      # Inside a container, "localhost" means the container itself — not the host machine.
      DATABASE_URL: postgresql+asyncpg://f1:f1secret@postgres:5432/f1kb
      OLLAMA_BASE_URL: http://ollama:11434
    ports:
      - "8000:8000"                   # FastAPI available at http://localhost:8000
    depends_on:
      postgres:
        condition: service_healthy
      ollama:
        condition: service_healthy
```

**Why the `environment:` block?** The `.env` file uses `localhost` URLs because
that's where things live on your development machine. But inside the `api`
container, `localhost` refers to the container itself — not PostgreSQL or Ollama.
Docker service names (`postgres`, `ollama`) are the correct hostnames for
inter-container communication. The `environment:` block overrides the `.env`
values with the correct internal hostnames, while still letting `.env` supply
`GEMINI_API_KEY` and other settings via `env_file:`.

### The `Dockerfile`

```dockerfile
FROM python:3.13-slim
WORKDIR /app

# gcc and python3-dev are required because aiohttp has no pre-built wheel
# for linux/aarch64 + Python 3.13 and must compile from source on ARM64 Macs.
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

# Stage 1: install dependencies only (layer is cached when only source files change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Stage 2: copy source code and install the project itself
COPY . .
RUN uv sync --frozen

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Why two `uv sync` stages?** The first stage (`--no-install-project`) installs
all dependencies but not the project package itself. Because it only needs
`pyproject.toml` and `uv.lock`, Docker caches this layer — if you only change
Python source files (not dependencies), Docker reuses the cached layer and skips
the long dependency install. The second `uv sync` (after `COPY . .`) installs
the project package itself, which requires the source files to be present.

**Key commands:**
```bash
docker compose up -d       # Start all three services in the background
docker compose down        # Stop all services
docker compose logs -f     # Watch live logs
docker compose logs api    # Logs for just the API container
```

### Why Port 5433 Instead of 5432?

PostgreSQL normally runs on port 5432. We use 5433 to avoid conflicts if you
already have PostgreSQL installed on your machine. The container internally still
uses 5432, but Docker maps it to 5433 on your host.

### Why Is Ollama CPU-Only in Docker?

On macOS, Docker containers run inside a Linux virtual machine and cannot access
the Mac's Metal GPU. This means Ollama runs CPU-only inside Docker — large
language models (3B+ parameters) would take minutes per response. This is why
we use **Gemini** (a cloud API) for all LLM inference and reserve Ollama only
for embeddings, which are much smaller and fast even on CPU.

---

## 23. The Database Schema — How Data Is Organised on Disk

**File:** `db/schema.sql`

A **schema** defines the structure of your database tables — what columns exist,
what types they hold, and what constraints apply.

### The `documents` Table

```sql
CREATE TABLE documents (
    id            SERIAL PRIMARY KEY,       -- auto-incrementing ID
    fingerprint   TEXT UNIQUE NOT NULL,      -- xxhash of content (for dedup)
    source        TEXT NOT NULL,             -- "jolpica" or "wikipedia"
    content_type  TEXT NOT NULL,             -- "race_result", "narrative", etc.
    partition     TEXT NOT NULL,             -- "static" or "live"
    metadata      JSONB DEFAULT '{}',       -- flexible key-value data
    created_at    TIMESTAMPTZ DEFAULT NOW()  -- when it was inserted
);
```

Think of this as a spreadsheet:

| id | fingerprint | source | content_type | partition | metadata | created_at |
|----|-------------|--------|-------------|-----------|----------|-----------|
| 1 | a3f8c2e1... | jolpica | race_result | static | {"year": 2019} | 2026-04-01 |
| 2 | 7b2d9f0e... | wikipedia | narrative | static | {"article": "Monaco"} | 2026-04-01 |

### The `chunks` Table

```sql
CREATE TABLE chunks (
    chunk_id        TEXT PRIMARY KEY,          -- "{fingerprint}_{index}"
    doc_fingerprint TEXT REFERENCES documents(fingerprint),
    content         TEXT NOT NULL,             -- the actual text
    source          TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    partition       TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}',
    embedding       vector(768),              -- THE VECTOR (768 floats)
    content_tsv     TSVECTOR                  -- full-text search index
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

The crucial column is `embedding vector(768)` — this stores the 768-dimensional
vector from Ollama. The `content_tsv` column is automatically generated for
keyword-based full-text search (used in Phase 3 for hybrid retrieval).

### Indexes

```sql
-- Vector similarity search (find nearest neighbours)
CREATE INDEX chunks_embedding_idx ON chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Full-text keyword search
CREATE INDEX chunks_content_tsv_idx ON chunks USING gin(content_tsv);
```

---

## 24. Key Python Concepts Used in This Project

### `async` / `await` — Doing Things Concurrently

Most of our code is **async** (asynchronous). Here's why:

**Without async (synchronous):**
```
Fetch driver 1 from API     ── 200ms waiting ──→ Got it
Fetch driver 2 from API     ── 200ms waiting ──→ Got it
Fetch driver 3 from API     ── 200ms waiting ──→ Got it
Total: 600ms
```

**With async (asynchronous):**
```
Fetch driver 1 ──→
Fetch driver 2 ──→  (all waiting at the same time)
Fetch driver 3 ──→
Total: ~200ms
```

When Python hits `await` (like `await self._client.get(url)`), it says "I'm
waiting for a network response — go do something else in the meantime." This is
especially powerful when making hundreds of API calls.

Key syntax:
```python
async def my_function():      # "this function can pause and resume"
    result = await some_io()  # "pause here until the I/O completes"
```

### Virtual Environments

Python libraries are installed globally by default, which can cause conflicts
between projects. A **virtual environment** is an isolated space where each
project has its own set of libraries.

`uv` manages this automatically. When you run `uv run python ...`, it uses the
project's virtual environment (stored in the `.venv/` folder).

### Decorators — `@something` Above a Function

```python
@retry(stop=stop_after_attempt(3))
async def _get(self, url):
    ...
```

A **decorator** wraps a function with extra behaviour. The `@retry` decorator
says "if `_get` fails, automatically retry it." You don't need to write the retry
loop yourself — the decorator handles it.

### Type Hints — `def foo(x: int) -> str:`

```python
async def embed_batch(self, chunks: list[Chunk]) -> list[Chunk]:
```

Type hints tell both humans and tools what type of data a function expects and
returns. They're optional in Python (the code works without them), but they:

- Make code easier to understand
- Enable IDE autocompletion
- Allow tools to catch bugs before you run the code

### `from __future__ import annotations`

You'll see this at the top of most files. It's a technical detail that makes type
hints like `list[float] | None` work in older Python versions. It tells Python
to treat all type hints as strings (evaluated lazily) rather than executing them
immediately.

---

## 25. How to Run the Project

### First-Time Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd f1-chatbot

# 2. Add your Gemini API key to .env
#    Get a free key at https://aistudio.google.com/apikey
echo "GEMINI_API_KEY=your_key_here" >> .env

# 3. Install Python dependencies (needed to run ingestion locally)
uv sync --extra dev

# 4. Start Docker services (PostgreSQL + Ollama + API)
docker compose up -d

# 5. Download the Ollama embedding model (one-time, ~270 MB)
docker compose exec ollama ollama pull nomic-embed-text

# 6. Verify everything is working
uv run python -m ingestion.healthcheck
```

### Running the Ingestion Pipeline

```bash
# Full static run (1950-2024) — takes 30-45 minutes
uv run python -m ingestion.pipeline --phase static

# Quick static test run (just one year)
uv run python -m ingestion.pipeline --phase static --start-year 2024 --end-year 2024

# Live ingestion (current-season data from OpenF1 + news)
uv run python -m ingestion.pipeline --phase live

# Live ingestion from a specific date
uv run python -m ingestion.pipeline --phase live --since 2024-01-01
```

### Running the API Server (Phase 3)

```bash
# Option A: via Docker Compose (recommended — postgres + ollama + api together)
docker compose up -d

# Option B: locally (useful during development)
uv run uvicorn api.main:app --reload

# Check it's running
curl http://localhost:8000/health

# Ask a question (non-streaming)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Who won the 1988 championship?"}'

# Ask a question (streaming SSE)
curl -N "http://localhost:8000/chat/stream?query=What+are+the+current+standings"
```

The API starts the background scheduler automatically — no need to run
`ingestion.scheduler` separately.

### Running Tests

```bash
# Install dev dependencies (pytest, respx, etc.) if not already done
uv sync --extra dev

# Run all 51 tests with verbose output
uv run python -m pytest tests/ -v
```

### Stopping Everything

```bash
docker compose down   # Stops PostgreSQL, Ollama, and the API
```

---

## 26. Glossary

| Term | Definition |
|------|-----------|
| **API** | A way for programs to communicate. Our code calls F1 APIs to get data. |
| **APScheduler** | A Python library for running functions on a repeating schedule (e.g. every 6 hours). |
| **Async** | A programming style where the program can do other work while waiting for slow operations (like network requests). |
| **Chunk** | A small piece of text (512-800 characters) that can be embedded and searched independently. |
| **CLI** | Command-Line Interface — running a program by typing commands in a terminal. |
| **Container** | An isolated environment (via Docker) that runs a piece of software with all its dependencies. |
| **Dataclass** | A Python feature that creates a class with named fields and auto-generated constructor. Like a struct in C or a record in Java. |
| **Decorator** | The `@something` syntax above a function that adds extra behaviour (like retrying on failure). |
| **Deduplication (dedup)** | Ensuring the same data isn't stored twice. We use content fingerprints. |
| **Docker** | Software that runs applications in isolated containers. |
| **Embedding** | A list of numbers (vector) that represents the meaning of text. Similar texts have similar vectors. |
| **Enum** | A fixed set of named constants (e.g., `SourceType.JOLPICA`). Prevents typos. |
| **Fingerprint** | A hash (unique ID) generated from content. Same content always produces the same fingerprint. |
| **Hash** | A function that converts input of any size to a fixed-size output. Used for dedup and integrity checks. |
| **Idempotent** | An operation that produces the same result no matter how many times you run it. Our pipeline is idempotent. |
| **Incremental sync** | Fetching only data that is newer than the last successful run, rather than re-downloading everything. |
| **Index** | A database structure that speeds up searches (like a book's index speeds up finding topics). |
| **IVFFlat** | A type of vector index that clusters vectors for faster approximate nearest-neighbour search. |
| **JSON** | JavaScript Object Notation — a text format for structured data, like `{"key": "value"}`. |
| **Mock** | In testing, a fake version of something (like a fake API) that returns predetermined responses. |
| **OpenF1** | A free, open REST API providing live Formula 1 data — sessions, positions, stints, and pit stops. |
| **Pagination** | Fetching large datasets in small pages (e.g., 100 items at a time). |
| **Partition** | A label on each document/chunk marking whether it belongs to historical (`static`) or live (`live`) data. |
| **pgvector** | A PostgreSQL extension that adds support for storing and searching vectors. |
| **Pipeline** | A sequence of processing steps where each step's output feeds into the next. |
| **PostgreSQL** | An open-source relational database that stores data in tables. |
| **RAG** | Retrieval-Augmented Generation — a technique where an AI retrieves relevant facts before generating an answer. |
| **Rate Limiting** | Adding delays between API calls to avoid overwhelming the server. |
| **Schema** | The structure of a database — what tables exist and what columns they have. |
| **Scheduler** | A background process that runs jobs (like data refresh) automatically at regular intervals. |
| **Scraping** | Extracting data from web pages by parsing their HTML. Used by the News extractor. |
| **Singleton** | A design pattern where only one instance of something exists. Our `settings` object is a singleton. |
| **SQL** | Structured Query Language — the language used to create tables, insert data, and query databases. |
| **Upsert** | "Update or Insert" — insert a row if it doesn't exist, update it if it does. |
| **Vector** | A list of numbers. In our case, 768 numbers that represent the meaning of text. |
| **Virtual Environment** | An isolated Python installation for a project, preventing library conflicts. |
| **Wikitext** | Wikipedia's markup language, which includes templates, links, and refs that we clean before storing. |
| **yield** | A Python keyword that produces values one at a time from a generator function, instead of returning all at once. |
| **Agent** | The core reasoning loop (Phase 3). Orchestrates routing, retrieval, tool calls, and LLM streaming. |
| **Dense retrieval** | Vector similarity search — finds chunks whose embedding is geometrically close to the query embedding. |
| **FastAPI** | A Python web framework for building async HTTP APIs with automatic request validation. |
| **Intent** | The classified purpose of a user's question: `HISTORICAL`, `CURRENT`, or `MIXED`. |
| **Lifespan** | FastAPI's startup/shutdown hook — runs setup before the server starts and teardown after it stops. |
| **Gemini 2.5 Flash** | Google's cloud LLM used for all reasoning: query classification (routing) and answer generation. Free tier: 10 RPM, 500 req/day. |
| **RRF (Reciprocal Rank Fusion)** | An algorithm that merges two ranked result lists by summing `1/(k+rank)` scores. Rewards chunks that rank well on both signals. |
| **Router** | The component that classifies a user's question into an intent class before any retrieval happens. |
| **Retriever** | The component that fetches the most relevant knowledge-base chunks for a given query using hybrid search. |
| **SSE (Server-Sent Events)** | A browser standard for receiving a stream of events over a single HTTP connection. Used by `GET /chat/stream`. |
| **Sparse retrieval** | Full-text keyword search — finds chunks that contain the exact words from the query. |
| **Streaming** | Yielding LLM tokens to the client as they are generated, rather than waiting for the full answer. |
| **System prompt** | Instructions given to the LLM before the user's message. `ROUTER_SYSTEM` instructs Gemini to classify intent; `SYSTEM_INSTRUCTION` tells it to answer only from the provided context. |
| **uvicorn** | An ASGI web server that runs the FastAPI application. |
