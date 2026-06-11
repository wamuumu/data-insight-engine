import re
import logging
import bisect
from typing import Generator, Callable

import openpyxl
from openpyxl import Workbook

from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, ParsedRecord

logger = logging.getLogger(__name__)

class XLSXParser(BaseParser):
    """
    Parser for XLSX files.
    """

    # TODO: Add firmware label to each row (search between ON and OFF)
    # TODO: Create a local postgres database and insert all the records there (use SQLAlchemy and migrations)

    CHUNK_SIZE = 100  # Number of rows to read at a time to manage memory usage

    def can_handle(self, file: BaseFile) -> bool:
        """
        Check if the file is an XLSX file based on its extension.
        """
        return file.suffix == ".xlsx"
    
    def parse(self, file: BaseFile) -> Generator[ParsedRecord, None, None]:
        """
        Parse the XLSX file and yield records as dictionaries.
        """
        logger.info(f"Parsing XLSX file: {file.path} (size: {file.size / 1e6:.2f} MB)")

        # Extract SN from filename using regex (e.g., "B" followed by 8 hexadecimal characters)
        sn_match = re.search(r"(B[0-9A-F]{8})", str(file.path))
        sn = sn_match.group() if sn_match else None
        
        try:
            workbook = openpyxl.load_workbook(file.path, read_only=True, data_only=True)
        except Exception as e:
            logger.error(f"Failed to open XLSX file: {file.path}, error: {e}")
            raise
            
        # Count total data rows and collect switch events for firmware indexing
        total_rows = 0
        switch_events = []
        SWITCH_ON = 1
        SWITCH_OFF = 2
        
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

            for row in rows:
                if all(cell is None for cell in row):
                    continue  # Skip if sheet is empty
                
                if event_id_col is not None and firmware_col is not None:
                    try:
                        event_id = int(row[event_id_col]) 
                        firmware_value = int(row[firmware_col])
                        if event_id in (SWITCH_ON, SWITCH_OFF):
                            switch_events.append((total_rows, event_id, firmware_value))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid data in row {total_rows} of sheet {sheet_name} in file {file.path}: {e}, skipping row.")
                
                total_rows += 1
        
        workbook.close()

        # Build segments and fast lookup from the index
        segments = self._build_firmware_segments(file, switch_events, total_rows)
        firmware_lookup = self._make_firmware_lookup(segments)

        try:
            workbook = openpyxl.load_workbook(file.path, read_only=True, data_only=True)
        except Exception as e:
            logger.error(f"Failed to reopen XLSX file for parsing: {file.path}, error: {e}")
            raise

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

                yield ParsedRecord(source_file=file.path, record_type="history_log", data=record_data)

                abs_row_index += 1
        
        workbook.close()
    
    def _build_firmware_index(self, file: BaseFile, workbook: Workbook) -> list[tuple[int, int, int]]:
        """
        Returns a list of (absolute row index, event id, firmware value) for ON/OFF events only.
        """
        SWITCH_ON = 1
        SWITCH_OFF = 2

        switch_events = []
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

            if not event_id_col or not firmware_col:
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

                if event_id in (SWITCH_ON, SWITCH_OFF):
                    switch_events.append((abs_row_index, event_id, firmware_value))
                
                abs_row_index += 1
        
        return switch_events
    
    def _build_firmware_segments(self, file: BaseFile, switch_events: list[tuple[int, int, int]], total_rows: int) -> list[tuple[int, int, int]]:
        """
        Returns a list of (start_row_index, end_row_index, firmware_value) segments based on the switch events.
        """
        SWITCH_ON = 1
        SWITCH_OFF = 2

        segments = []
        pending_start = 0
        last_type = None
        last_firmware = None

        def close_segment(end_idx: int, firmware_value: int):
            if end_idx >= pending_start:
                segments.append((pending_start, end_idx, firmware_value))

        for row_index, event_id, firmware_value in switch_events:
            if last_type is None:
                if event_id == SWITCH_OFF:
                    # Orphan OFF event (likely at the start): everything before up to this OFF
                    close_segment(row_index, firmware_value)
                    pending_start = row_index + 1
                    last_type = SWITCH_OFF
                    last_firmware = firmware_value
                else:
                    # Records before the first ON event get the firmware of the first ON event
                    pending_start = row_index
                    last_type = SWITCH_ON
                    last_firmware = firmware_value
            elif last_type == SWITCH_ON:
                if event_id == SWITCH_OFF:
                    # Normal ON->OFF transition: close segment and start new one after OFF
                    close_segment(row_index, last_firmware)
                    pending_start = row_index + 1
                    last_type = SWITCH_OFF
                    last_firmware = firmware_value
                else:
                    # [Anomaly] Consecutive ON->ON events: close with first firmware, reopen with second
                    if row_index - 1 >= pending_start:
                        segments.append((pending_start, row_index - 1, last_firmware))
                    pending_start = row_index
                    last_firmware = firmware_value
            elif last_type == SWITCH_OFF:
                if event_id == SWITCH_ON:
                    # Normal OFF->ON transition
                    pending_start = row_index
                    last_type = SWITCH_ON
                    last_firmware = firmware_value
                else:
                    # [Anomaly] Consecutive OFF->OFF events: close with second firmware, advance
                    if row_index >= pending_start:
                        segments.append((pending_start, row_index, firmware_value))
                    pending_start = row_index + 1
                    last_firmware = firmware_value
            else:
                logger.warning(f"Unexpected last_type {last_type} encountered while building firmware segments for file {file.path}, row {row_index}.")
        
        # Close any trailing open segment
        if pending_start <= total_rows - 1:
            close_segment(total_rows - 1, last_firmware if last_firmware else 0)
        
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