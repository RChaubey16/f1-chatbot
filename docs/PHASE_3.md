# Phase 3 — FastAPI RAG Agent + Query Routing

## Goal

Build the reasoning layer on top of the knowledge base: a FastAPI service
that accepts a user question, routes it to the right retrieval strategy, and
returns a grounded answer via a local Ollama LLM.

**Completion criteria:**
- FastAPI app running with `/chat` and `/health` endpoints
- Hybrid search (pgvector cosine similarity + PostgreSQL full-text) working
- Query router classifying intent → correct retrieval path
- Agent synthesising answers with source attribution
- Streaming responses via SSE
- Full Docker Compose stack running all services

---

## Architecture Overview

```
User question
     │
     ▼
┌─────────────┐
│   Router    │  Classifies query intent
└─────────────┘
     │
     ├──── "historical fact / narrative"  ──▶  Hybrid RAG retrieval
     │
     ├──── "current standings / results"  ──▶  Live API tool call (OpenF1)
     │
     └──── "structured lookup"            ──▶  SQL query tool (pgvector metadata)
                                                        │
                                                        ▼
                                              ┌──────────────────┐
                                              │   Ollama LLM     │
                                              │  (mistral/llama3)│
                                              └──────────────────┘
                                                        │
                                                        ▼
                                                Streamed answer
```

---

## Step 1 — Retriever

### File: `agent/retriever.py`

**Hybrid search** combines two signals and merges via Reciprocal Rank Fusion (RRF):

### 1.1 Dense retrieval (pgvector)

```sql
SELECT chunk_id, content, metadata, source, content_type,
       1 - (embedding <=> $1::vector) AS similarity
FROM chunks
WHERE partition = ANY($2)          -- ['static'] or ['live'] or both
ORDER BY embedding <=> $1::vector
LIMIT $3;
```

- Embed the query first using `OllamaEmbedder`
- `$2` partition filter lets the router scope search to static, live, or both

### 1.2 Sparse retrieval (PostgreSQL full-text)

```sql
SELECT chunk_id, content, metadata, source, content_type,
       ts_rank(content_tsv, query) AS rank
FROM chunks, plainto_tsquery('english', $1) query
WHERE content_tsv @@ query
  AND partition = ANY($2)
ORDER BY rank DESC
LIMIT $3;
```

### 1.3 Reciprocal Rank Fusion

Merge the two result lists in Python:

```python
def rrf(dense_results, sparse_results, k=60) -> list[Chunk]:
    scores = defaultdict(float)
    for rank, chunk in enumerate(dense_results):
        scores[chunk.chunk_id] += 1 / (k + rank + 1)
    for rank, chunk in enumerate(sparse_results):
        scores[chunk.chunk_id] += 1 / (k + rank + 1)
    # Return top chunks sorted by combined score
```

**Reranking (optional enhancement):**
After RRF, optionally run a cross-encoder reranker. With local models this is
expensive — only enable if latency budget allows. A simple BM25-style
re-scoring in Python is a free alternative.

**Retriever interface:**
```python
async def retrieve(
    query: str,
    partitions: list[str] = ["static", "live"],
    top_k: int = 6,
) -> list[RetrievedChunk]:
```

---

## Step 2 — Query Router

### File: `agent/router.py`

The router classifies the user's intent before retrieval so the agent uses the
most appropriate data source. Think of it as a traffic controller — the same
question phrased differently might need a different path.

**Three intent classes:**

| Class | Examples | Strategy |
|---|---|---|
| `HISTORICAL` | "Who won the 1988 championship?", "Tell me about Senna" | Hybrid RAG over static KB |
| `CURRENT` | "What are the standings today?", "Who won last week?" | Live API tool call |
| `MIXED` | "How does Hamilton's career compare to Schumacher?" | RAG over both partitions |

**Classification approach — prompt the local LLM:**

```python
ROUTER_PROMPT = """
You are an F1 query classifier. Classify the query into exactly one of:
- HISTORICAL: about past seasons, history, biographical info, anything before this year
- CURRENT: about the current season, live standings, recent race results
- MIXED: requires both historical context and current information

Query: {query}

Respond with only the class name. No explanation.
"""
```

This uses the same Ollama `mistral` instance as the main agent — no extra
service needed.

**Fallback:** If the LLM returns an unexpected value, default to `MIXED`
(searches both partitions — safe but slightly slower).

---

## Step 3 — Tools

### File: `agent/tools.py`

Tools the agent can call for structured lookups and live data. These bypass
vector search entirely and return precise, fresh answers.

**Tool 1: `get_current_standings`**
```python
async def get_current_standings() -> str:
    # Calls OpenF1 /drivers + /sessions to build current WDC/WCC standings
    # Returns formatted string: "1. Verstappen — 245pts  2. Hamilton — 198pts..."
```

**Tool 2: `get_race_results(year, round_or_gp_name)`**
```python
async def get_race_results(year: int, gp: str) -> str:
    # Queries Jolpica (static) or OpenF1 (current year)
    # Returns formatted race result string
```

**Tool 3: `get_driver_stats(driver_name)`**
```python
async def get_driver_stats(driver_name: str) -> str:
    # SQL query against chunks metadata for fast structured lookup
    # SELECT metadata FROM chunks
    # WHERE content_type = 'driver_profile'
    # AND metadata->>'name' ILIKE '%{driver_name}%'
    # LIMIT 1
```

