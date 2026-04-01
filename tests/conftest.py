"""Shared test configuration."""

import pytest


@pytest.fixture(autouse=True)
def _setup_logging():
    from ingestion.core.logging import setup_logging
    setup_logging()
