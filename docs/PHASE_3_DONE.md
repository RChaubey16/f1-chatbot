# Phase 3 — Completion Report

> This file is generated at the end of Phase 3 execution.
> Claude Code should fill in every section below before marking Phase 3 done.

---

## What Was Built in This Phase

A brief human-readable summary of everything that was implemented. Claude Code
should fill this in after the phase completes — not before.

### Retriever
- _(e.g. Dense retrieval via pgvector cosine similarity — query embedded with nomic-embed-text before search)_
- _(e.g. Sparse retrieval via PostgreSQL full-text search on content_tsv GIN index)_
- _(e.g. Reciprocal Rank Fusion merges both result lists — k=60, top-6 chunks returned)_
- _(e.g. Partition filter scopes search to static, live, or both depending on intent)_

### Query Router
- _(e.g. Router prompts local Ollama mistral to classify query into HISTORICAL / CURRENT / MIXED)_
- _(e.g. Fallback to MIXED on unexpected LLM output)_
- _(e.g. Classification adds ~0.8s latency on CPU — acceptable within 5s budget)_

### Tools
- _(e.g. get_current_standings() — calls OpenF1 API, returns formatted WDC/WCC standings string)_
- _(e.g. get_race_results(year, gp) — queries Jolpica for historical, OpenF1 for current year)_
- _(e.g. get_driver_stats(name) — SQL lookup against chunks metadata for fast structured response)_

### Agent
- _(e.g. Lightweight reasoning loop — no LangChain, routes → retrieves/calls tools → builds prompt → streams)_
- _(e.g. Context window managed — truncated to top-k chunks if token count exceeds ~3000)_
- _(e.g. System prompt instructs LLM to cite sources and admit uncertainty rather than hallucinate)_

### API
- _(e.g. POST /chat — non-streaming endpoint, returns answer + sources + intent + latency_ms)_
- _(e.g. GET /chat/stream — SSE streaming endpoint, yields tokens as data: {"token": "..."} events)_
- _(e.g. GET /health — checks postgres, ollama, chunk counts, last live refresh)_
- _(e.g. APScheduler started as background task on app startup)_

### Infrastructure
- _(e.g. Dockerfile added — python:3.12-slim base, uv for deps)_
- _(e.g. docker-compose.yml extended with api service, healthcheck dependencies on postgres + ollama)_

### Tests
- _(e.g. test_agent.py — integration tests for historical query, current query, and SSE streaming)_
- _(e.g. Router tested against 10 sample queries — N/10 correct classification)_

---

## Completion Status

- [ ] All Phase 3 checklist items passed
- [ ] All tests pass (`uv run pytest tests/ -v`)
- [ ] `GET /health` returns `"status": "ok"` for all components
- [ ] `POST /chat` returns grounded answers with sources
- [ ] `GET /chat/stream` streams tokens correctly
- [ ] Query router correctly classifies all 10 test queries
- [ ] Full Docker Compose stack (`postgres` + `ollama` + `api`) starts cleanly

**Completed at:** `YYYY-MM-DD HH:MM`
**Executed by:** _(Claude Code session ID or developer name)_

---

## Environment Snapshot

```
Phase 2 completed at:    # Copy from PHASE_2_DONE.md
Phase 3 started at:      # YYYY-MM-DD HH:MM
FastAPI version:         # uv run python -c "import fastapi; print(fastapi.__version__)"
Ollama LLM model:        # from .env — LLM_MODEL value
```

---

## Files Created

```
agent/
  retriever.py           ✅ / ❌
  router.py              ✅ / ❌
  tools.py               ✅ / ❌
  agent.py               ✅ / ❌
  prompts.py             ✅ / ❌

api/
  main.py                ✅ / ❌
  schemas.py             ✅ / ❌
  routes/
    chat.py              ✅ / ❌
    health.py            ✅ / ❌

Dockerfile               ✅ / ❌
docker-compose.yml       ✅ / ❌  (api service added)

tests/
  test_agent.py          ✅ / ❌
```

---

## Docker Compose Stack

```bash
docker compose up -d
docker compose ps
```

```
# Paste output here — all three services should show "healthy" or "running"
```

| Service | Status | Port |
|---|---|---|
| postgres | _(fill in)_ | 5432 |
| ollama | _(fill in)_ | 11434 |
| api | _(fill in)_ | 8000 |

---

## Health Check

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

```json
// Paste response here
```

- [ ] `"status": "ok"`
- [ ] `"postgres": "ok"`
- [ ] `"ollama": "ok"`
- [ ] `chunks_static` > 0
- [ ] `chunks_live` > 0
- [ ] `last_live_refresh` is populated

---

## Query Router Validation

Test the router against 10 sample queries and record the classified intent.
Expected values are provided — flag any misclassifications.

```bash
# For each query below, call:
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "<QUERY>"}' | python3 -m json.tool | grep intent
```

