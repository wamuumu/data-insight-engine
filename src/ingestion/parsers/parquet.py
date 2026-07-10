import pandas as pd

from common.constants import PARQUET_DROP_COLUMNS
from common.logging import get_logger
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, SpecialEventRecord
from ingestion.processing.event_statistics import compute_event_statistics

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

    def can_handle(self, file: BaseFile) -> bool:
        """
        Check if the file is a Parquet file based on its extension.
        """
        return file.suffix == ".parquet"

    def parse(self, file: BaseFile) -> SpecialEventRecord:
        """
        Parse the Parquet file and return computed event statistics.
        """
        logger.debug(
            "Parsing Parquet file",
            path=str(file.path),
            size_mb=round(file.size / 1e6, 2),
        )

        df = pd.read_parquet(file.path, engine="pyarrow")

        if df.empty:
            raise ValueError("Parquet file has no data rows.")

        logger.debug(
            "Parquet file opened successfully",
            path=str(file.path),
            num_rows=len(df),
            columns=list(df.columns),
        )

        df = df.drop(columns=PARQUET_DROP_COLUMNS, errors="ignore").rename(
            columns=_HEADER_MAPPING
        )[list(_HEADER_MAPPING.values())]

        statistics = compute_event_statistics(df)

        logger.debug(
            "Special event statistics computed", num_statistics=len(statistics)
        )

        return SpecialEventRecord(source_file=file.path, data=statistics)
