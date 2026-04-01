"""Tests for Jolpica and Wikipedia extractors."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from ingestion.core.models import ContentType, KBPartition, SourceType
from ingestion.extractors.jolpica import JolpicaExtractor
from ingestion.extractors.wikipedia import WikipediaExtractor


# -----------------------------------------------------------------------
# Jolpica extractor tests
# -----------------------------------------------------------------------

def _jolpica_response(table_key: str, list_key: str, items: list, total: int | None = None) -> dict:
    if total is None:
        total = len(items)
    return {
        "MRData": {
            "total": str(total),
            table_key: {list_key: items},
        }
    }


@pytest.mark.asyncio
@respx.mock
async def test_jolpica_extracts_drivers():
    driver = {
        "driverId": "hamilton",
        "givenName": "Lewis",
        "familyName": "Hamilton",
        "nationality": "British",
        "dateOfBirth": "1985-01-07",
        "permanentNumber": "44",
    }
    respx.get("https://api.jolpi.ca/ergast/f1/drivers.json").mock(
        return_value=httpx.Response(
            200,
            json=_jolpica_response("DriverTable", "Drivers", [driver]),
        )
    )
    # Mock race/qualifying/standings endpoints to return empty for year range
    respx.get(url__regex=r".*/\d{4}/.*\.json").mock(
        return_value=httpx.Response(
            200,
            json=_jolpica_response("RaceTable", "Races", [], total=0),
        )
    )
    respx.get("https://api.jolpi.ca/ergast/f1/constructors.json").mock(
        return_value=httpx.Response(
            200,
            json=_jolpica_response("ConstructorTable", "Constructors", []),
        )
    )

    extractor = JolpicaExtractor(start_year=2024, end_year=2024)
    docs = []
    async for doc in extractor.extract():
        docs.append(doc)

    driver_docs = [d for d in docs if d.content_type == ContentType.DRIVER_PROFILE]
    assert len(driver_docs) == 1
    assert driver_docs[0].source == SourceType.JOLPICA
    assert driver_docs[0].partition == KBPartition.STATIC

    data = json.loads(driver_docs[0].raw_content)
    assert data["driverId"] == "hamilton"


@pytest.mark.asyncio
@respx.mock
async def test_jolpica_fingerprint_changes_with_content():
    d1 = {"driverId": "hamilton", "givenName": "Lewis"}
    d2 = {"driverId": "hamilton", "givenName": "Lewis", "extra": "data"}

    from ingestion.core.models import RawDocument

    doc1 = RawDocument(
        source=SourceType.JOLPICA,
        content_type=ContentType.DRIVER_PROFILE,
        partition=KBPartition.STATIC,
        raw_content=json.dumps(d1),
    )
    doc2 = RawDocument(
        source=SourceType.JOLPICA,
        content_type=ContentType.DRIVER_PROFILE,
        partition=KBPartition.STATIC,
        raw_content=json.dumps(d2),
    )
    assert doc1.fingerprint != doc2.fingerprint


# -----------------------------------------------------------------------
# Wikipedia extractor tests
# -----------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_wikipedia_extracts_sections():
    # Mock intro
    respx.get("https://en.wikipedia.org/w/api.php").mock(
        side_effect=_wikipedia_mock_handler,
    )

    extractor = WikipediaExtractor()
    # Override article list for test
    import ingestion.extractors.wikipedia as wiki_mod
    original = wiki_mod.ALL_ARTICLES
    wiki_mod.ALL_ARTICLES = ["Formula One"]

    docs = []
    try:
        async for doc in extractor.extract():
            docs.append(doc)
    finally:
        wiki_mod.ALL_ARTICLES = original

    assert len(docs) >= 1
    assert all(d.source == SourceType.WIKIPEDIA for d in docs)
    assert all(d.content_type == ContentType.NARRATIVE for d in docs)
    assert all(d.partition == KBPartition.STATIC for d in docs)


def _wikipedia_mock_handler(request: httpx.Request) -> httpx.Response:
    params = dict(request.url.params)
    action = params.get("action", "")

    if action == "query" and "extracts" in params.get("prop", ""):
        return httpx.Response(200, json={
            "query": {
                "pages": {
                    "1": {
                        "title": "Formula One",
                        "extract": "Formula One is the highest class of international racing. " * 5,
                    }
                }
            }
        })

    if action == "parse" and params.get("prop") == "sections":
        return httpx.Response(200, json={
            "parse": {
                "sections": [
                    {"index": "1", "line": "History"},
                    {"index": "2", "line": "References"},
                ]
            }
        })

    if action == "parse" and params.get("prop") == "wikitext":
        return httpx.Response(200, json={
            "parse": {
                "wikitext": {
                    "*": "Formula One has a long history dating back to 1950. " * 5,
                }
            }
        })

    if action == "query" and params.get("meta") == "siteinfo":
        return httpx.Response(200, json={"query": {"general": {}}})

    return httpx.Response(200, json={})


@pytest.mark.asyncio
async def test_wikipedia_clean_wikitext():
    cleaned = WikipediaExtractor._clean_wikitext(
        "Hello {{citation needed}} [[Lewis Hamilton|Hamilton]] <ref>some ref</ref> world"
    )
    assert "{{" not in cleaned
    assert "[[" not in cleaned
    assert "<ref" not in cleaned
    assert "Hamilton" in cleaned
    assert "world" in cleaned
