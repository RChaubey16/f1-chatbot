"""Gemini LLM client used for routing and answer generation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

import httpx

from ingestion.core.config import settings
from ingestion.core.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_MAX_RETRIES = 3
_RETRY_DELAY = 5.0  # seconds; doubled on each 429


def _generate_url(stream: bool = False) -> str:
    if stream:
        return f"{_BASE_URL}/{settings.gemini_model}:streamGenerateContent?alt=sse&key={settings.gemini_api_key}"
    return f"{_BASE_URL}/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"


def _build_body(system: str, prompt: str) -> dict:
    return {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
    }


async def generate(system: str, prompt: str) -> str:
    """Call Gemini and return the full response text. Retries on 429."""
    delay = _RETRY_DELAY
    for attempt in range(_MAX_RETRIES):
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                _generate_url(stream=False),
                json=_build_body(system, prompt),
            )
        if response.status_code == 429:
            log.warning("gemini.generate: rate limited, retrying", attempt=attempt + 1, delay=delay)
            await asyncio.sleep(delay)
            delay *= 2
            continue
        response.raise_for_status()
        data = response.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            log.warning("gemini.generate: unexpected response shape", error=str(exc))
            return ""
    raise httpx.HTTPStatusError("Gemini rate limit exceeded after retries", request=response.request, response=response)


async def stream(system: str, prompt: str) -> AsyncGenerator[str, None]:
    """Stream Gemini response tokens via SSE. Retries on 429."""
    delay = _RETRY_DELAY
    for attempt in range(_MAX_RETRIES):
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", _generate_url(stream=True), json=_build_body(system, prompt)
            ) as response:
                if response.status_code == 429:
                    log.warning("gemini.stream: rate limited, retrying", attempt=attempt + 1, delay=delay)
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    try:
                        chunk = json.loads(payload)
                        text = chunk["candidates"][0]["content"]["parts"][0]["text"]
                        if text:
                            yield text
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
                return  # success — exit retry loop
    raise RuntimeError("Gemini stream rate limit exceeded after retries")
