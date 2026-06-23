import bisect
from typing import Callable

from common.constants import (
    SWITCH_ON_EVENT_ID,
    SWITCH_OFF_EVENT_ID,
    UNDEFINED_FIRMWARE_VERSION,
)
from common.logging import get_logger
from ingestion.crawler.base import BaseFile

logger = get_logger(__name__)


def _build_firmware_index(
    file: BaseFile, header: list[str], rows: list[tuple]
) -> list[tuple[int, int, int]]:
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


def _partition_firmware_regions(
    file: BaseFile, switch_events: list[tuple[int, int, int]], total_rows: int
) -> list[tuple[int, int, int]]:
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
                close_segment(row_index, firmware_value)
                pending_start = row_index + 1
                last_type = SWITCH_OFF_EVENT_ID
                last_firmware = firmware_value
            else:
                pending_start = row_index
                last_type = SWITCH_ON_EVENT_ID
                last_firmware = firmware_value
        elif last_type == SWITCH_ON_EVENT_ID:
            if event_id == SWITCH_OFF_EVENT_ID:
                close_segment(row_index, last_firmware)
                pending_start = row_index + 1
                last_type = SWITCH_OFF_EVENT_ID
                last_firmware = firmware_value
            else:
                if row_index - 1 >= pending_start:
                    segments.append((pending_start, row_index - 1, last_firmware))
                pending_start = row_index
                last_type = SWITCH_ON_EVENT_ID
                last_firmware = firmware_value
        elif last_type == SWITCH_OFF_EVENT_ID:
            if event_id == SWITCH_ON_EVENT_ID:
                pending_start = row_index
                last_type = SWITCH_ON_EVENT_ID
                last_firmware = firmware_value
            else:
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

    firmware_to_use = (
        last_firmware if last_firmware is not None else UNDEFINED_FIRMWARE_VERSION
    )
    if total_rows > 0 and pending_start <= total_rows - 1:
        close_segment(total_rows - 1, firmware_to_use)

    return segments


def _create_firmware_resolver(
    segments: list[tuple[int, int, int]]
) -> Callable[[int], int | None]:
    starts = [s for s, _, _ in segments]
    ends = [e for _, e, _ in segments]
    firmwares = [f for _, _, f in segments]

    def lookup(row_index: int) -> int:
        pos = bisect.bisect_right(starts, row_index) - 1
        if pos >= 0 and row_index <= ends[pos]:
            return firmwares[pos]
        return UNDEFINED_FIRMWARE_VERSION

    return lookup

def build_firmware_lookup(
    file: BaseFile, 
    header: list[str], 
    rows: list[tuple],
) -> Callable[[int], int | None]:
    switch_events = _build_firmware_index(file, header, rows)
    segments = _partition_firmware_regions(file, switch_events, len(rows))
    firmware_lookup = _create_firmware_resolver(segments)
    return firmware_lookup
