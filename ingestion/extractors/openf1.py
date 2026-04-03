"""OpenF1 API extractor — live session data for the current season."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx

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

BASE_URL = "https://api.openf1.org/v1"
# Delay between requests within a session — OpenF1 rate-limits aggressively
REQUEST_DELAY = 2.0


class OpenF1Extractor(BaseExtractor):
    """Fetch live F1 session data from the OpenF1 API.

    On first run (since=None) fetches all sessions from Jan 1 of the given
    season. On subsequent runs pass the last_synced_at timestamp to fetch
    only new sessions.
    """

    def __init__(
        self,
        season: int | None = None,
        since: datetime | None = None,
    ) -> None:
        self.season = season or datetime.now(tz=timezone.utc).year
        self.since = since
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": settings.user_agent},
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> list[dict]:
        """GET a list from the OpenF1 API.

        - 404: returns [] immediately (no data for this session/endpoint — not an error)
        - 429: waits for Retry-After then retries (up to max_retries attempts)
        - Other 4xx/5xx: raises after max_retries attempts
        """
        url = f"{BASE_URL}/{path}"

        for attempt in range(settings.max_retries):
            resp = await self._client.get(url, params=params)

            if resp.status_code == 404:
                # Endpoint has no data for these params (e.g. practice sessions
                # don't have position/stint/pit data) — return empty, don't retry.
                return []

            if resp.status_code == 429:
                retry_after = min(int(resp.headers.get("Retry-After", 15)), 60)
                log.warning(
                    "openf1.rate_limited",
                    url=url,
                    retry_after=retry_after,
                    attempt=attempt + 1,
                )
                await asyncio.sleep(retry_after)
                continue

            resp.raise_for_status()
            return resp.json()

        # Exhausted retries — raise the last response's error
        resp.raise_for_status()
        return []  # unreachable but keeps type checker happy

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    async def extract(self) -> AsyncIterator[RawDocument]:  # type: ignore[override]
        log.info("openf1.start", season=self.season, since=self.since)

        sessions = await self._fetch_sessions()
        if not sessions:
            log.info("openf1.no_sessions")
            await self._client.aclose()
            return

        log.info("openf1.sessions_found", count=len(sessions))

        # Yield each session as a document
        for session in sessions:
            yield self._session_doc(session)
            await asyncio.sleep(0)

        await asyncio.sleep(settings.request_delay_seconds)

        # Drivers for the season
        async for doc in self._extract_drivers():
            yield doc

        await asyncio.sleep(settings.request_delay_seconds)

        # Per-session detail data — limit to recent sessions to avoid hammering
        # the API with hundreds of requests on a full run.
        detail_cutoff = self.since or (
            datetime.now(tz=timezone.utc) - timedelta(days=30)
        )
        recent_sessions = [
            s for s in sessions
            if (s.get("date_start") or "") >= detail_cutoff.strftime("%Y-%m-%d")
        ]
        log.info("openf1.detail_sessions", total=len(sessions), recent=len(recent_sessions))

        for session in recent_sessions:
            session_key = session.get("session_key")
            if not session_key:
                continue

            async for doc in self._extract_session_detail(session_key, session):
                yield doc

            await asyncio.sleep(REQUEST_DELAY)

        await self._client.aclose()
        log.info("openf1.done")

    async def _fetch_sessions(self) -> list[dict]:
        """Return sessions for this season, optionally filtered by since."""
        season_start = f"{self.season}-01-01"
        params: dict = {"date_start>": season_start}

        if self.since:
            since_str = self.since.strftime("%Y-%m-%dT%H:%M:%S")
            params["date_start>"] = since_str

        try:
            return await self._get("sessions", params)
        except Exception as exc:
            log.error("openf1.sessions.fail", error=str(exc))
            return []

    def _session_doc(self, session: dict) -> RawDocument:
        session_key = session.get("session_key", "")
        session_name = session.get("session_name", "")
        gp_name = session.get("meeting_name", "")
        date = session.get("date_start", "")
        circuit = session.get("circuit_short_name", "")
        country = session.get("country_name", "")

        lines = [
            f"Session: {gp_name} {self.season} — {session_name}",
            f"Date: {date[:10] if date else 'Unknown'}",
        ]
        if circuit:
            lines.append(f"Circuit: {circuit}")
        if country:
            lines.append(f"Country: {country}")

        return RawDocument(
            source=SourceType.OPENF1,
            content_type=ContentType.RACE_RESULT,
            partition=KBPartition.LIVE,
            raw_content=json.dumps(session),
            metadata={
                "session_key": session_key,
                "session_name": session_name,
                "meeting_name": gp_name,
                "season": self.season,
                "narrative": "\n".join(lines),
            },
        )

    async def _extract_drivers(self) -> AsyncIterator[RawDocument]:
        log.info("openf1.drivers", season=self.season)
        try:
            items = await self._get("drivers", {"session_key": "latest"})
        except Exception as exc:
            log.error("openf1.drivers.fail", error=str(exc))
            return

        seen: set[str] = set()
        for drv in items:
            # Deduplicate by driver_number within a single fetch
            key = str(drv.get("driver_number", drv.get("name_acronym", "")))
            if key in seen:
                continue
            seen.add(key)

            yield RawDocument(
                source=SourceType.OPENF1,
                content_type=ContentType.DRIVER_PROFILE,
                partition=KBPartition.LIVE,
                raw_content=json.dumps(drv),
                metadata={
                    "driver_number": drv.get("driver_number"),
                    "full_name": drv.get("full_name", ""),
                    "season": self.season,
                },
            )
            await asyncio.sleep(0)

    async def _extract_session_detail(
        self, session_key: int | str, session_meta: dict
    ) -> AsyncIterator[RawDocument]:
        """Fetch position, stints, and pit data for one session."""
        gp_name = session_meta.get("meeting_name", "")
        session_name = session_meta.get("session_name", "")

        # Position data
        try:
            positions = await self._get("position", {"session_key": session_key})
            if positions:
                yield self._position_doc(positions, session_key, gp_name, session_name)
        except Exception as exc:
            log.warning("openf1.position.fail", session_key=session_key, error=str(exc))

        await asyncio.sleep(REQUEST_DELAY)

        # Stints
        try:
            stints = await self._get("stints", {"session_key": session_key})
            if stints:
                yield self._stints_doc(stints, session_key, gp_name, session_name)
        except Exception as exc:
            log.warning("openf1.stints.fail", session_key=session_key, error=str(exc))

        await asyncio.sleep(REQUEST_DELAY)

        # Pit stops
        try:
            pits = await self._get("pit", {"session_key": session_key})
            if pits:
                yield self._pit_doc(pits, session_key, gp_name, session_name)
        except Exception as exc:
            log.warning("openf1.pit.fail", session_key=session_key, error=str(exc))

        await asyncio.sleep(REQUEST_DELAY)

    def _position_doc(
        self,
        positions: list[dict],
        session_key: int | str,
        gp_name: str,
        session_name: str,
    ) -> RawDocument:
        # Take the last known position for each driver (final classification)
        latest: dict[int, dict] = {}
        for entry in positions:
            dn = entry.get("driver_number")
            if dn is not None:
                latest[dn] = entry

        lines = [f"Position data: {gp_name} — {session_name}"]
        for pos_entry in sorted(latest.values(), key=lambda x: x.get("position", 99)):
            pos = pos_entry.get("position", "?")
            driver = pos_entry.get("driver_number", "?")
            lines.append(f"P{pos}: Driver #{driver}")

        return RawDocument(
            source=SourceType.OPENF1,
            content_type=ContentType.RACE_RESULT,
            partition=KBPartition.LIVE,
            raw_content=json.dumps({"session_key": session_key, "positions": list(latest.values())}),
            metadata={
                "session_key": session_key,
                "meeting_name": gp_name,
                "session_name": session_name,
                "data_type": "position",
                "narrative": "\n".join(lines),
            },
        )

    def _stints_doc(
        self,
        stints: list[dict],
        session_key: int | str,
        gp_name: str,
        session_name: str,
    ) -> RawDocument:
        lines = [f"Tyre stints: {gp_name} — {session_name}"]
        for stint in stints:
            driver = stint.get("driver_number", "?")
            compound = stint.get("compound", "?")
            lap_start = stint.get("lap_start", "?")
            lap_end = stint.get("lap_end", "?")
            lines.append(f"Driver #{driver}: {compound} (laps {lap_start}–{lap_end})")

        return RawDocument(
            source=SourceType.OPENF1,
            content_type=ContentType.RACE_RESULT,
            partition=KBPartition.LIVE,
            raw_content=json.dumps({"session_key": session_key, "stints": stints}),
            metadata={
                "session_key": session_key,
                "meeting_name": gp_name,
                "session_name": session_name,
                "data_type": "stints",
                "narrative": "\n".join(lines),
            },
        )

    def _pit_doc(
        self,
        pits: list[dict],
        session_key: int | str,
        gp_name: str,
        session_name: str,
    ) -> RawDocument:
        lines = [f"Pit stops: {gp_name} — {session_name}"]
        for pit in pits:
            driver = pit.get("driver_number", "?")
            lap = pit.get("lap_number", "?")
            duration = pit.get("pit_duration", "?")
            lines.append(f"Driver #{driver}: lap {lap} — {duration}s")

        return RawDocument(
            source=SourceType.OPENF1,
            content_type=ContentType.RACE_RESULT,
            partition=KBPartition.LIVE,
            raw_content=json.dumps({"session_key": session_key, "pits": pits}),
            metadata={
                "session_key": session_key,
                "meeting_name": gp_name,
                "session_name": session_name,
                "data_type": "pit",
                "narrative": "\n".join(lines),
            },
        )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(
                f"{BASE_URL}/sessions",
                params={"session_key": "latest"},
                timeout=10.0,
            )
            return resp.status_code == 200
        except Exception:
            return False
