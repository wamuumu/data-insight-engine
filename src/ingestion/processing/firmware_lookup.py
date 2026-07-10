import bisect
from typing import Callable

import pandas as pd

from common.constants import EventID
from common.logging import get_logger

logger = get_logger(__name__)


_BOUNDARY_EVENT_IDS = {EventID.SWITCH_ON, EventID.SWITCH_OFF}


def _build_firmware_index(df: pd.DataFrame) -> list[tuple[int, int, int]]:
    """
    Build a list of switch events from the DataFrame, where each event is represented as a tuple of (row_index, event_id, firmware_value).
    
    Args:
        df (pd.DataFrame): The DataFrame containing event data.
    
    Returns:
        list[tuple[int, int, int]]: A list of tuples where each tuple contains (row_index, event_id, firmware_value) for switch events.
    """
    switch_events: list[tuple[int, int, int]] = []

    if "event_id" not in df.columns or "value" not in df.columns:
        logger.warning(
            "DataFrame does not contain required columns for firmware lookup.",
            columns=list(df.columns),
        )
        return switch_events

    for abs_row_index, row in enumerate(df.itertuples(index=False)):
        try:
            event_id = int(row.event_id)
        except (ValueError, TypeError):
            continue

        if event_id not in _BOUNDARY_EVENT_IDS:
            continue

        try:
            firmware_value = int(row.value)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid firmware value encountered at boundary event.",
                row_index=abs_row_index,
                event_id=event_id,
                value=row.value,
            )
            continue

        switch_events.append((abs_row_index, event_id, firmware_value))

    return switch_events


def _partition_firmware_regions(
    switch_events: list[tuple[int, int, int]], 
    total_rows: int
) -> list[tuple[int, int, int | None]]:
    """
    Partition the DataFrame into segments based on switch events and their corresponding firmware versions.

    Args:
        switch_events (list[tuple[int, int, int]]): A list of tuples where each tuple contains (row_index, event_id, firmware_value).
        total_rows (int): Total number of rows in the DataFrame.
    
    Returns:
        list[tuple[int, int, int | None]]: A list of segments where each segment is represented as a tuple (start_index, end_index, firmware_version).
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
            if event_id == EventID.SWITCH_OFF:
                close_segment(row_index, firmware_value)
                pending_start = row_index + 1
                last_type = EventID.SWITCH_OFF
                last_firmware = firmware_value
            else:
                pending_start = row_index
                last_type = EventID.SWITCH_ON
                last_firmware = firmware_value
        elif last_type == EventID.SWITCH_ON:
            if event_id == EventID.SWITCH_OFF:
                close_segment(row_index, last_firmware)
                pending_start = row_index + 1
                last_type = EventID.SWITCH_OFF
                last_firmware = firmware_value
            else:
                if row_index - 1 >= pending_start:
                    segments.append((pending_start, row_index - 1, last_firmware))
                pending_start = row_index
                last_type = EventID.SWITCH_ON
                last_firmware = firmware_value
        elif last_type == EventID.SWITCH_OFF:
            if event_id == EventID.SWITCH_ON:
                last_type = EventID.SWITCH_ON
                last_firmware = firmware_value
            else:
                if row_index >= pending_start:
                    segments.append((pending_start, row_index, firmware_value))
                pending_start = row_index + 1
                last_type = EventID.SWITCH_OFF
                last_firmware = firmware_value
        else:
            logger.warning(
                "Unexpected last_type encountered during firmware region partitioning.",
                last_type=last_type,
                row_index=row_index,
                event_id=event_id,
                firmware_value=firmware_value,
            )

    if total_rows > 0 and pending_start <= total_rows - 1:
        if last_type == EventID.SWITCH_OFF:
            logger.warning(
                "Final session has no SWITCH_ON event; carrying forward last known firmware version.", 
                last_firmware=last_firmware
            )
        close_segment(total_rows - 1, last_firmware)

    return segments


def _create_firmware_resolver(
    segments: list[tuple[int, int, int]],
) -> Callable[[int], int | None]:
    """
    Create a firmware resolver function based on the provided segments.

    Args:
        segments (list[tuple[int, int, int]]): A list of tuples where each tuple contains (start_index, end_index, firmware_version).
    
    Returns:
        Callable[[int], int | None]: A function that takes a row index and returns the corresponding firmware version, or None if not found.
    """
    starts = [s for s, _, _ in segments]
    ends = [e for _, e, _ in segments]
    firmwares = [f for _, _, f in segments]

    def lookup(row_index: int) -> int | None:
        if not starts:
            return None
        
        pos = bisect.bisect_right(starts, row_index) - 1
        if pos >= 0 and row_index <= ends[pos]:
            return firmwares[pos]

        return None

    return lookup


def build_firmware_lookup(df: pd.DataFrame) -> Callable[[int], int | None]:
    """
    Build a row-position-based firmware resolver for the given DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame containing event data.
    
    Returns:
        Callable[[int], int | None]: A function that takes a row index and returns the
        corresponding firmware version, or None if not found.
    """
    switch_events = _build_firmware_index(df)

    if not switch_events:
        logger.warning("No switch events found in DataFrame; firmware lookup will return None for all rows.")
        return lambda idx: None

    segments = _partition_firmware_regions(switch_events, len(df))
    firmware_lookup = _create_firmware_resolver(segments)
    return firmware_lookup
