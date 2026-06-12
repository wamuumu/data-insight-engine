import logging

from config import load_settings
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser
from ingestion.parsers.parquet import ParquetParser
from ingestion.parsers.xlsx import XLSXParser

logger = logging.getLogger(__name__)

_settings = load_settings()

_PARSER_FACTORIES: list = [
    lambda: XLSXParser(),
    lambda: ParquetParser(batch_size=_settings.parquet_batch_size),
]

def get_parser(file: BaseFile) -> BaseParser | None:
    """
    Factory function that returns the first appropriate parser for a given file, or None.
    """
    for factory in _PARSER_FACTORIES:
        instance: BaseParser = factory()
        if instance.can_handle(file):
            return instance
    logger.warning("No suitable parser found for file", extra={"path": file.path})
    return None