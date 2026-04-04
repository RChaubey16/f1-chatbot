"""Tests for agent/tools.py: get_current_standings and get_race_results."""

from __future__ import annotations

import httpx
import pytest
import respx

from agent.tools import get_current_standings, get_race_results

_OPENF1_URL = "https://api.openf1.org/v1/position"
_JOLPICA_URL_2023 = "https://api.jolpi.ca/ergast/f1/2023/results.json"

# ---------------------------------------------------------------------------
# get_current_standings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_current_standings_success():
    payload = [
        {"driver_number": 1, "position": 1},
        {"driver_number": 11, "position": 2},
        {"driver_number": 44, "position": 3},
    ]
    with respx.mock:
        respx.get(_OPENF1_URL).mock(return_value=httpx.Response(200, json=payload))
        result = await get_current_standings()

    assert "1" in result
    assert "11" in result
    assert "44" in result


@pytest.mark.asyncio
async def test_get_current_standings_empty_data():
    with respx.mock:
        respx.get(_OPENF1_URL).mock(return_value=httpx.Response(200, json=[]))
        result = await get_current_standings()

    assert result == "Current standings unavailable."


@pytest.mark.asyncio
async def test_get_current_standings_http_error():
    with respx.mock:
        respx.get(_OPENF1_URL).mock(return_value=httpx.Response(503))
        result = await get_current_standings()

    assert result == "Current standings unavailable."


@pytest.mark.asyncio
async def test_get_current_standings_network_error():
    with respx.mock:
        respx.get(_OPENF1_URL).mock(side_effect=httpx.ConnectError("timeout"))
        result = await get_current_standings()

    assert result == "Current standings unavailable."


# ---------------------------------------------------------------------------
# get_race_results
# ---------------------------------------------------------------------------

def _jolpica_payload(race_name: str, locality: str = "") -> dict:
    return {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "raceName": race_name,
                        "Circuit": {
                            "circuitId": "monaco",
                            "Location": {"locality": locality},
                        },
                        "Results": [
                            {
                                "position": "1",
                                "Driver": {"givenName": "Max", "familyName": "Verstappen"},
                                "Constructor": {"name": "Red Bull"},
                            },
                            {
                                "position": "2",
                                "Driver": {"givenName": "Fernando", "familyName": "Alonso"},
                                "Constructor": {"name": "Aston Martin"},
                            },
                            {
                                "position": "3",
                                "Driver": {"givenName": "Lewis", "familyName": "Hamilton"},
                                "Constructor": {"name": "Mercedes"},
                            },
                        ],
                    }
                ]
            }
        }
    }


@pytest.mark.asyncio
async def test_get_race_results_match_by_name():
    with respx.mock:
        respx.get(_JOLPICA_URL_2023).mock(
            return_value=httpx.Response(200, json=_jolpica_payload("Monaco Grand Prix"))
        )
        result = await get_race_results(2023, "monaco")

    assert "Verstappen" in result
    assert "Alonso" in result
    assert "Hamilton" in result


@pytest.mark.asyncio
async def test_get_race_results_match_by_locality():
    with respx.mock:
        respx.get(_JOLPICA_URL_2023).mock(
            return_value=httpx.Response(
                200, json=_jolpica_payload("Grand Prix de Monaco", locality="Monte-Carlo")
            )
        )
        result = await get_race_results(2023, "monte-carlo")

    assert "Verstappen" in result


@pytest.mark.asyncio
async def test_get_race_results_no_match():
    with respx.mock:
        respx.get(_JOLPICA_URL_2023).mock(
            return_value=httpx.Response(200, json=_jolpica_payload("Monaco Grand Prix"))
        )
        result = await get_race_results(2023, "silverstone")

    assert "unavailable" in result.lower()


@pytest.mark.asyncio
async def test_get_race_results_http_error():
    with respx.mock:
        respx.get(_JOLPICA_URL_2023).mock(return_value=httpx.Response(500))
        result = await get_race_results(2023, "monaco")

    assert "unavailable" in result.lower()


@pytest.mark.asyncio
async def test_get_race_results_malformed_response():
    with respx.mock:
        respx.get(_JOLPICA_URL_2023).mock(
            return_value=httpx.Response(200, json={"unexpected": "schema"})
        )
        result = await get_race_results(2023, "monaco")

    assert "unavailable" in result.lower()
