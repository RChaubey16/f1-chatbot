"""Pipeline orchestrator — ties extractors, chunker, embedder, loader together."""

from __future__ import annotations

import argparse
import asyncio

from tqdm import tqdm

from ingestion.core.logging import get_logger, setup_logging
from ingestion.core.models import IngestionResult
from ingestion.embedders.ollama import OllamaEmbedder
from ingestion.extractors.jolpica import JolpicaExtractor
from ingestion.extractors.wikipedia import WikipediaExtractor
from ingestion.loaders.pgvector import PgVectorLoader
from ingestion.transformers.chunker import Chunker

log = get_logger(__name__)


async def run_static(
    start_year: int = 1950,
    end_year: int = 2024,
) -> IngestionResult:
    chunker = Chunker()
    embedder = OllamaEmbedder()
    loader = PgVectorLoader()

    total = IngestionResult()
    extractors = [
        JolpicaExtractor(start_year=start_year, end_year=end_year),
        WikipediaExtractor(),
    ]

    progress = tqdm(desc="Ingesting", unit="doc")

    try:
        for extractor in extractors:
            name = type(extractor).__name__
            log.info("pipeline.source.start", source=name)

            async for raw_doc in extractor.extract():
                # Check for duplicate before doing expensive work
                if await loader.doc_exists(raw_doc.fingerprint):
                    total.docs_skipped_duplicate += 1
                    progress.update(1)
                    continue

                chunks = chunker.chunk(raw_doc)
                total.chunks_created += len(chunks)

                chunks = await embedder.embed_batch(chunks)
                total.chunks_embedded += sum(1 for c in chunks if c.embedding)

                result = await loader.upsert(raw_doc, chunks)
                total.docs_fetched += result.docs_fetched
                total.chunks_upserted += result.chunks_upserted
                total.errors.extend(result.errors)

                progress.update(1)

            log.info("pipeline.source.done", source=name, summary=total.summarise())

        # Rebuild IVFFlat index after full ingestion
        await loader.rebuild_index()

        chunk_count = await loader.get_chunk_count()
        log.info("pipeline.done", total_chunks=chunk_count, summary=total.summarise())

    finally:
        progress.close()
        await embedder.close()
        await loader.close()

    return total


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="F1 Knowledge Base Ingestion")
    parser.add_argument(
        "--phase",
        choices=["static", "live", "all"],
        default="static",
        help="Which phase to run (default: static)",
    )
    parser.add_argument("--start-year", type=int, default=1950)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()

    if args.phase in ("static", "all"):
        result = asyncio.run(run_static(args.start_year, args.end_year))
        print(f"\nStatic ingestion complete: {result.summarise()}")

    if args.phase == "live":
        print("Live ingestion not yet implemented (Phase 2)")


if __name__ == "__main__":
    main()
