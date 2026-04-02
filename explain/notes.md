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
12. [The Health Check — Making Sure Everything Is Online](#12-the-health-check--making-sure-everything-is-online)
13. [The Tests — How We Verify Our Code Works](#13-the-tests--how-we-verify-our-code-works)
14. [Docker — Running Services Without Installing Them](#14-docker--running-services-without-installing-them)
15. [The Database Schema — How Data Is Organised on Disk](#15-the-database-schema--how-data-is-organised-on-disk)
16. [Key Python Concepts Used in This Project](#16-key-python-concepts-used-in-this-project)
17. [How to Run the Project](#17-how-to-run-the-project)
18. [Glossary](#18-glossary)

---

## 1. What Is This Project?

This is a chatbot that can answer questions about Formula 1 racing history — from
the very first championship in 1950 to 2024. For example:

- "Who won the 2019 Monaco Grand Prix?"
- "How many championships did Michael Schumacher win?"
- "Tell me about the history of the Silverstone Circuit."

To answer these questions, the chatbot needs a **knowledge base** — a searchable
store of F1 facts. Phase 1 (what we've built so far) is entirely about building
that knowledge base by:

1. **Fetching** data from external sources (F1 APIs and Wikipedia)
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

**Phase 1 builds the "RETRIEVE" part** — the searchable knowledge base. Phases 2
and 3 (not built yet) will add the "AUGMENT" and "GENERATE" parts.

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
| **docker-compose.yml** | A recipe file for Docker | Tells Docker: "start a PostgreSQL database and an Ollama AI server, with these settings." |
| **PostgreSQL** | A relational database (stores structured data in tables) | Stores our F1 knowledge — documents and their chunks. |
| **pgvector** | A PostgreSQL add-on for vector search | Lets PostgreSQL search by *meaning*, not just exact text matches. |
| **Ollama** | Runs AI models locally on your machine | Converts text into vectors (embeddings) without sending data to the cloud. Free and private. |

### Python Libraries (Code Others Wrote That We Reuse)

| Library | What It Does | Where We Use It |
|---------|-------------|-----------------|
| **pydantic** / **pydantic-settings** | Validates data and loads config from `.env` files | `config.py` — loads settings like database URL, chunk sizes |
| **httpx** | Makes HTTP requests (like a browser, but in code) | Extractors — calls the Jolpica API and Wikipedia API |
| **tenacity** | Retries failed operations automatically | Extractors + embedder — if an API call fails, try again up to 3 times |
| **xxhash** | Generates fast fingerprints (hashes) of text | Models — creates a unique ID for each document's content for deduplication |
| **langchain-text-splitters** | Splits long text into smaller overlapping chunks | Chunker — breaks documents into pieces that fit the AI's context window |
| **sqlalchemy** | Talks to databases using Python code | Loader — inserts documents and chunks into PostgreSQL |
| **asyncpg** | Fast PostgreSQL driver for async Python | Used by SQLAlchemy under the hood for database connections |
| **structlog** | Structured logging (better than `print()`) | All modules — logs what's happening with timestamps and context |
| **tqdm** | Shows progress bars in the terminal | Pipeline — shows how many documents have been processed |
| **beautifulsoup4** / **lxml** | Parses HTML (for future use) | Available for Wikipedia HTML parsing if needed |
| **pytest** | Testing framework | Runs our test suite to verify code works |
| **respx** | Mocks HTTP requests in tests | Tests — pretends to be the Jolpica/Wikipedia API so tests don't need the internet |

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
├── ingestion/                    # *** PHASE 1 — Everything we built ***
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
│   │   ├── jolpica.py            # Fetches F1 race data from Jolpica API
│   │   └── wikipedia.py          # Fetches F1 articles from Wikipedia
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
│   │   └── pgvector.py           # Inserts into PostgreSQL
│   │
│   ├── pipeline.py               # Orchestrates steps 1-4 together
│   └── healthcheck.py            # Verifies all services are running
│
├── tests/                        # Automated tests
│   ├── __init__.py
│   ├── conftest.py               # Shared test setup
│   ├── test_extractors.py        # Tests for Jolpica + Wikipedia extractors
│   └── test_pipeline.py          # Tests for the chunker
│
├── agent/                        # Phase 3 (empty — not built yet)
├── api/                          # Phase 3 (empty — not built yet)
│
├── docs/                         # Planning documents
│   ├── PLAN.md
│   ├── PHASE_1.md
│   ├── PHASE_2.md
│   ├── PHASE_3.md
│   └── Phase-1-summary.md        # Detailed technical summary
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

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text

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

The pipeline is the **conductor** that orchestrates all the pieces:

```
for each extractor (Jolpica, Wikipedia):
    for each document from extractor:
        │
        ├─ Is fingerprint already in database?
        │   ├─ YES → skip (already processed)
        │   └─ NO  → continue ↓
        │
        ├─ Chunk the document (Chunker)
        │
        ├─ Embed all chunks (OllamaEmbedder)
        │
        └─ Store in database (PgVectorLoader)

After all documents:
    └─ Rebuild the vector search index
```

### The CLI (Command-Line Interface)

You run the pipeline from the terminal:

```bash
# Ingest all historical data (1950-2024)
uv run python -m ingestion.pipeline --phase static

# Ingest only a specific year range
uv run python -m ingestion.pipeline --phase static --start-year 2000 --end-year 2024
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

## 12. The Health Check — Making Sure Everything Is Online

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

## 13. The Tests — How We Verify Our Code Works

### What Is Automated Testing?

Instead of manually running the program and eyeballing the output, we write
small programs that **automatically** check that our code behaves correctly.
If someone later changes the code and accidentally breaks something, the tests
will catch it.

### Our Test Suite

**Run with:** `uv run pytest tests/ -v`

#### `tests/test_extractors.py` — 4 Tests

These test the Jolpica and Wikipedia extractors, but **without hitting the real
APIs**. Instead, we use **mocking** (via the `respx` library) to intercept HTTP
requests and return fake responses:

```python
@respx.mock
async def test_jolpica_extracts_drivers():
    # Set up fake API response
    respx.get("https://api.jolpi.ca/ergast/f1/drivers.json").mock(
        return_value=httpx.Response(200, json={...fake data...})
    )

    # Run the extractor — it thinks it's talking to the real API
    extractor = JolpicaExtractor(start_year=2024, end_year=2024)
    docs = []
    async for doc in extractor.extract():
        docs.append(doc)

    # Verify the output
    assert len(driver_docs) == 1
    assert driver_docs[0].source == SourceType.JOLPICA
```

**Why mock?**
- Tests run in milliseconds instead of minutes
- Tests work without an internet connection
- Tests are deterministic (same fake data every time)

| Test | What It Verifies |
|------|-----------------|
| `test_jolpica_extracts_drivers` | Jolpica extractor produces documents with correct source, type, and content |
| `test_jolpica_fingerprint_changes_with_content` | Different content produces different fingerprints |
| `test_wikipedia_extracts_sections` | Wikipedia extractor yields narrative documents with proper metadata |
| `test_wikipedia_clean_wikitext` | Wikitext cleanup strips templates, links, and refs correctly |

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

#### `tests/conftest.py` — Shared Setup

Automatically initialises structured logging before every test. `conftest.py` is
a special pytest file — fixtures defined here are available to all test files.

---

## 14. Docker — Running Services Without Installing Them

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
    image: ollama/ollama:latest       # Latest Ollama release
    ports:
      - "11434:11434"                 # Access on port 11434
    volumes:
      - ollama_models:/root/.ollama   # Persist downloaded AI models
```

**Key commands:**
```bash
docker compose up -d       # Start both services in the background
docker compose down        # Stop both services
docker compose logs -f     # Watch live logs
```

### Why Port 5433 Instead of 5432?

PostgreSQL normally runs on port 5432. We use 5433 to avoid conflicts if you
already have PostgreSQL installed on your machine. The container internally still
uses 5432, but Docker maps it to 5433 on your host.

---

## 15. The Database Schema — How Data Is Organised on Disk

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

## 16. Key Python Concepts Used in This Project

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

## 17. How to Run the Project

### First-Time Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd f1-chatbot

# 2. Install Python dependencies
uv sync --extra dev

# 3. Start Docker services (PostgreSQL + Ollama)
docker compose up -d

# 4. Download the embedding AI model (one-time, ~270 MB)
docker compose exec ollama ollama pull nomic-embed-text

# 5. Verify everything is working
uv run python -m ingestion.healthcheck
```

### Running the Ingestion Pipeline

```bash
# Full run (1950-2024) — takes 30-45 minutes
uv run python -m ingestion.pipeline --phase static

# Quick test run (just one year)
uv run python -m ingestion.pipeline --phase static --start-year 2024 --end-year 2024
```

### Running Tests

```bash
# Run all tests with verbose output
uv run pytest tests/ -v
```

### Stopping Everything

```bash
docker compose down   # Stops PostgreSQL and Ollama
```

---

## 18. Glossary

| Term | Definition |
|------|-----------|
| **API** | A way for programs to communicate. Our code calls F1 APIs to get data. |
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
| **Index** | A database structure that speeds up searches (like a book's index speeds up finding topics). |
| **IVFFlat** | A type of vector index that clusters vectors for faster approximate nearest-neighbour search. |
| **JSON** | JavaScript Object Notation — a text format for structured data, like `{"key": "value"}`. |
| **Mock** | In testing, a fake version of something (like a fake API) that returns predetermined responses. |
| **Pagination** | Fetching large datasets in small pages (e.g., 100 items at a time). |
| **pgvector** | A PostgreSQL extension that adds support for storing and searching vectors. |
| **Pipeline** | A sequence of processing steps where each step's output feeds into the next. |
| **PostgreSQL** | An open-source relational database that stores data in tables. |
| **RAG** | Retrieval-Augmented Generation — a technique where an AI retrieves relevant facts before generating an answer. |
| **Rate Limiting** | Adding delays between API calls to avoid overwhelming the server. |
| **Schema** | The structure of a database — what tables exist and what columns they have. |
| **Singleton** | A design pattern where only one instance of something exists. Our `settings` object is a singleton. |
| **SQL** | Structured Query Language — the language used to create tables, insert data, and query databases. |
| **Upsert** | "Update or Insert" — insert a row if it doesn't exist, update it if it does. |
| **Vector** | A list of numbers. In our case, 768 numbers that represent the meaning of text. |
| **Virtual Environment** | An isolated Python installation for a project, preventing library conflicts. |
| **Wikitext** | Wikipedia's markup language, which includes templates, links, and refs that we clean before storing. |
| **yield** | A Python keyword that produces values one at a time from a generator function, instead of returning all at once. |
