from typing import Iterator

import pandas as pd

from common.logging import get_logger
from common.exceptions import FirmwareLookupError, ParsingError, TimestampCleaningError
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

        try:
            df = pd.read_excel(
                file.path, 
                sheet_name=0, 
                header=0, 
                names=_COLUMNS, 
                engine="openpyxl"
            )
        except Exception as e:
            raise ParsingError(f"Failed to read XLSX file: {file.path}") from e

        df = df.dropna(how="all")  # Drop rows where all elements are NaN

        if df.empty:
            raise ParsingError(f"XLSX file has no data rows: {file.path}")

        logger.debug(
            "XLSX file opened successfully",
            path=str(file.path),
            num_rows=len(df),
            columns=list(df.columns),
        )

        try:
            cleaned_records = clean_timestamps(df)
        except TimestampCleaningError:
            raise
        except Exception as e:
            raise TimestampCleaningError(f"Failed to clean timestamps in XLSX file: {file.path}") from e

        logger.info(
            "Timestamps cleaning completed",
            num_original_records=len(df),
            num_cleaned_records=len(cleaned_records),
            diff=len(cleaned_records) - len(df),
        )
        
        try:
            firmware_lookup = build_firmware_lookup(cleaned_records)
            firmware_versions = [firmware_lookup(idx) for idx in range(len(cleaned_records))]
        except FirmwareLookupError:
            raise
        except Exception as e:
            raise FirmwareLookupError(f"Failed to lookup firmware versions in XLSX file: {file.path}") from e
        
        if any(fv is None for fv in firmware_versions):
            raise FirmwareLookupError(f"Firmware version lookup failed for some records in XLSX file: {file.path}")
        
        logger.info("Firmware version lookup completed", num_lookups=len(firmware_versions))

        for idx, row in enumerate(cleaned_records.itertuples(index=False)):
            yield HistoryLogRecord(
                source_file=str(file.path),
                data={
                    "firmware_version": firmware_versions[idx],
                    "event_ts": row.datetime,
                    "event_id": row.event_id,
                    "value": row.value,
                    "tssc": row.tssc,
                }
            )
