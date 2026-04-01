"""Wikipedia extractor — fetches per-section content for F1 articles."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ingestion.core.config import settings
from ingestion.core.logging import get_logger
from ingestion.core.models import (
    ContentType,
    KBPartition,
    RawDocument,
    SourceType,
)
from ingestion.extractors.base import BaseExtractor

log = get_logger(__name__)

API_URL = "https://en.wikipedia.org/w/api.php"

# -----------------------------------------------------------------------
# Article lists
# -----------------------------------------------------------------------

DRIVER_ARTICLES = [
    "Michael Schumacher", "Ayrton Senna", "Alain Prost",
    "Lewis Hamilton", "Max Verstappen", "Sebastian Vettel",
    "Fernando Alonso", "Niki Lauda", "Jim Clark",
    "Juan Manuel Fangio", "Jackie Stewart", "Nigel Mansell",
    "Mika Häkkinen", "Kimi Räikkönen", "Nelson Piquet",
    "Emerson Fittipaldi", "Jenson Button", "Damon Hill",
    "Lando Norris", "Charles Leclerc", "Carlos Sainz Jr.",
    "Daniel Ricciardo", "Valtteri Bottas", "Oscar Piastri",
    "George Russell (racing driver)",
]

CONSTRUCTOR_ARTICLES = [
    "Scuderia Ferrari", "McLaren", "Mercedes-Benz in Formula One",
    "Red Bull Racing", "Williams Racing", "Lotus 49",
    "Renault in Formula One", "Aston Martin in Formula One",
    "Alpine F1 Team", "Haas F1 Team",
]

CIRCUIT_ARTICLES = [
    "Circuit de Monaco", "Silverstone Circuit", "Monza Circuit",
    "Spa-Francorchamps", "Suzuka International Racing Course",
    "Interlagos", "Circuit de Barcelona-Catalunya",
    "Hungaroring", "Circuit Gilles Villeneuve",
    "Bahrain International Circuit", "Yas Marina Circuit",
    "Jeddah Corniche Circuit", "Las Vegas Grand Prix",
]

TOPIC_ARTICLES = [
    "Formula One", "Formula One car", "History of Formula One",
    "Formula One regulations", "DRS (Formula One)",
    "Formula One tyres", "FIA", "Formula One World Championship",
    "List of Formula One World Drivers' Champions",
    "Formula One Group",
]

ALL_ARTICLES = DRIVER_ARTICLES + CONSTRUCTOR_ARTICLES + CIRCUIT_ARTICLES + TOPIC_ARTICLES


class WikipediaExtractor(BaseExtractor):
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": settings.user_agent},
        )

    # ------------------------------------------------------------------
    # Wikitext cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_wikitext(text: str) -> str:
        # Strip {{templates}}
        text = re.sub(r"\{\{[^}]*\}\}", "", text)
        # Unwrap [[link|display]] -> display, [[link]] -> link
        text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
        # Remove <ref>...</ref> and <ref ... />
        text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
        text = re.sub(r"<ref[^/]*/\s*>", "", text)
        # Remove remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Normalise whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _api_get(self, params: dict) -> dict:
        resp = await self._client.get(API_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _get_intro(self, title: str) -> str | None:
        data = await self._api_get({
            "action": "query",
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "titles": title,
            "format": "json",
        })
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            extract = page.get("extract", "")
            if extract:
                return extract
        return None

    async def _get_sections(self, title: str) -> list[dict]:
        data = await self._api_get({
            "action": "parse",
            "page": title,
            "prop": "sections",
            "format": "json",
        })
        return data.get("parse", {}).get("sections", [])

    async def _get_section_text(self, title: str, section_index: int) -> str:
        data = await self._api_get({
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "section": section_index,
            "format": "json",
        })
        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        return self._clean_wikitext(wikitext)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    async def extract(self) -> AsyncIterator[RawDocument]:  # type: ignore[override]
        log.info("wikipedia.start", articles=len(ALL_ARTICLES))

        for title in ALL_ARTICLES:
            log.info("wikipedia.article", title=title)
            try:
                async for doc in self._extract_article(title):
                    yield doc
            except Exception as exc:
                log.error("wikipedia.article_error", title=title, error=str(exc))

            await asyncio.sleep(settings.request_delay_seconds)

        await self._client.aclose()
        log.info("wikipedia.done")

    async def _extract_article(self, title: str) -> AsyncIterator[RawDocument]:
        # Intro section
        intro = await self._get_intro(title)
        if intro and len(intro.strip()) > 50:
            yield RawDocument(
                source=SourceType.WIKIPEDIA,
                content_type=ContentType.NARRATIVE,
                partition=KBPartition.STATIC,
                raw_content=f"{title}\n\n{intro}",
                metadata={"article": title, "section": "intro"},
            )

        await asyncio.sleep(0.2)

        # Per-section
        sections = await self._get_sections(title)
        for sec in sections:
            idx = int(sec.get("index", 0))
            sec_title = sec.get("line", "")

            # Skip boilerplate sections
            if sec_title.lower() in {
                "references", "external links", "see also",
                "notes", "further reading", "bibliography",
            }:
                continue

            text = await self._get_section_text(title, idx)
            if len(text.strip()) < 50:
                continue

            yield RawDocument(
                source=SourceType.WIKIPEDIA,
                content_type=ContentType.NARRATIVE,
                partition=KBPartition.STATIC,
                raw_content=f"{title} — {sec_title}\n\n{text}",
                metadata={
                    "article": title,
                    "section": sec_title,
                    "section_index": idx,
                },
            )

            await asyncio.sleep(0.2)

    async def health_check(self) -> bool:
        try:
            data = await self._api_get({
                "action": "query",
                "meta": "siteinfo",
                "format": "json",
            })
            return "query" in data
        except Exception:
            return False
