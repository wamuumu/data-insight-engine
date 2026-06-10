import logging
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser
from ingestion.parsers.xlsx import XLSXParser
from ingestion.parsers.parquet import ParquetParser

logger = logging.getLogger(__name__)

PARSER_REGISTRY: list[BaseParser] = [
    XLSXParser(),
    ParquetParser(),
]

def get_parser(file: BaseFile) -> BaseParser | None:
    """
    Factory function to get the appropriate parser for a given file.
    """
    for parser in PARSER_REGISTRY:
        if parser.can_handle(file):
            return parser

    logger.warning(f"No parser available for file: {file.path}")
    return None