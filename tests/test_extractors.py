"""Tests for Jolpica, Wikipedia, OpenF1, and News extractors."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from ingestion.core.models import ContentType, KBPartition, SourceType
from ingestion.extractors.jolpica import JolpicaExtractor
from ingestion.extractors.news import NewsExtractor
from ingestion.extractors.openf1 import OpenF1Extractor
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


# -----------------------------------------------------------------------
# OpenF1 extractor tests
# -----------------------------------------------------------------------

def _openf1_session() -> dict:
    return {
        "session_key": 9158,
        "session_name": "Race",
        "meeting_name": "Australian Grand Prix",
        "date_start": "2024-03-24T05:00:00",
        "circuit_short_name": "Albert Park",
        "country_name": "Australia",
    }


@pytest.mark.asyncio
@respx.mock
async def test_openf1_extracts_sessions():
    session = _openf1_session()

    respx.get("https://api.openf1.org/v1/sessions").mock(
        return_value=httpx.Response(200, json=[session])
    )
    respx.get("https://api.openf1.org/v1/drivers").mock(
        return_value=httpx.Response(200, json=[])
    )
    # Mock all per-session detail endpoints to return empty
    respx.get("https://api.openf1.org/v1/position").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://api.openf1.org/v1/stints").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://api.openf1.org/v1/pit").mock(
        return_value=httpx.Response(200, json=[])
    )

    extractor = OpenF1Extractor(season=2024)
    docs = [doc async for doc in extractor.extract()]

    session_docs = [d for d in docs if d.content_type == ContentType.RACE_RESULT]
    assert len(session_docs) >= 1
    assert session_docs[0].source == SourceType.OPENF1
    assert session_docs[0].partition == KBPartition.LIVE

    data = json.loads(session_docs[0].raw_content)
    assert data["session_key"] == 9158
    assert data["meeting_name"] == "Australian Grand Prix"


@pytest.mark.asyncio
@respx.mock
async def test_openf1_extracts_stints():
    session = _openf1_session()
    stints = [
        {"driver_number": 1, "compound": "MEDIUM", "lap_start": 1, "lap_end": 18},
        {"driver_number": 1, "compound": "HARD", "lap_start": 19, "lap_end": 57},
    ]

    respx.get("https://api.openf1.org/v1/sessions").mock(
        return_value=httpx.Response(200, json=[session])
    )
    respx.get("https://api.openf1.org/v1/drivers").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://api.openf1.org/v1/position").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://api.openf1.org/v1/stints").mock(
        return_value=httpx.Response(200, json=stints)
    )
    respx.get("https://api.openf1.org/v1/pit").mock(
        return_value=httpx.Response(200, json=[])
    )

    extractor = OpenF1Extractor(season=2024)
    docs = [doc async for doc in extractor.extract()]

    stint_docs = [d for d in docs if d.metadata.get("data_type") == "stints"]
    assert len(stint_docs) == 1
    assert "MEDIUM" in stint_docs[0].metadata["narrative"]
    assert "HARD" in stint_docs[0].metadata["narrative"]


@pytest.mark.asyncio
@respx.mock
async def test_openf1_returns_empty_on_no_sessions():
    respx.get("https://api.openf1.org/v1/sessions").mock(
        return_value=httpx.Response(200, json=[])
    )

    extractor = OpenF1Extractor(season=2024)
    docs = [doc async for doc in extractor.extract()]
    assert docs == []


# -----------------------------------------------------------------------
# News extractor tests
# -----------------------------------------------------------------------

_INDEX_HTML = """
<html><body>
  <article>
    <a href="/f1/news/verstappen-wins-2024-bahrain-gp/123/">Verstappen wins</a>
  </article>
  <article>
    <a href="/f1/news/hamilton-mercedes-contract/456/">Hamilton contract</a>
  </article>
</body></html>
"""

_ARTICLE_HTML = """
<html>
<head>
  <meta property="article:published_time" content="2024-03-02T15:00:00+00:00">
  <meta name="author" content="Jane Doe">
  <meta name="keywords" content="f1, verstappen, bahrain">
</head>
<body>
  <h1>Verstappen wins 2024 Bahrain GP</h1>
  <article>
    <div class="ms-article-content">
      <p>Max Verstappen claimed victory at the 2024 Bahrain Grand Prix.</p>
      <p>He led from pole position and managed his tyres brilliantly.</p>
    </div>
  </article>
</body>
</html>
"""


@pytest.mark.asyncio
@respx.mock
async def test_news_extracts_articles():
    respx.get("https://www.motorsport.com/f1/news/").mock(
        return_value=httpx.Response(200, text=_INDEX_HTML)
    )
    respx.get(url__regex=r".*motorsport\.com/f1/news/.*").mock(
        return_value=httpx.Response(200, text=_ARTICLE_HTML)
    )

    extractor = NewsExtractor(max_articles=5)
    docs = [doc async for doc in extractor.extract()]

    assert len(docs) >= 1
    assert docs[0].source == SourceType.NEWS
    assert docs[0].content_type == ContentType.NARRATIVE
    assert docs[0].partition == KBPartition.LIVE
    assert "Verstappen" in docs[0].raw_content
    assert docs[0].metadata["url"].startswith("https://www.motorsport.com/f1/news/")


@pytest.mark.asyncio
@respx.mock
async def test_news_skips_known_urls():
    respx.get("https://www.motorsport.com/f1/news/").mock(
        return_value=httpx.Response(200, text=_INDEX_HTML)
    )
    respx.get(url__regex=r".*motorsport\.com/f1/news/.*").mock(
        return_value=httpx.Response(200, text=_ARTICLE_HTML)
    )

    # url_exists_fn always returns True — all articles should be skipped
    async def always_exists(url: str) -> bool:
        return True

    extractor = NewsExtractor(max_articles=5, url_exists_fn=always_exists)
    docs = [doc async for doc in extractor.extract()]
    assert docs == []


@pytest.mark.asyncio
@respx.mock
async def test_news_returns_empty_on_broken_layout():
    # Index returns HTML with no article links
    respx.get("https://www.motorsport.com/f1/news/").mock(
        return_value=httpx.Response(200, text="<html><body><p>Nothing here</p></body></html>")
    )

    extractor = NewsExtractor(max_articles=5)
    docs = [doc async for doc in extractor.extract()]
    # Should yield 0 docs, not raise
    assert docs == []
