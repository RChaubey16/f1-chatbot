"""Query router: classifies user queries into intents via Gemini."""

from __future__ import annotations

from enum import Enum

from agent import llm as gemini
from agent.prompts import ROUTER_SYSTEM, ROUTER_PROMPT
from ingestion.core.logging import get_logger

logger = get_logger(__name__)


class Intent(str, Enum):
    HISTORICAL = "HISTORICAL"
    CURRENT = "CURRENT"
    MIXED = "MIXED"


class Router:
    """Classifies a user query into an Intent using Gemini."""

    async def classify(self, query: str) -> Intent:
        prompt = ROUTER_PROMPT.replace("{query}", query)
        try:
            raw = await gemini.generate(system=ROUTER_SYSTEM, prompt=prompt)
            raw = raw.strip().upper()
            if not raw:
                logger.warning("router.classify: empty response, defaulting to MIXED")
                return Intent.MIXED
            # Extract just the first word in case the model adds punctuation
            word = raw.split()[0].rstrip(".")
            return Intent(word)
        except (ValueError, Exception) as exc:
            logger.warning("Router classify failed, defaulting to MIXED", error=str(exc))
            return Intent.MIXED

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> "Router":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass
