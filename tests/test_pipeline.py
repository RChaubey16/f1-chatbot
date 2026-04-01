"""Tests for chunker and pipeline integration."""

from __future__ import annotations

import json

import pytest

from ingestion.core.models import (
    ContentType,
    KBPartition,
    RawDocument,
    SourceType,
)
from ingestion.transformers.chunker import Chunker


# -----------------------------------------------------------------------
# Chunker tests
# -----------------------------------------------------------------------


@pytest.fixture
def chunker() -> Chunker:
    return Chunker()


def _make_race_doc() -> RawDocument:
    race = {
        "raceName": "Monaco Grand Prix",
        "season": "2019",
        "round": "6",
        "Circuit": {"circuitName": "Circuit de Monaco"},
        "Results": [
            {
                "position": "1",
                "Driver": {"givenName": "Lewis", "familyName": "Hamilton"},
                "Constructor": {"name": "Mercedes"},
                "Time": {"time": "1:43:28.437"},
                "points": "25",
                "status": "Finished",
            },
            {
                "position": "2",
                "Driver": {"givenName": "Sebastian", "familyName": "Vettel"},
                "Constructor": {"name": "Ferrari"},
                "Time": {"time": "+2.654"},
                "points": "18",
                "status": "Finished",
            },
        ],
    }
    return RawDocument(
        source=SourceType.JOLPICA,
        content_type=ContentType.RACE_RESULT,
        partition=KBPartition.STATIC,
        raw_content=json.dumps(race),
        metadata={"year": 2019, "round": "6", "race_name": "Monaco Grand Prix"},
    )


def _make_driver_doc() -> RawDocument:
    driver = {
        "driverId": "hamilton",
        "givenName": "Lewis",
        "familyName": "Hamilton",
        "nationality": "British",
        "dateOfBirth": "1985-01-07",
        "permanentNumber": "44",
    }
    return RawDocument(
        source=SourceType.JOLPICA,
        content_type=ContentType.DRIVER_PROFILE,
        partition=KBPartition.STATIC,
        raw_content=json.dumps(driver),
    )


def _make_wiki_doc() -> RawDocument:
    content = (
        "Formula One — History\n\n"
        "Formula One has a rich history spanning more than 70 years. "
        "The first World Championship race was held at Silverstone in 1950. "
        "Since then the sport has grown into one of the most popular "
        "motorsport categories worldwide, attracting billions of viewers."
    )
    return RawDocument(
        source=SourceType.WIKIPEDIA,
        content_type=ContentType.NARRATIVE,
        partition=KBPartition.STATIC,
        raw_content=content,
        metadata={"article": "Formula One", "section": "History"},
    )


def test_chunk_race_result(chunker: Chunker):
    doc = _make_race_doc()
    chunks = chunker.chunk(doc)
    assert len(chunks) >= 1
    assert all(c.source == SourceType.JOLPICA for c in chunks)
    assert all(c.doc_fingerprint == doc.fingerprint for c in chunks)
    # Should contain prose, not raw JSON
    assert "Monaco Grand Prix" in chunks[0].content
    assert "P1:" in chunks[0].content or "Lewis Hamilton" in chunks[0].content


def test_chunk_driver_profile(chunker: Chunker):
    doc = _make_driver_doc()
    chunks = chunker.chunk(doc)
    assert len(chunks) >= 1
    assert "Lewis Hamilton" in chunks[0].content
    assert "British" in chunks[0].content


def test_chunk_wikipedia(chunker: Chunker):
    doc = _make_wiki_doc()
    chunks = chunker.chunk(doc)
    assert len(chunks) >= 1
    assert all(c.source == SourceType.WIKIPEDIA for c in chunks)
    assert "Silverstone" in chunks[0].content or "Formula One" in chunks[0].content


def test_chunk_ids_use_fingerprint(chunker: Chunker):
    doc = _make_race_doc()
    chunks = chunker.chunk(doc)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_id == f"{doc.fingerprint}_{i}"


def test_idempotent_fingerprint():
    """Same content produces same fingerprint — dedup works."""
    doc1 = _make_driver_doc()
    doc2 = _make_driver_doc()
    assert doc1.fingerprint == doc2.fingerprint


def test_different_content_different_fingerprint():
    doc1 = _make_driver_doc()
    doc2 = _make_wiki_doc()
    assert doc1.fingerprint != doc2.fingerprint
