from common.exceptions import PipelineError
from common.logging import get_logger
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser
from ingestion.parsers.parquet import ParquetParser
from ingestion.parsers.xlsx import XLSXParser

logger = get_logger(__name__)

_PARSER_FACTORIES: list = [
    lambda: XLSXParser(),
    lambda: ParquetParser(),
]


def get_parser(file: BaseFile) -> BaseParser:
    """
    Factory function that returns the first appropriate parser for a given file, or None.
    """
    for factory in _PARSER_FACTORIES:
        instance: BaseParser = factory()
        if instance.can_handle(file):
            return instance
    raise PipelineError(f"No suitable parser found for file: {file.path}")
