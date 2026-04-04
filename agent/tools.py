"""Structured lookup tools for the F1 chatbot agent."""

from __future__ import annotations

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ingestion.core.config import settings
from ingestion.core.logging import get_logger

log = get_logger(__name__)


async def get_current_standings() -> str:
    """Fetch current race standings from OpenF1 API."""
    url = "https://api.openf1.org/v1/position?session_key=latest"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        log.warning("get_current_standings failed", error=str(exc))
        return "Current standings unavailable."

    if not data:
        return "Current standings unavailable."

    lines = [
        f"{i + 1}. {entry['driver_number']} — P{entry['position']}"
        for i, entry in enumerate(data)
    ]
    return "\n".join(lines)


async def get_race_results(year: int, gp: str) -> str:
    """Fetch race results from Jolpica/Ergast API for a given year and GP name."""
    url = f"https://api.jolpi.ca/ergast/f1/{year}/results.json?limit=100"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        log.warning("get_race_results failed", year=year, gp=gp, error=str(exc))
        return f"Race results for {year} {gp} unavailable."

    try:
        races = data["MRData"]["RaceTable"]["Races"]
    except (KeyError, TypeError):
        return f"Race results for {year} {gp} unavailable."

    gp_lower = gp.lower()
    matched_race = None
    for race in races:
        circuit_name = race.get("raceName", "").lower()
        circuit_id = race.get("Circuit", {}).get("circuitId", "").lower()
        circuit_locality = race.get("Circuit", {}).get("Location", {}).get("locality", "").lower()
        if gp_lower in circuit_name or gp_lower in circuit_id or gp_lower in circuit_locality:
            matched_race = race
            break

    if matched_race is None:
        return f"Race results for {year} {gp} unavailable."

    results = matched_race.get("Results", [])
    if not results:
        return f"Race results for {year} {gp} unavailable."

    top_3 = results[:3]
    lines = [f"Results for {year} {gp}:"]
    for entry in top_3:
        driver = entry.get("Driver", {})
        constructor = entry.get("Constructor", {})
        driver_name = f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip()
        constructor_name = constructor.get("name", "")
        position = entry.get("position", "?")
        lines.append(f"{position}. {driver_name} ({constructor_name})")

    return "\n".join(lines)


async def get_driver_stats(driver_name: str) -> str:
    """Look up a driver profile from the PostgreSQL chunks table."""
    engine = create_async_engine(settings.database_url, echo=False)
    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                text("""
                    SELECT content
                    FROM chunks
                    WHERE content_type = 'driver_profile'
                      AND metadata->>'name' ILIKE :name
                    LIMIT 1
                """),
                {"name": f"%{driver_name}%"},
            )
            row = result.fetchone()
    except Exception as exc:
        log.warning("get_driver_stats DB error", driver_name=driver_name, error=str(exc))
        return "Driver stats unavailable."
    finally:
        await engine.dispose()

    if row is None:
        return f"No stats found for {driver_name}."

    return row.content
