"""Registry for deterministic public-document parsers."""

from .plans import IngestionError, ingest_plans

__all__ = ["IngestionError", "ingest_plans"]
