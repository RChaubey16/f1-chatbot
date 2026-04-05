# Deployment Approaches

This document outlines the main deployment options for the F1 Chatbot and the trade-offs between them. The stack has three independently deployable pieces:

| Piece | What it is |
|---|---|
| **PostgreSQL + pgvector** | The vector/relational database |
| **Ollama** | Local embedding service (`nomic-embed-text`) |
| **FastAPI API** | Backend — agent, retrieval, scheduler, routes |
| **Next.js frontend** | Chat and standings UI |

---

## Option 1 — Full Docker Compose (local / single server)

The simplest option. Everything runs in one `docker compose up`.

```
┌───────────────────────────────────┐
│           Single host             │
│                                   │
│  postgres  ollama  api  frontend  │
└───────────────────────────────────┘
```

**How to run:**

```bash
docker compose up -d
cd frontend && pnpm install && pnpm dev   # frontend still runs on host
```

The provided `docker-compose.yml` already wires up `postgres`, `ollama`, and `api`. The frontend can be added as a fourth service or run on the host with `pnpm dev`.

**Trade-offs:**

| | |
|---|---|
| Pros | Zero cloud cost, simple to reason about, no network latency between services |
| Cons | Single point of failure, no horizontal scaling, Ollama is CPU-only by default (slow embeddings without GPU) |

**Best for:** Local development, demos, personal use.

---

## Option 2 — Vercel (frontend) + Fly.io or Railway (API) + Managed Postgres

Split the frontend from the backend. The frontend is stateless and deploys well on edge platforms; the API and database stay on a persistent server.

```
┌──────────────┐     HTTPS      ┌─────────────────────────────┐
│   Vercel     │ ─────────────► │   Fly.io / Railway          │
│  (Next.js)   │                │                             │
└──────────────┘                │  FastAPI + Ollama container │
                                └──────────────┬──────────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │  Supabase / Neon /  │
                                    │  Railway Postgres   │
                                    └─────────────────────┘
```

**Frontend — Vercel:**

1. Push the `frontend/` directory to a GitHub repo (or point Vercel at a monorepo subdirectory).
2. Set the `f1_api_url` environment secret in the Vercel dashboard — this is referenced in `vercel.json` as `@f1_api_url` and exposed as `NEXT_PUBLIC_API_URL`.
3. Vercel auto-deploys on every push to `main`.

**API — Fly.io example:**

```bash
cd /path/to/f1-chatbot
fly launch          # generates fly.toml
fly secrets set GEMINI_API_KEY=... DATABASE_URL=... FRONTEND_URL=https://your-app.vercel.app
fly deploy
```

The `Dockerfile` at the project root is already set up for this — it installs dependencies with `uv` and starts `uvicorn`.

**Postgres — managed options:**

| Provider | pgvector support | Notes |
|---|---|---|
| Supabase | Yes (built-in) | Generous free tier |
| Neon | Yes | Serverless, scales to zero |
| Railway | Yes (via plugin) | Simple setup alongside the API |
| Fly Postgres | Yes (extension) | Co-located with API, low latency |

**Ollama — important caveat:**

Ollama needs to run alongside the API because embeddings are generated at ingestion time and at query time (for the retriever). On Fly.io, include Ollama in the same VM or as a sidecar. Alternatively, replace Ollama with a managed embedding API (see Option 4).

**Trade-offs:**

| | |
|---|---|
| Pros | Frontend auto-scales on Vercel edge, managed Postgres removes DB ops burden, reasonable cost |
| Cons | Ollama on a shared cloud VM is CPU-only and slow; embedding at query time adds latency |

**Best for:** Side projects and small production deployments where embedding latency is acceptable.

---

## Option 3 — Kubernetes / Docker Swarm (self-hosted or cloud)

For higher availability and horizontal scaling. Each service runs as a separate deployment/service.

```
Ingress (nginx / Traefik)
        │
        ├── frontend  (Next.js — replicas: 2+)
        │
        └── api       (FastAPI — replicas: 2+)
                │
                ├── postgres  (StatefulSet or managed)
                └── ollama    (Deployment, GPU node if available)
```

Key considerations:

- **Ollama** should be pinned to a node with sufficient RAM (8 GB+ for `nomic-embed-text`). If a GPU node is available, use `ollama/ollama:latest` with the NVIDIA runtime for ~10x faster embedding.
- **Postgres** with pgvector is best run as a managed service (see Option 2) rather than a StatefulSet, unless you have existing DB ops expertise.
- **Scheduler**: The APScheduler runs embedded in the API process. With multiple API replicas, use `max_instances=1` (already set) and ensure only one replica runs the scheduler, or extract the scheduler into its own single-replica deployment.

**Best for:** Production workloads with traffic spikes, teams with Kubernetes experience.

---

## Option 4 — Swap Ollama for a Managed Embedding API

Ollama is the most operationally awkward piece because it requires a persistent, memory-heavy process. For production, consider replacing it:

| Provider | Model | Dimensions | Notes |
|---|---|---|---|
| Google `text-embedding-004` | `text-embedding-004` | 768 | Same dim as `nomic-embed-text`, pairs naturally with Gemini LLM |
| OpenAI `text-embedding-3-small` | `text-embedding-3-small` | 1536 | Would require re-ingesting with schema change |
| Cohere Embed v3 | `embed-english-v3.0` | 1024 | Strong retrieval benchmarks |

**Migration steps:**

1. Update `ingestion/embedders/` — create a new embedder class mirroring `OllamaEmbedder`'s interface (`embed_batch`, `_embed_one`, `close`).
2. Update `agent/retriever.py` — swap `OllamaEmbedder` for the new embedder.
3. Update `ingestion/core/config.py` — add the new API key setting.
4. Re-run ingestion to regenerate all embeddings with the new model (existing vectors are incompatible if dimensions differ).
5. Remove the `ollama` service from `docker-compose.yml`.

**Best for:** Deployments where removing the Ollama dependency is worth the per-embedding API cost.

---

## Environment variables per deployment target

| Variable | Local | Vercel (frontend) | Fly / Railway (API) |
|---|---|---|---|
| `DATABASE_URL` | `localhost:5432` | — | Managed Postgres URL |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | — | Internal service URL |
| `GEMINI_API_KEY` | `.env` | — | Secret |
| `GEMINI_MODEL` | `gemini-2.5-flash` | — | `gemini-2.5-flash` |
| `FRONTEND_URL` | `http://localhost:3000` | — | `https://your-app.vercel.app` |
| `NEXT_PUBLIC_API_URL` | — | `https://your-api.fly.dev` | — |

---

## Recommendation

| Use case | Recommended approach |
|---|---|
| Local dev / demo | Option 1 (Docker Compose) |
| Low-traffic production, solo project | Option 2 (Vercel + Fly.io + Supabase) |
| Cost-sensitive, high query volume | Option 4 (swap Ollama for managed embeddings) + Option 2 |
| High availability, team product | Option 3 (Kubernetes) + managed Postgres + managed embeddings |
