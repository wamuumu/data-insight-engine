import logging
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser
from ingestion.parsers.xlsx import XLSXParser
from ingestion.parsers.parquet import ParquetParser

logger = logging.getLogger(__name__)

PARSER_REGISTRY: list[type[BaseParser]] = [
    XLSXParser,
    ParquetParser,
]

def get_parser(file: BaseFile) -> BaseParser | None:
    """
    Factory function to get the appropriate parser for a given file.
    """
    for parser_cls in PARSER_REGISTRY:
        instance = parser_cls()
        if instance.can_handle(file):
            return instance

    logger.warning(f"No parser available for file: {file.path}")
    return None