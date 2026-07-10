from typing import Iterator

import pandas as pd

from common.logging import get_logger
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, HistoryLogRecord
from ingestion.processing.timestamp_cleaner import clean_timestamps
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

    def parse(self, file: BaseFile) -> Iterator[HistoryLogRecord]:
        """
        Parse the XLSX file and yield HistoryLogRecord instances. Cleans timestamps and builds firmware version lookup.
        """
        logger.debug(
            "Parsing XLSX file",
            path=str(file.path), 
            size_mb=round(file.size / 1e6, 2)
        )

        df = pd.read_excel(
            file.path, sheet_name=0, header=0, names=_COLUMNS, engine="openpyxl"
        )

        df = df.dropna(how="all")  # Drop rows where all elements are NaN

        if df.empty:
            raise ValueError("XLSX file has no data rows.")

        logger.debug(
            "XLSX file opened successfully",
            path=str(file.path),
            num_rows=len(df),
            columns=list(df.columns),
        )

        cleaned_records = clean_timestamps(df)

        logger.info(
            "Timestamps cleaning completed",
            num_original_records=len(df),
            num_cleaned_records=len(cleaned_records),
            diff=len(cleaned_records) - len(df),
        )

        firmware_lookup = build_firmware_lookup(cleaned_records)
        firmware_versions = [firmware_lookup(idx) for idx in range(len(cleaned_records))]

        if any(fv is None for fv in firmware_versions):
            raise ValueError("Firmware version lookup failed for some records.")
        
        logger.info("Firmware version lookup completed", num_lookups=len(firmware_versions))

        for idx, row in enumerate(cleaned_records.itertuples(index=False)):
            yield HistoryLogRecord(
                source_file=str(file.path),
                data={
                    "datetime": row.datetime,
                    "event_id": row.event_id,
                    "value": row.value,
                    "tssc": row.tssc,
                    "rollover": row.rollover,
                    "firmware_version": firmware_versions[idx],
                }
            )
