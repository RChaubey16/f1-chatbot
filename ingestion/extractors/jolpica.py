"""Jolpica (Ergast-compatible) F1 API extractor."""

from __future__ import annotations

import asyncio
import json
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

BASE_URL = "https://api.jolpi.ca/ergast/f1"
PAGE_LIMIT = 100


class JolpicaExtractor(BaseExtractor):
    def __init__(
        self,
        start_year: int = 1950,
        end_year: int = 2024,
    ) -> None:
        self.start_year = start_year
        self.end_year = end_year
        self._client = httpx.AsyncClient(timeout=30.0)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _get(self, url: str, params: dict | None = None) -> dict:
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _get_all_pages(self, path: str) -> list[dict]:
        """Fetch all pages from a paginated Jolpica endpoint."""
        offset = 0
        all_items: list[dict] = []

        while True:
            url = f"{BASE_URL}/{path}.json"
            data = await self._get(url, {"limit": PAGE_LIMIT, "offset": offset})

            # The response nests data under MRData -> <Table>
            mr = data.get("MRData", {})
            total = int(mr.get("total", 0))

            # Find the data table (e.g. RaceTable, DriverTable, etc.)
            table_key = next(
                (k for k in mr if k.endswith("Table")), None
            )
            if table_key is None:
                break

            table = mr[table_key]
            # Find the list key inside the table (e.g. Races, Drivers)
            list_key = next(
                (k for k in table if isinstance(table[k], list)), None
            )
            if list_key is None:
                break

            items = table[list_key]
            all_items.extend(items)

            offset += PAGE_LIMIT
            if offset >= total:
                break

            await asyncio.sleep(settings.request_delay_seconds)

        return all_items

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    async def extract(self) -> AsyncIterator[RawDocument]:  # type: ignore[override]
        log.info("jolpica.start", start=self.start_year, end=self.end_year)

        # --- Drivers ---
        async for doc in self._extract_drivers():
            yield doc

        # --- Constructors ---
        async for doc in self._extract_constructors():
            yield doc

        # --- Per-year data ---
        for year in range(self.start_year, self.end_year + 1):
            log.info("jolpica.year", year=year)

            async for doc in self._extract_race_results(year):
                yield doc
            async for doc in self._extract_qualifying(year):
                yield doc
            async for doc in self._extract_standings(year):
                yield doc

        await self._client.aclose()
        log.info("jolpica.done")

    async def _extract_drivers(self) -> AsyncIterator[RawDocument]:
        log.info("jolpica.drivers")
        items = await self._get_all_pages("drivers")
        for drv in items:
            yield RawDocument(
                source=SourceType.JOLPICA,
                content_type=ContentType.DRIVER_PROFILE,
                partition=KBPartition.STATIC,
                raw_content=json.dumps(drv),
                metadata={"driver_id": drv.get("driverId", "")},
            )
            await asyncio.sleep(0)  # yield control

    async def _extract_constructors(self) -> AsyncIterator[RawDocument]:
        log.info("jolpica.constructors")
        items = await self._get_all_pages("constructors")
        for con in items:
            yield RawDocument(
                source=SourceType.JOLPICA,
                content_type=ContentType.CONSTRUCTOR_PROFILE,
                partition=KBPartition.STATIC,
                raw_content=json.dumps(con),
                metadata={"constructor_id": con.get("constructorId", "")},
            )
            await asyncio.sleep(0)

    async def _extract_race_results(self, year: int) -> AsyncIterator[RawDocument]:
        items = await self._get_all_pages(f"{year}/results")
        for race in items:
            yield RawDocument(
                source=SourceType.JOLPICA,
                content_type=ContentType.RACE_RESULT,
                partition=KBPartition.STATIC,
                raw_content=json.dumps(race),
                metadata={
                    "year": year,
                    "round": race.get("round", ""),
                    "race_name": race.get("raceName", ""),
                },
            )
            await asyncio.sleep(0)

    async def _extract_qualifying(self, year: int) -> AsyncIterator[RawDocument]:
        # Qualifying data only available from ~1994 onwards
        if year < 1994:
            return
        items = await self._get_all_pages(f"{year}/qualifying")
        for race in items:
            yield RawDocument(
                source=SourceType.JOLPICA,
                content_type=ContentType.QUALIFYING_RESULT,
                partition=KBPartition.STATIC,
                raw_content=json.dumps(race),
                metadata={
                    "year": year,
                    "round": race.get("round", ""),
                    "race_name": race.get("raceName", ""),
                },
            )
            await asyncio.sleep(0)

    async def _extract_standings(self, year: int) -> AsyncIterator[RawDocument]:
        # Driver standings
        drv = await self._get_all_pages(f"{year}/driverStandings")
        if drv:
            yield RawDocument(
                source=SourceType.JOLPICA,
                content_type=ContentType.STANDINGS,
                partition=KBPartition.STATIC,
                raw_content=json.dumps(drv),
                metadata={"year": year, "standings_type": "driver"},
            )

        await asyncio.sleep(settings.request_delay_seconds)

        # Constructor standings
        con = await self._get_all_pages(f"{year}/constructorStandings")
        if con:
            yield RawDocument(
                source=SourceType.JOLPICA,
                content_type=ContentType.STANDINGS,
                partition=KBPartition.STATIC,
                raw_content=json.dumps(con),
                metadata={"year": year, "standings_type": "constructor"},
            )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{BASE_URL}/status.json", timeout=10.0)
            return resp.status_code == 200
        except Exception:
            # Fallback: try fetching a simple endpoint
            try:
                resp = await self._client.get(
                    f"{BASE_URL}/drivers.json",
                    params={"limit": 1},
                    timeout=10.0,
                )
                return resp.status_code == 200
            except Exception:
                return False
