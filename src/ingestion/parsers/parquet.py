from typing import Generator

import pyarrow.parquet as pq

from common.constants import PARQUET_DROP_COLUMNS
from common.logging import get_logger
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, SpecialEventRecord

logger = get_logger(__name__)

_HEADER_MAPPING = {
    "ACC_X": "acc_x",
    "ACC_Y": "acc_y",
    "ACC_Z": "acc_z",
    "GYRO_X": "gyro_x",
    "GYRO_Y": "gyro_y",
    "GYRO_Z": "gyro_z",
    "HDOP": "hdop",
    "lat": "lat",
    "long": "lon",
    "speed_km_h": "speed",
    "Hour": "hour",
    "Min": "min",
    "Sec": "sec",
    "Cent": "cent",
    "Alarms": "alarms",
    "algoIgnited": "algo_ignited",
    "algoEnabled": "algo_enabled",
    "GPS_Fix": "gps_fix"
}

class ParquetParser(BaseParser):
    """
    Parser for Parquet Special Event files.
    """

    def __init__(self, batch_size: int = 500):
        self.batch_size = batch_size

    def can_handle(self, file: BaseFile) -> bool:
        """
        Check if the file is a Parquet file based on its extension.
        """
        return file.suffix == ".parquet"
    
    def parse(self, file: BaseFile) -> Generator[SpecialEventRecord, None, None]:
        """
        Parse the Parquet file and yield records as dictionaries.
        """
        logger.info("Parsing Parquet file", path=str(file.path), size_mb=round(file.size / 1e6, 2))
        
        try:
            parquet_file = pq.ParquetFile(file.path)
        except Exception as e:
            logger.error("Failed to read Parquet file", path=str(file.path), error=str(e))
            raise

        logger.debug(
            "Parquet file metadata",
            path=str(file.path),
            num_row_groups=parquet_file.num_row_groups,
            num_rows=parquet_file.metadata.num_rows,
            columns=[col.name for col in parquet_file.schema_arrow],
        )

        for batch in parquet_file.iter_batches(batch_size=self.batch_size):
            df = batch.to_pydict()

            # Drop unnecessary columns
            for col in PARQUET_DROP_COLUMNS:
                df.pop(col, None)
            
            num_rows = len(next(iter(df.values()))) if df else 0

            for i in range(num_rows):
                record = {col: df[col][i] for col in df}
                record_data: dict = {}

                # Map known fields to the expected data structure
                for key, value in record.items():
                    mapped_key = _HEADER_MAPPING.get(key)
                    if mapped_key:
                        record_data[mapped_key] = value

                yield SpecialEventRecord(source_file=file.path, data=record_data)
            

