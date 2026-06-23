from typing import Generator

import openpyxl
from openpyxl import Workbook

from common.logging import get_logger
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, HistoryLogRecord
from ingestion.processing.datetime_cleaner import clean_timestamps
from ingestion.processing.firmware_lookup import build_firmware_lookup

logger = get_logger(__name__)


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
            workbook = openpyxl.load_workbook(file.path, read_only=True, data_only=True)
        except Exception as e:
            logger.error("Failed to open XLSX file", path=str(file.path), error=str(e))
            raise

        logger.debug(
            "XLSX file opened successfully",
            path=str(file.path),
            sheets=workbook.sheetnames,
        )

        if len(workbook.sheetnames) != 1:
            logger.warning(
                "Expected exactly one sheet in XLSX file, found %d.",
                len(workbook.sheetnames),
                path=str(file.path),
                found_sheets=len(workbook.sheetnames),
            )

        try:
            yield from self._parse_workbook(file, workbook)
        finally:
            workbook.close()

    def _parse_workbook(
        self, file: BaseFile, workbook: Workbook
    ) -> Generator[HistoryLogRecord, None, None]:
        """
        Parse the workbook and yield HistoryLogRecord instances. This method assumes the workbook is already open.
        """
        abs_row_index = 0

        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            rows_iter = sheet.iter_rows(values_only=True)

            # Read header, assuming the first row contains column names
            try:
                header = [
                    str(h).strip() if h is not None else f"column_{i}"
                    for i, h in enumerate(next(rows_iter))
                ]
            except StopIteration:
                logger.warning(
                    "Sheet %s in file %s is empty, skipping.", sheet_name, file.path
                )
                continue

            all_rows = [
                row for row in rows_iter if not all(cell is None for cell in row)
            ]  # Skip empty rows

            # Build firmware index over the sheet's rows
            firmware_lookup = build_firmware_lookup(file, header, all_rows)

            # create a mapping of header names to their column indices for easy access
            header_mapping = {col: i for i, col in enumerate(header)}

            event_id_col = header_mapping.get("Event ID")
            value_col = header_mapping.get("Value")
            date_col = header_mapping.get("Date")
            time_col = header_mapping.get("Time")

            raw_records: list[dict] = []
            for _, row in enumerate(all_rows):
                record_data: dict = {}

                # ── Required fields ───────────────────────────────────────
                record_data["event_date"] = row[date_col]
                record_data["event_time"] = row[time_col]
                record_data["event_id"] = row[event_id_col]
                record_data["value"] = row[value_col]

                # ── Derived fields ────────────────────────────────────────
                record_data["firmware_version"] = firmware_lookup(abs_row_index)

                raw_records.append(record_data)
                abs_row_index += 1
            
            cleaned_records = clean_timestamps(raw_records)
            logger.info(
                "RTC timestamps cleaning completed",
                raw_records_count=len(raw_records),
                cleaned_records_count=len(cleaned_records),
                diff=len(cleaned_records) - len(raw_records)
            )

            # for i, record in enumerate(cleaned_records):
            #     logger.debug(f"{i}", **record)

            for record_data in cleaned_records:
                yield HistoryLogRecord(source_file=str(file.path), data=record_data)


