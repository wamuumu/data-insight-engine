from typing import Generator

import pandas as pd

from common.logging import get_logger
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, HistoryLogRecord
from ingestion.processing.datetime_cleaner import clean_timestamps
from ingestion.processing.firmware_lookup import build_firmware_lookup

logger = get_logger(__name__)

_COLUMNS = ["counter", "date", "time", "event_id", "description", "value"]


class XLSXParser(BaseParser):
    """
    Parser for XLSX History Log files.
    """

    def can_handle(self, file: BaseFile) -> bool:
        """
        Check if the file is an XLSX file based on its extension.
        """
        return file.suffix == ".xlsx"

    def parse(self, file: BaseFile) -> Generator[HistoryLogRecord, None, None]:
        """
        Parse the XLSX file and yield records as dictionaries.
        """
        logger.info(
            "Parsing XLSX file", path=str(file.path), size_mb=round(file.size / 1e6, 2)
        )

        try:
            df = pd.read_excel(file.path, sheet_name=0, header=0, names=_COLUMNS, engine="openpyxl")
        except Exception as e:
            logger.error("Failed to read XLSX file into DataFrame", path=str(file.path), error=str(e))
            raise

        df = df.dropna(how="all")  # Drop rows where all elements are NaN

        if df.empty:
            logger.warning("XLSX file has no data rows", path=str(file.path))
            return

        logger.debug(
            "XLSX file opened successfully",
            path=str(file.path),
            num_rows=len(df),
            columns=list(df.columns)
        )

        firmware_lookup = build_firmware_lookup(df)

        raw_records = [
            {
                "event_date": row.date,
                "event_time": row.time,
                "event_id": row.event_id,
                "value": row.value,
                "firmware_version": firmware_lookup(idx),
            }
            for idx, row in enumerate(df.itertuples(index=False))
        ]

        cleaned_records = clean_timestamps(raw_records)

        logger.info(
            "RTC timestamps cleaning completed",
            raw_records_count=len(raw_records),
            cleaned_records_count=len(cleaned_records),
            diff=len(cleaned_records) - len(raw_records)
        )

        for record_data in cleaned_records:
            yield HistoryLogRecord(source_file=str(file.path), data=record_data)