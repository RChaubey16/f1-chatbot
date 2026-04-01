"""Ollama local embedding client."""

from __future__ import annotations

import asyncio

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ingestion.core.config import settings
from ingestion.core.logging import get_logger
from ingestion.core.models import Chunk

log = get_logger(__name__)


class OllamaEmbedder:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=60.0)
        self._url = f"{settings.ollama_base_url}/api/embeddings"
        self._model = settings.embedding_model

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _embed_one(self, text: str) -> list[float]:
        resp = await self._client.post(
            self._url,
            json={"model": self._model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    async def embed_batch(self, chunks: list[Chunk]) -> list[Chunk]:
        batch_size = settings.embedding_batch_size

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            embeddings = await asyncio.gather(
                *(self._embed_one(c.content) for c in batch)
            )
            for chunk, emb in zip(batch, embeddings):
                chunk.embedding = emb

        return chunks

    async def close(self) -> None:
        await self._client.aclose()

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(
                f"{settings.ollama_base_url}/api/tags", timeout=10.0
            )
            if resp.status_code != 200:
                return False
            models = [m["name"] for m in resp.json().get("models", [])]
            # Model name may include tag like "nomic-embed-text:latest"
            return any(self._model in m for m in models)
        except Exception:
            return False
