"""Query router: classifies user queries into intents."""

from __future__ import annotations

from enum import Enum

import httpx

from agent.prompts import ROUTER_PROMPT
from ingestion.core.config import settings
from ingestion.core.logging import get_logger

logger = get_logger(__name__)

# Default model name if settings.llm_model is not yet defined
_DEFAULT_LLM_MODEL = "llama3"


def _llm_model() -> str:
    return getattr(settings, "llm_model", _DEFAULT_LLM_MODEL)


class Intent(str, Enum):
    HISTORICAL = "HISTORICAL"
    CURRENT = "CURRENT"
    MIXED = "MIXED"


class Router:
    """Classifies a user query into an Intent using an Ollama LLM."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)
        self._generate_url = f"{settings.ollama_base_url}/api/generate"

    async def classify(self, query: str) -> Intent:
        """Call Ollama to classify the query into an Intent."""
        prompt = ROUTER_PROMPT.format(query=query)
        payload = {
            "model": _llm_model(),
            "prompt": prompt,
            "stream": False,
        }
        try:
            response = await self._client.post(self._generate_url, json=payload)
            response.raise_for_status()
            data = response.json()
            raw = data.get("response", "").strip().upper()
            if not raw:
                logger.warning("router.classify: LLM returned empty response, defaulting to MIXED")
                return Intent.MIXED
            return Intent(raw)
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("Router classify failed, defaulting to MIXED", error=str(exc))
            return Intent.MIXED

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable and the configured model is available."""
        try:
            url = f"{settings.ollama_base_url}/api/tags"
            response = await self._client.get(url)
            if response.status_code != 200:
                return False
            data = response.json()
            models = data.get("models", [])
            model_name = _llm_model()
            return any(model_name in m.get("name", "") for m in models)
        except Exception as exc:
            logger.warning("Router health_check failed", error=str(exc))
            return False

    async def __aenter__(self) -> "Router":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
