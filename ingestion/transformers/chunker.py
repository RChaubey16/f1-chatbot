"""Source-aware chunking: structured JSON -> prose, then split."""

from __future__ import annotations

import json

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ingestion.core.config import settings
from ingestion.core.models import (
    Chunk,
    ContentType,
    RawDocument,
    SourceType,
)


class Chunker:
    def __init__(self) -> None:
        self._structured_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size_structured,
            chunk_overlap=settings.chunk_overlap,
        )
        self._narrative_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size_narrative,
            chunk_overlap=settings.chunk_overlap,
        )

    def chunk(self, doc: RawDocument) -> list[Chunk]:
        if doc.source == SourceType.JOLPICA:
            text = self._to_narrative(doc)
            splits = self._structured_splitter.split_text(text)
        else:
            text = doc.raw_content
            splits = self._narrative_splitter.split_text(text)

        fp = doc.fingerprint
        return [
            Chunk(
                chunk_id=f"{fp}_{i}",
                doc_fingerprint=fp,
                content=s,
                source=doc.source,
                content_type=doc.content_type,
                partition=doc.partition,
                metadata=doc.metadata,
            )
            for i, s in enumerate(splits)
        ]

    # ------------------------------------------------------------------
    # Structured -> prose converters
    # ------------------------------------------------------------------

    def _to_narrative(self, doc: RawDocument) -> str:
        data = json.loads(doc.raw_content)
        ct = doc.content_type

        if ct == ContentType.RACE_RESULT:
            return self._format_race_result(data, doc.metadata)
        if ct == ContentType.QUALIFYING_RESULT:
            return self._format_qualifying(data, doc.metadata)
        if ct == ContentType.DRIVER_PROFILE:
            return self._format_driver(data)
        if ct == ContentType.CONSTRUCTOR_PROFILE:
            return self._format_constructor(data)
        if ct == ContentType.STANDINGS:
            return self._format_standings(data, doc.metadata)

        # Fallback: pretty-print JSON
        return json.dumps(data, indent=2)

    @staticmethod
    def _format_race_result(data: dict, meta: dict) -> str:
        name = data.get("raceName", meta.get("race_name", "Unknown"))
        year = data.get("season", meta.get("year", ""))
        circuit = data.get("Circuit", {}).get("circuitName", "")

        lines = [f"Race: {name} {year}"]
        if circuit:
            lines.append(f"Circuit: {circuit}")

        results = data.get("Results", [])
        for r in results:
            pos = r.get("position", "?")
            driver = r.get("Driver", {})
            first = driver.get("givenName", "")
            last = driver.get("familyName", "")
            team = r.get("Constructor", {}).get("name", "")
            time_val = r.get("Time", {}).get("time", "")
            pts = r.get("points", "0")
            status = r.get("status", "")

            line = f"P{pos}: {first} {last} ({team})"
            if time_val:
                line += f" — {time_val}"
            if status and status != "Finished":
                line += f" [{status}]"
            line += f" [{pts} pts]"
            lines.append(line)

        return "\n".join(lines)

    @staticmethod
    def _format_qualifying(data: dict, meta: dict) -> str:
        name = data.get("raceName", meta.get("race_name", "Unknown"))
        year = data.get("season", meta.get("year", ""))

        lines = [f"Qualifying: {name} {year}"]

        results = data.get("QualifyingResults", [])
        for r in results:
            pos = r.get("position", "?")
            driver = r.get("Driver", {})
            first = driver.get("givenName", "")
            last = driver.get("familyName", "")
            q1 = r.get("Q1", "")
            q2 = r.get("Q2", "")
            q3 = r.get("Q3", "")

            line = f"P{pos}: {first} {last}"
            times = []
            if q1:
                times.append(f"Q1: {q1}")
            if q2:
                times.append(f"Q2: {q2}")
            if q3:
                times.append(f"Q3: {q3}")
            if times:
                line += " | " + " ".join(times)
            lines.append(line)

        return "\n".join(lines)

    @staticmethod
    def _format_driver(data: dict) -> str:
        first = data.get("givenName", "")
        last = data.get("familyName", "")
        nationality = data.get("nationality", "")
        dob = data.get("dateOfBirth", "")
        number = data.get("permanentNumber", "")

        lines = [f"Driver: {first} {last}"]
        if nationality:
            lines.append(f"Nationality: {nationality}")
        if dob:
            lines.append(f"DOB: {dob}")
        if number:
            lines.append(f"Permanent number: #{number}")
        return "\n".join(lines)

    @staticmethod
    def _format_constructor(data: dict) -> str:
        name = data.get("name", "")
        nationality = data.get("nationality", "")
        lines = [f"Constructor: {name}"]
        if nationality:
            lines.append(f"Nationality: {nationality}")
        return "\n".join(lines)

    @staticmethod
    def _format_standings(data: list | dict, meta: dict) -> str:
        year = meta.get("year", "")
        st_type = meta.get("standings_type", "driver")

        if isinstance(data, dict):
            data = [data]

        lines = [f"{year} {st_type.title()} Standings"]

        for entry in data:
            pos = entry.get("position", "?")
            pts = entry.get("points", "0")

            if st_type == "driver":
                drv = entry.get("Driver", {})
                name = f"{drv.get('givenName', '')} {drv.get('familyName', '')}".strip()
            else:
                con = entry.get("Constructor", {})
                name = con.get("name", "Unknown")

            lines.append(f"{pos}. {name} — {pts} pts")

        return "\n".join(lines)
