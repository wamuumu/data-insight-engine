import logging
from typing import Generator

import pyarrow.parquet as pq

from config import load_settings
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, ParsedRecord

settings = load_settings()

logger = logging.getLogger(__name__)

class ParquetParser(BaseParser):
    """
    Parser for Parquet Special Event files.
    """

    def can_handle(self, file: BaseFile) -> bool:
        """
        Check if the file is a Parquet file based on its extension.
        """
        return file.suffix == ".parquet"
    
    def parse(self, file: BaseFile) -> Generator[ParsedRecord, None, None]:
        """
        Parse the Parquet file and yield records as dictionaries.
        """
        logger.info(f"Parsing Parquet file: {file.path} (size: {file.size / 1e6:.2f} MB)")
        
        try:
            parquet_file = pq.ParquetFile(file.path)
        except Exception as e:
            logger.error(f"Failed to open Parquet file: {file.path}, error: {e}")
            raise
        
        logger.debug(
            f"Schema: {parquet_file.schema}, "
            f"Number of row groups: {parquet_file.num_row_groups}, "
        )

        for batch in parquet_file.iter_batches(batch_size=settings.parquet_batch_size):
            df = batch.to_pydict()
            num_rows = len(next(iter(df.values())))

            for i in range(num_rows):
                record = {col: df[col][i] for col in df}
                yield ParsedRecord(source_file=file.path, record_type="raw_data", data=record)
            

