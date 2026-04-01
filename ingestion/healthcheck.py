"""Pre-flight checks: verify all external services are reachable."""

from __future__ import annotations

import asyncio
import sys

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ingestion.core.config import settings
from ingestion.core.logging import get_logger, setup_logging

log = get_logger(__name__)


async def check_postgres() -> bool:
    try:
        engine = create_async_engine(settings.database_url)
        async with AsyncSession(engine) as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1

            # Verify pgvector extension
            result = await session.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
            ext = result.scalar()
            assert ext == "vector", "pgvector extension not installed"

        await engine.dispose()
        return True
    except Exception as e:
        log.error("healthcheck.postgres.fail", error=str(e))
        return False


async def check_ollama() -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            found = any(settings.embedding_model in m for m in models)
            if not found:
                log.error(
                    "healthcheck.ollama.model_missing",
                    model=settings.embedding_model,
                    available=models,
                )
            return found
    except Exception as e:
        log.error("healthcheck.ollama.fail", error=str(e))
        return False


async def check_jolpica() -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.jolpi.ca/ergast/f1/drivers.json",
                params={"limit": 1},
            )
            return resp.status_code == 200
    except Exception as e:
        log.error("healthcheck.jolpica.fail", error=str(e))
        return False


async def check_wikipedia() -> bool:
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": settings.user_agent},
        ) as client:
            resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "meta": "siteinfo", "format": "json"},
            )
            return resp.status_code == 200
    except Exception as e:
        log.error("healthcheck.wikipedia.fail", error=str(e))
        return False


async def run_all() -> bool:
    checks = {
        "PostgreSQL": check_postgres,
        "Ollama": check_ollama,
        "Jolpica API": check_jolpica,
        "Wikipedia API": check_wikipedia,
    }

    results = {}
    for name, fn in checks.items():
        ok = await fn()
        results[name] = ok
        status = "OK" if ok else "FAIL"
        log.info("healthcheck.result", service=name, status=status)

    all_ok = all(results.values())
    if all_ok:
        log.info("healthcheck.all_passed")
    else:
        failed = [k for k, v in results.items() if not v]
        log.error("healthcheck.failed", services=failed)

    return all_ok


def main() -> None:
    setup_logging()
    ok = asyncio.run(run_all())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
