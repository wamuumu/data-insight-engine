import logging
import bisect
from typing import Generator, Callable

import openpyxl
from openpyxl import Workbook

from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, HistoryLogRecord
from common.utils import extract_serial_number
from common.constants import SWITCH_ON_EVENT_ID, SWITCH_OFF_EVENT_ID, UNDEFINED_FIRMWARE_VERSION

logger = logging.getLogger(__name__)

class XLSXParser(BaseParser):
    """
    Parser for XLSX History Log files.
    """

    # TODO: Create a local postgres database and insert all the records there (use SQLAlchemy and migrations)

    def can_handle(self, file: BaseFile) -> bool:
        """
        Check if the file is an XLSX file based on its extension.
        """
        return file.suffix == ".xlsx"
    
    def parse(self, file: BaseFile) -> Generator[HistoryLogRecord, None, None]:
        """
        Parse the XLSX file and yield records as dictionaries.
        """
        logger.info(f"Parsing XLSX file: {file.path} (size: {file.size / 1e6:.2f} MB)")
        
        try:
            workbook = openpyxl.load_workbook(file.path, read_only=True, data_only=True)
        except Exception as e:
            logger.error(f"[Indexing] Failed to open XLSX file: {file.path}, error: {e}")
            raise

        logger.debug(f"Opened workbook for parsing: {file.path}, sheets: {workbook.sheetnames}")

        if not workbook.sheetnames or len(workbook.sheetnames) != 1:
            logger.warning(f"Expected exactly one sheet in XLSX file: {file.path}, found {len(workbook.sheetnames)}. Proceeding with parsing but results may be unexpected.")
        
        # Build firmware index
        try:
            switch_events, total_rows = self._build_firmware_index(file, workbook)
        finally:
            workbook.close()  # Close after building index to free resources

        # Build segments and fast lookup from the index
        segments = self._build_firmware_segments(file, switch_events, total_rows)
        firmware_lookup = self._make_firmware_lookup(segments)

        try:
            workbook = openpyxl.load_workbook(file.path, read_only=True, data_only=True)
        except Exception as e:
            logger.error(f"[Analysis] Failed to open XLSX file: {file.path}, error: {e}")
            raise
            
        logger.debug(f"Reopened workbook for parsing: {file.path}, sheets: {workbook.sheetnames}")
        
        try:
            sn = extract_serial_number(file.path)
            abs_row_index = 0

            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                rows = sheet.iter_rows(values_only=True)

                try:
                    header = [str(h).strip() if h is not None else f"column_{i}" for i, h in enumerate(next(rows))]
                except StopIteration:
                    logger.warning(f"Sheet {sheet_name} in file {file.path} is empty on second read, skipping.")
                    continue
                
                for row in rows:
                    if all(cell is None for cell in row):
                        continue  # Skip if sheet is empty

                    record_data = dict(zip(header, row))
                    record_data["Serial Number"] = sn
                    record_data["Firmware Version"] = firmware_lookup(abs_row_index)

                    yield HistoryLogRecord(source_file=file.path, data=record_data)

                    abs_row_index += 1
        finally:
            workbook.close()
    
    def _build_firmware_index(self, file: BaseFile, workbook: Workbook) -> tuple[list[tuple[int, int, int]], int]:
        """
        Returns a list of (absolute row index, event id, firmware value) for ON/OFF events only.
        """
        switch_events: list[tuple[int, int, int]] = []
        abs_row_index = 0

        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            rows = sheet.iter_rows(values_only=True)

            # Read header, assuming the first row contains column names
            try:
                header = [str(h).strip() if h is not None else f"column_{i}" for i, h in enumerate(next(rows))]
            except StopIteration:
                logger.warning(f"Sheet {sheet_name} in file {file.path} is empty, skipping.")
                continue

            event_id_col = header.index("Event ID") if "Event ID" in header else None
            firmware_col = header.index("Value") if "Value" in header else None

            if event_id_col is None or firmware_col is None:
                logger.warning(f"Sheet {sheet_name} in file {file.path} is missing 'Event ID' or 'Value' columns, skipping firmware index building.")
                continue

            for row in rows:
                if all(cell is None for cell in row):
                    continue # Skip if sheet is empty
                
                try:
                    event_id = int(row[event_id_col]) 
                    firmware_value = int(row[firmware_col])
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid data in row {abs_row_index} of sheet {sheet_name} in file {file.path}: {e}, skipping row.")
                    abs_row_index += 1
                    continue

                if event_id in (SWITCH_ON_EVENT_ID, SWITCH_OFF_EVENT_ID):
                    switch_events.append((abs_row_index, event_id, firmware_value))
                
                abs_row_index += 1
        
        return switch_events, abs_row_index
    
    def _build_firmware_segments(self, file: BaseFile, switch_events: list[tuple[int, int, int]], total_rows: int) -> list[tuple[int, int, int]]:
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
                logger.warning(f"Unexpected last_type {last_type} encountered while building firmware segments for file {file.path}, row {row_index}.")
        
        # Close any trailing open segment
        firmware_to_use = last_firmware if last_firmware is not None else UNDEFINED_FIRMWARE_VERSION
        if pending_start <= total_rows - 1:
            close_segment(total_rows - 1, firmware_to_use)
        
        return segments

    def _make_firmware_lookup(self, segments: list[tuple[int, int, int]]) -> Callable[[int], int | None]:
        """
        Builds a lookup dictionary mapping absolute row indices to firmware values based on the segments.
        """
        starts = [s for s, _, _ in segments]
        ends = [e for _, e, _ in segments]
        firmware_values = [f for _, _, f in segments]

        def lookup(row_index: int) -> int | None:
            # Find the rightmost segment whose start <= row_index
            pos = bisect.bisect_right(starts, row_index) - 1
            if pos >= 0 and row_index <= ends[pos]:
                return firmware_values[pos]
            return None

        return lookup