"""Pydantic models shared across all pipeline stages."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import xxhash


class SourceType(str, enum.Enum):
    JOLPICA = "jolpica"
    WIKIPEDIA = "wikipedia"
    OPENF1 = "openf1"
    NEWS = "news"


class ContentType(str, enum.Enum):
    RACE_RESULT = "race_result"
    QUALIFYING_RESULT = "qualifying_result"
    STANDINGS = "standings"
    DRIVER_PROFILE = "driver_profile"
    CONSTRUCTOR_PROFILE = "constructor_profile"
    NARRATIVE = "narrative"


class KBPartition(str, enum.Enum):
    STATIC = "static"
    LIVE = "live"


@dataclass
class RawDocument:
    source: SourceType
    content_type: ContentType
    partition: KBPartition
    raw_content: str
    metadata: dict = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return xxhash.xxh64(self.raw_content.encode()).hexdigest()


@dataclass
class Chunk:
    chunk_id: str
    doc_fingerprint: str
    content: str
    source: SourceType
    content_type: ContentType
    partition: KBPartition
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None


@dataclass
class IngestionResult:
    docs_fetched: int = 0
    docs_skipped_duplicate: int = 0
    chunks_created: int = 0
    chunks_embedded: int = 0
    chunks_upserted: int = 0
    errors: list[str] = field(default_factory=list)

    def summarise(self) -> str:
        return (
            f"Fetched={self.docs_fetched} "
            f"Skipped={self.docs_skipped_duplicate} "
            f"Chunks: created={self.chunks_created} "
            f"embedded={self.chunks_embedded} "
            f"upserted={self.chunks_upserted} "
            f"Errors={len(self.errors)}"
        )