Tools return plain strings — the agent includes them in its context window
alongside RAG chunks.

---

## Step 4 — Agent

### File: `agent/agent.py`

The agent is a simple reasoning loop — not a full LangChain agent — which keeps
it lean and debuggable.

```python
async def run(query: str) -> AsyncIterator[str]:

    # 1. Route
    intent = await router.classify(query)

    # 2. Retrieve or call tools
    context_parts = []

    if intent in (Intent.HISTORICAL, Intent.MIXED):
        partitions = ["static"] if intent == Intent.HISTORICAL else ["static", "live"]
        chunks = await retriever.retrieve(query, partitions=partitions)
        context_parts.append(format_chunks(chunks))

    if intent in (Intent.CURRENT, Intent.MIXED):
        standings = await tools.get_current_standings()
        context_parts.append(standings)

    # 3. Build prompt
    context = "\n\n---\n\n".join(context_parts)
    prompt = build_prompt(query, context)

    # 4. Stream from Ollama
    async for token in ollama_stream(prompt):
        yield token
```

### File: `agent/prompts.py`

```python
SYSTEM_PROMPT = """
You are an expert F1 analyst and historian. Answer questions about Formula One
using only the context provided below. If the context does not contain enough
information to answer, say so clearly rather than guessing.

Always cite your sources when possible (e.g. "According to the 2019 Monaco GP
results..." or "Based on Lewis Hamilton's driver profile...").

Context:
{context}
"""
```

Keep the system prompt tight — local models have smaller context windows than
cloud models. If context exceeds ~3000 tokens, truncate to the top-k most
relevant chunks only.

---

## Step 5 — FastAPI App

### File: `api/main.py`

```python
app = FastAPI(title="F1 Chatbot API", version="1.0.0")

@app.on_event("startup")
async def startup():
    await db.connect()
    scheduler.start()      # Start Phase 2 background jobs

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
    await db.disconnect()
```

### File: `api/routes/chat.py`

**Non-streaming endpoint** (simpler, good for testing):
```
POST /chat
Body: { "query": "Who won the 2019 Monaco GP?" }
Response: { "answer": "...", "sources": [...], "intent": "HISTORICAL" }
```

**Streaming endpoint (SSE):**
```
GET /chat/stream?query=Who+won+Monaco+2019
Response: text/event-stream
data: {"token": "Lewis"}
data: {"token": " Hamilton"}
data: {"token": " won..."}
data: [DONE]
```

**SSE implementation using FastAPI `StreamingResponse`:**
```python
async def event_generator(query: str):
    async for token in agent.run(query):
        yield f"data: {json.dumps({'token': token})}\n\n"
    yield "data: [DONE]\n\n"

@router.get("/chat/stream")
async def chat_stream(query: str):
    return StreamingResponse(
        event_generator(query),
        media_type="text/event-stream"
    )
```

### File: `api/routes/health.py`

```
GET /health
Response: {
  "status": "ok",
  "postgres": "ok" | "error",
  "ollama": "ok" | "error",
  "chunks_static": 9800,
  "chunks_live": 1200,
  "last_live_refresh": "2024-03-25T10:00:00Z"
}
```

### File: `api/schemas.py`

Pydantic models for request/response validation:
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

---

## Step 6 — Docker Compose (Full Stack)

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
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U f1"]
      interval: 5s
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
      retries: 5

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
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - .:/app

volumes:
  pgdata:
  ollama_models:
```

### `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv sync --frozen

COPY . .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Step 7 — End-to-End Test

### File: `tests/test_agent.py`

With the full stack running:

```python
@pytest.mark.integration
async def test_historical_query():
    response = await client.post("/chat", json={"query": "Who won the 1988 championship?"})
    assert response.status_code == 200
    data = response.json()
    assert "Senna" in data["answer"] or "Ayrton" in data["answer"]
    assert data["intent"] == "HISTORICAL"

@pytest.mark.integration
async def test_streaming():
    tokens = []
    async with client.stream("GET", "/chat/stream?query=Who+is+Max+Verstappen") as r:
        async for line in r.aiter_lines():
            if line.startswith("data:") and "[DONE]" not in line:
                tokens.append(json.loads(line[5:])["token"])
    assert len(tokens) > 0
    assert "Verstappen" in "".join(tokens)
```

---

## Performance Targets

| Metric | Target |
|---|---|
| Non-streaming response | < 5s end-to-end |
| First token (streaming) | < 2s |
| Vector search (top-6) | < 200ms |
| Router classification | < 1s |

Local Ollama on CPU will be the bottleneck for generation. If latency is too
high, switch to `mistral:7b-instruct-q4_K_M` (quantised, much faster on CPU).

---

## Phase 3 Done When

- [ ] `docker compose up` starts all three services cleanly
- [ ] `GET /health` returns `"status": "ok"` for all components
- [ ] `POST /chat` with a historical query returns a grounded answer with sources
- [ ] `POST /chat` with a "current standings" query routes to live tool (not RAG)
- [ ] `GET /chat/stream` streams tokens correctly to a browser/curl client
- [ ] Router correctly classifies HISTORICAL / CURRENT / MIXED for a test set of 10 sample queries
- [ ] Integration tests pass
