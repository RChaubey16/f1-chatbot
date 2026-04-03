"""Query router: classifies user queries into intents."""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    HISTORICAL = "historical"
    LIVE = "live"
    GENERAL = "general"


class Router:
    """Classifies a user query into an Intent."""

    async def route(self, query: str) -> Intent:
        raise NotImplementedError
