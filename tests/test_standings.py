"""Tests for GET /standings/drivers and GET /standings/constructors."""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from unittest.mock import MagicMock, AsyncMock

_JOLPICA_DRIVERS_URL = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"
_JOLPICA_CONSTRUCTORS_URL = "https://api.jolpi.ca/ergast/f1/current/constructorStandings.json"


def _driver_standings_payload() -> dict:
    return {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "DriverStandings": [
                            {
                                "position": "1",
                                "points": "136",
                                "Driver": {"givenName": "Max", "familyName": "Verstappen"},
                                "Constructors": [{"name": "Red Bull Racing"}],
                            },
                            {
                                "position": "2",
                                "points": "113",
                                "Driver": {"givenName": "Lando", "familyName": "Norris"},
                                "Constructors": [{"name": "McLaren"}],
                            },
                        ]
                    }
                ]
            }
        }
    }


def _constructor_standings_payload() -> dict:
    return {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "ConstructorStandings": [
                            {
                                "position": "1",
                                "points": "249",
                                "Constructor": {"name": "Red Bull Racing"},
                            },
                            {
                                "position": "2",
                                "points": "174",
                                "Constructor": {"name": "McLaren"},
                            },
                        ]
                    }
                ]
            }
        }
    }


@pytest.fixture()
async def test_client():
    from api.main import app
    mock_agent = MagicMock()
    mock_agent.close = AsyncMock()
    app.state.agent = mock_agent
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_driver_standings_success(test_client):
    with respx.mock:
        respx.get(_JOLPICA_DRIVERS_URL).mock(
            return_value=httpx.Response(200, json=_driver_standings_payload())
        )
        response = await test_client.get("/standings/drivers")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["position"] == 1
    assert data[0]["driver"] == "Max Verstappen"
    assert data[0]["team"] == "Red Bull Racing"
    assert data[0]["points"] == 136.0


@pytest.mark.asyncio
async def test_driver_standings_api_error_returns_503(test_client):
    with respx.mock:
        respx.get(_JOLPICA_DRIVERS_URL).mock(return_value=httpx.Response(503))
        response = await test_client.get("/standings/drivers")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_constructor_standings_success(test_client):
    with respx.mock:
        respx.get(_JOLPICA_CONSTRUCTORS_URL).mock(
            return_value=httpx.Response(200, json=_constructor_standings_payload())
        )
        response = await test_client.get("/standings/constructors")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["position"] == 1
    assert data[0]["team"] == "Red Bull Racing"
    assert data[0]["points"] == 249.0


@pytest.mark.asyncio
async def test_constructor_standings_api_error_returns_503(test_client):
    with respx.mock:
        respx.get(_JOLPICA_CONSTRUCTORS_URL).mock(return_value=httpx.Response(503))
        response = await test_client.get("/standings/constructors")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_driver_standings_empty_season_returns_empty_list(test_client):
    payload = {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": []
            }
        }
    }
    with respx.mock:
        respx.get(_JOLPICA_DRIVERS_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        response = await test_client.get("/standings/drivers")

    assert response.status_code == 200
    assert response.json() == []
