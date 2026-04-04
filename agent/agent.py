"""Core reasoning loop for the F1 chatbot RAG agent."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator

from agent import llm as gemini
from agent.prompts import ANSWER_PROMPT, SYSTEM_INSTRUCTION
from agent.retriever import RetrievedChunk, Retriever
from agent.router import Intent, Router
from agent.tools import get_current_standings
from ingestion.core.logging import get_logger

log = get_logger(__name__)

_MAX_CONTEXT_CHARS = 12_000


class Agent:
    """RAG agent that routes queries, retrieves context, and streams LLM responses."""

    def __init__(self) -> None:
        self._router = Router()
        self._retriever = Retriever()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _prepare_context(
        self, query: str, top_k: int = 6
    ) -> tuple[Intent, list[RetrievedChunk], str]:
        """Classify the query and build a context string for the LLM.

        Returns:
            (intent, chunks, context_str)
        """
        intent = await self._router.classify(query)
        log.info("agent.prepare_context", intent=intent.value, query=query)

        # --- retrieve chunks -------------------------------------------------
        chunks: list[RetrievedChunk] = []
        if intent is Intent.HISTORICAL:
            chunks = await self._retriever.retrieve(
                query, partitions=["static"], top_k=top_k
            )
        elif intent is Intent.MIXED:
            chunks = await self._retriever.retrieve(
                query, partitions=["static", "live"], top_k=top_k
            )
        # CURRENT → no chunk retrieval

        # --- fetch live standings when needed --------------------------------
        standings: str | None = None
        if intent in (Intent.CURRENT, Intent.MIXED):
            standings = await get_current_standings()

        # --- build context string -------------------------------------------
        parts: list[str] = []
        for chunk in chunks:
            parts.append(f"Source: {chunk.source}\n{chunk.content}\n")

        if standings:
            parts.append(standings)

        context_str = "\n".join(parts)

        # Truncate to stay within ~3000 token budget (proxy: 12 000 chars)
        if len(context_str) > _MAX_CONTEXT_CHARS:
            context_str = context_str[:_MAX_CONTEXT_CHARS]

        return intent, chunks, context_str

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(self, query: str) -> AsyncGenerator[str, None]:
        """Stream the answer token-by-token for *query*.

        Yields individual response tokens as strings.
        """
        _, _, context_str = await self._prepare_context(query)
        prompt = ANSWER_PROMPT.replace("{context}", context_str).replace("{question}", query)
        async for token in gemini.stream(system=SYSTEM_INSTRUCTION, prompt=prompt):
            yield token

    async def run_sync(self, query: str, max_chunks: int = 6) -> dict:
        """Return the full answer and metadata for *query* (non-streaming).

        Args:
            query: The user's question.
            max_chunks: Maximum number of context chunks to retrieve.

        Returns:
            A dict with keys ``answer``, ``sources``, ``intent``, and
            ``latency_ms``.
        """
        t0 = time.monotonic()

        intent, chunks, context_str = await self._prepare_context(query, top_k=max_chunks)
        prompt = ANSWER_PROMPT.replace("{context}", context_str).replace("{question}", query)

        answer_parts: list[str] = []
        async for token in gemini.stream(system=SYSTEM_INSTRUCTION, prompt=prompt):
            answer_parts.append(token)

        latency_ms = (time.monotonic() - t0) * 1000.0

        return {
            "answer": "".join(answer_parts),
            "sources": [
                {
                    "content_type": c.content_type,
                    "source": c.source,
                    "metadata": c.metadata,
                }
                for c in chunks
            ],
            "intent": intent.value,
            "latency_ms": latency_ms,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Release all underlying resources."""
        await self._router.close()
        await self._retriever.close()

    async def __aenter__(self) -> "Agent":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
