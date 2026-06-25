from typing import Generator

import pandas as pd

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
    "GPS_Fix": "gps_fix",
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
        logger.info(
            "Parsing Parquet file",
            path=str(file.path),
            size_mb=round(file.size / 1e6, 2),
        )

        try:
            df = pd.read_parquet(file.path, engine="pyarrow")
        except Exception as e:
            logger.error(
                "Failed to read Parquet file", path=str(file.path), error=str(e)
            )
            raise

        logger.debug(
            "Parquet file metadata",
            path=str(file.path),
            num_rows=len(df),
            columns=list(df.columns)
        )

        pf = (
            df.drop(columns=PARQUET_DROP_COLUMNS, errors="ignore")
            .rename(columns=_HEADER_MAPPING)
            [list(_HEADER_MAPPING.values())]
        )

        for start in range(0, len(pf), self.batch_size):
            batch_df = pf.iloc[start:start + self.batch_size]
            for row in batch_df.itertuples(index=False):
                yield SpecialEventRecord(source_file=file.path, data=row._asdict())
