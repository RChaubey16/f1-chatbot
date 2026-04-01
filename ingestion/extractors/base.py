"""Abstract base class for all data extractors."""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator

from ingestion.core.models import RawDocument


class BaseExtractor(abc.ABC):
    @abc.abstractmethod
    async def extract(self) -> AsyncIterator[RawDocument]:
        """Yield documents one at a time for streaming into the pipeline."""
        ...  # pragma: no cover
        # Make this an async generator so subclasses can use `yield`.
        if False:  # noqa: SIM108
            yield  # type: ignore[misc]

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Return True if the upstream source is reachable."""
        ...
