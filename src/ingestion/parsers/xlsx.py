import bisect
from typing import Generator, Callable

import openpyxl
from openpyxl import Workbook

from common.constants import (
    SWITCH_ON_EVENT_ID,
    SWITCH_OFF_EVENT_ID,
    UNDEFINED_FIRMWARE_VERSION,
)
from common.logging import get_logger
from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, HistoryLogRecord
from ingestion.processing.datetime_cleaner import clean_timestamps

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
            total_rows = len(all_rows)

            # Build firmware index over the sheet's rows
            switch_events = self._build_firmware_index(file, header, all_rows)
            segments = self._build_firmware_segments(file, switch_events, total_rows)
            firmware_lookup = self._make_firmware_lookup(segments)

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

            for i, record in enumerate(cleaned_records):
                logger.debug(f"{i}", **record)

            for record_data in cleaned_records:
                yield HistoryLogRecord(source_file=str(file.path), data=record_data)

    def _build_firmware_index(
        self, file: BaseFile, header: list[str], rows: list[tuple]
    ) -> list[tuple[int, int, int]]:
        """
        Returns a list of (abs_row_index, event_id, firmware_value) for ON/OFF events only.
        """
        switch_events: list[tuple[int, int, int]] = []

        event_id_col = header.index("Event ID") if "Event ID" in header else None
        firmware_col = header.index("Value") if "Value" in header else None

        if event_id_col is None or firmware_col is None:
            logger.warning(
                "Sheet is missing 'Event ID' or 'Value' columns, skipping firmware index building.",
                path=str(file.path),
            )
            return switch_events

        for abs_row_index, row in enumerate(rows):
            try:
                event_id = int(row[event_id_col])
                firmware_value = int(row[firmware_col])
            except (ValueError, TypeError):
                continue

            if event_id in (SWITCH_ON_EVENT_ID, SWITCH_OFF_EVENT_ID):
                switch_events.append((abs_row_index, event_id, firmware_value))

        return switch_events

    def _build_firmware_segments(
        self, file: BaseFile, switch_events: list[tuple[int, int, int]], total_rows: int
    ) -> list[tuple[int, int, int]]:
        """
        Returns a list of (start_row_index, end_row_index, firmware_value) segments based on the switch events.
        """
        segments: list[tuple[int, int, int]] = []
        pending_start = 0
        last_type: int | None = None
        last_firmware: int | None = None

        def close_segment(end_idx: int, firmware_value: int):
            if end_idx >= pending_start:
                segments.append((pending_start, end_idx, firmware_value))

        for row_index, event_id, firmware_value in switch_events:
            if last_type is None:
                if event_id == SWITCH_OFF_EVENT_ID:
                    # Orphan OFF at start: everything up to and including this row inherits its firmware
                    close_segment(row_index, firmware_value)
                    pending_start = row_index + 1
                    last_type = SWITCH_OFF_EVENT_ID
                    last_firmware = firmware_value
                else:
                    # First event is an ON — rows before it inherit its firmware
                    pending_start = row_index
                    last_type = SWITCH_ON_EVENT_ID
                    last_firmware = firmware_value
            elif last_type == SWITCH_ON_EVENT_ID:
                if event_id == SWITCH_OFF_EVENT_ID:
                    # Normal ON → OFF transition
                    close_segment(row_index, last_firmware)
                    pending_start = row_index + 1
                    last_type = SWITCH_OFF_EVENT_ID
                    last_firmware = firmware_value
                else:
                    # Anomaly: ON → ON — close up to previous row with first firmware
                    if row_index - 1 >= pending_start:
                        segments.append((pending_start, row_index - 1, last_firmware))
                    pending_start = row_index
                    last_type = SWITCH_ON_EVENT_ID
                    last_firmware = firmware_value
            elif last_type == SWITCH_OFF_EVENT_ID:
                if event_id == SWITCH_ON_EVENT_ID:
                    # Normal OFF → ON transition
                    pending_start = row_index
                    last_type = SWITCH_ON_EVENT_ID
                    last_firmware = firmware_value
                else:
                    # Anomaly: OFF → OFF — treat the two segments as separate
                    if row_index >= pending_start:
                        segments.append((pending_start, row_index, firmware_value))
                    pending_start = row_index + 1
                    last_type = SWITCH_OFF_EVENT_ID
                    last_firmware = firmware_value
            else:
                logger.warning(
                    "Unexpected last event type %s while processing firmware segments.",
                    last_type,
                    path=str(file.path),
                    row_index=row_index,
                    event_id=event_id,
                )

        # Close any trailing open segment
        firmware_to_use = (
            last_firmware if last_firmware is not None else UNDEFINED_FIRMWARE_VERSION
        )
        if total_rows > 0 and pending_start <= total_rows - 1:
            close_segment(total_rows - 1, firmware_to_use)

        return segments

    def _make_firmware_lookup(
        self, segments: list[tuple[int, int, int]]
    ) -> Callable[[int], int | None]:
        """
        Builds a binary-search lookup over firmware segments. Returns UNDEFINED_FIRMWARE_VERSION for rows that don't fall into any segment.
        """
        starts = [s for s, _, _ in segments]
        ends = [e for _, e, _ in segments]
        firmwares = [f for _, _, f in segments]

        def lookup(row_index: int) -> int:
            # Find the rightmost segment whose start <= row_index
            pos = bisect.bisect_right(starts, row_index) - 1
            if pos >= 0 and row_index <= ends[pos]:
                return firmwares[pos]
            return UNDEFINED_FIRMWARE_VERSION

        return lookup
