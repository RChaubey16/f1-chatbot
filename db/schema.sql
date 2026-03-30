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