| # | Query | Expected intent | Actual intent | Pass? |
|---|---|---|---|---|
| 1 | "Who won the 1988 Formula One championship?" | HISTORICAL | _(fill in)_ | ✅/❌ |
| 2 | "Tell me about Ayrton Senna's career" | HISTORICAL | _(fill in)_ | ✅/❌ |
| 3 | "What are the current driver standings?" | CURRENT | _(fill in)_ | ✅/❌ |
| 4 | "Who won the last race?" | CURRENT | _(fill in)_ | ✅/❌ |
| 5 | "What is the fastest lap record at Monza?" | HISTORICAL | _(fill in)_ | ✅/❌ |
| 6 | "How does Hamilton's career compare to Schumacher?" | MIXED | _(fill in)_ | ✅/❌ |
| 7 | "What are Red Bull's constructor points this season?" | CURRENT | _(fill in)_ | ✅/❌ |
| 8 | "Explain DRS and when it was introduced" | HISTORICAL | _(fill in)_ | ✅/❌ |
| 9 | "Who is leading the championship and how does it compare to 2021?" | MIXED | _(fill in)_ | ✅/❌ |
| 10 | "What happened at the 2021 British Grand Prix?" | HISTORICAL | _(fill in)_ | ✅/❌ |

**Router accuracy:** _ / 10

---

## Sample Chat Responses

Record at least three real responses to verify answer quality and source attribution.

### Query 1: Historical fact
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Who won the 1988 Formula One championship?"}'
```
```json
// Paste response here
```
- [ ] Answer mentions Senna / Ayrton Senna
- [ ] Sources are populated
- [ ] `intent` = "HISTORICAL"
- [ ] `latency_ms` recorded: ___ ms

---

### Query 2: Current standings (live tool call)
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the current driver standings?"}'
```
```json
// Paste response here
```
- [ ] Answer contains driver names and points
- [ ] `intent` = "CURRENT"
- [ ] `latency_ms` recorded: ___ ms

---

### Query 3: Narrative / contextual
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Why is Monaco considered the most prestigious F1 race?"}'
```
```json
// Paste response here
```
- [ ] Answer is coherent and grounded in context
- [ ] Sources reference Wikipedia circuit or narrative chunks
- [ ] `latency_ms` recorded: ___ ms

---

## Streaming Verification

```bash
curl -N "http://localhost:8000/chat/stream?query=Who+is+Lewis+Hamilton"
```

```
# Paste raw SSE output here (first 10 lines is enough)
data: {"token": "Lewis"}
data: {"token": " Hamilton"}
...
data: [DONE]
```

- [ ] Tokens stream progressively (not all at once)
- [ ] Final event is `[DONE]`
- [ ] No error events in stream

---

## Performance Metrics

| Metric | Target | Actual | Pass? |
|---|---|---|---|
| Non-streaming response (historical) | < 5s | ___ ms | ✅/❌ |
| Non-streaming response (current/tool) | < 3s | ___ ms | ✅/❌ |
| First token latency (streaming) | < 2s | ___ ms | ✅/❌ |
| Vector search (top-6) | < 200ms | ___ ms | ✅/❌ |
| Router classification | < 1s | ___ ms | ✅/❌ |

> If non-streaming latency exceeds 5s, consider switching `LLM_MODEL` to
> `mistral:7b-instruct-q4_K_M` (quantised) in `.env` for faster CPU inference.

---

## Hybrid Search Validation

Confirm both dense and sparse retrieval are contributing to results.

```bash
# Enable debug logging temporarily and run a query, then check logs for:
# "dense_results: N chunks"
# "sparse_results: N chunks"
# "rrf_merged: N chunks"
```

- [ ] Dense retrieval returning results
- [ ] Sparse (full-text) retrieval returning results
- [ ] RRF merging both result sets

---

## Test Results

```bash
uv run pytest tests/ -v
```

```
# Paste pytest output here
```

**Passed:** _ / _
**Failed:** _

---

## Deviations from Plan

| Item | Plan said | What actually happened | Reason |
|---|---|---|---|
| | | | |

---

## Known Issues / Debt

- _(e.g. router misclassifies ambiguous queries, latency on CPU-only Ollama)_

---

## Build Complete ✅

All three phases done. The F1 RAG chatbot backend is fully operational.

**Summary of what was built:**

| Phase | What | Status |
|---|---|---|
| 1 | Static KB — Jolpica + Wikipedia ingested into pgvector | ✅ |
| 2 | Live KB — OpenF1 + News scraper + APScheduler | ✅ |
| 3 | FastAPI RAG agent — hybrid search, query routing, streaming | ✅ |

**Next step:** Frontend (Next.js chatbot UI) — not covered in this plan.
The API is ready: `POST /chat` and `GET /chat/stream` are the two endpoints
the frontend needs to integrate with.
