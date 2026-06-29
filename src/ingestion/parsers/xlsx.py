import pandas as pd

from common.logging import get_logger
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, HistoryLogRecord, HistoryLogStream
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

    def parse(self, file: BaseFile) -> HistoryLogStream:
        """
        Parse the XLSX file and yield HistoryLogRecord instances. Cleans timestamps and builds firmware version lookup.
        """
        logger.debug(
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
            return HistoryLogStream(records=iter([]), rollover_detected=False, rollover_index=None)

        logger.debug(
            "XLSX file opened successfully",
            path=str(file.path),
            num_rows=len(df),
            columns=list(df.columns)
        )

        cleaned_records, rollover_index = clean_timestamps(df)

        logger.info(
            "RTC timestamps cleaning completed",
            num_cleaned_records=len(cleaned_records),
            diff=len(cleaned_records) - len(df)
        )

        firmware_lookup = build_firmware_lookup(cleaned_records)

        def record_generator():
            for idx, row in enumerate(cleaned_records.itertuples(index=False)):
                yield HistoryLogRecord(
                    source_file=str(file.path),
                    data={
                        "event_datetime": row.datetime,
                        "event_id": row.event_id,
                        "value": row.value,
                        "firmware_version": firmware_lookup(idx),
                    },
                    is_rollover=row.rollover
                )
            
        return HistoryLogStream(
            records=record_generator(),
            rollover_index=rollover_index
        )