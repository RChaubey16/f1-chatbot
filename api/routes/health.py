"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from ingestion.core.config import settings
from ingestion.core.logging import get_logger
from ingestion.embedders.ollama import OllamaEmbedder

log = get_logger(__name__)

router = APIRouter(prefix="")


@router.get("/health")
async def health() -> dict:
    chunks_static = 0
    chunks_live = 0
    last_live_refresh = None
    postgres_status = "ok"

    engine = create_async_engine(settings.database_url, echo=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM chunks WHERE partition='static'")
            )
            chunks_static = result.scalar() or 0

            result = await conn.execute(
                text("SELECT COUNT(*) FROM chunks WHERE partition='live'")
            )
            chunks_live = result.scalar() or 0

            result = await conn.execute(
                text(
                    "SELECT last_synced_at FROM sync_state"
                    " WHERE source='openf1' LIMIT 1"
                )
            )
            row = result.fetchone()
            if row and row[0] is not None:
                ts = row[0]
                # Format as ISO string with Z suffix if not already tz-aware string
                if hasattr(ts, "isoformat"):
                    last_live_refresh = ts.isoformat().replace("+00:00", "Z")
                else:
                    last_live_refresh = str(ts)

        postgres_status = "ok"
    except Exception as exc:
        log.warning("Postgres health check failed: %s", exc)
        postgres_status = "error"
        chunks_static = 0
        chunks_live = 0
        last_live_refresh = None
    finally:
        await engine.dispose()

    embedder = OllamaEmbedder()
    try:
        ollama_ok = await embedder.health_check()
        ollama_status = "ok" if ollama_ok else "error"
    except Exception as exc:
        log.warning("Ollama health check failed: %s", exc)
        ollama_status = "error"
    finally:
        await embedder.close()

    overall = "ok" if postgres_status == "ok" and ollama_status == "ok" else "error"

    return {
        "status": overall,
        "postgres": postgres_status,
        "ollama": ollama_status,
        "chunks_static": chunks_static,
        "chunks_live": chunks_live,
        "last_live_refresh": last_live_refresh,
    }
