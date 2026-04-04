"""Standings endpoints — fetches current season standings from Jolpica."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from api.schemas import ConstructorStanding, DriverStanding
from ingestion.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/standings")

_JOLPICA_DRIVERS = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"
_JOLPICA_CONSTRUCTORS = "https://api.jolpi.ca/ergast/f1/current/constructorStandings.json"


@router.get("/drivers", response_model=list[DriverStanding])
async def driver_standings() -> list[DriverStanding]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_JOLPICA_DRIVERS)
            resp.raise_for_status()
            data = resp.json()
        rows = data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
    except Exception as exc:
        log.warning("driver_standings fetch failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Standings unavailable") from exc

    return [
        DriverStanding(
            position=int(r["position"]),
            driver=f"{r['Driver']['givenName']} {r['Driver']['familyName']}",
            team=r["Constructors"][0]["name"],
            points=int(r["points"]),
        )
        for r in rows
    ]


@router.get("/constructors", response_model=list[ConstructorStanding])
async def constructor_standings() -> list[ConstructorStanding]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_JOLPICA_CONSTRUCTORS)
            resp.raise_for_status()
            data = resp.json()
        rows = data["MRData"]["StandingsTable"]["StandingsLists"][0]["ConstructorStandings"]
    except Exception as exc:
        log.warning("constructor_standings fetch failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Standings unavailable") from exc

    return [
        ConstructorStanding(
            position=int(r["position"]),
            team=r["Constructor"]["name"],
            points=int(r["points"]),
        )
        for r in rows
    ]
