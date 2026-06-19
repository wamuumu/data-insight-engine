from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import NamedTuple

from common.constants import (
    RTC_SET_EVENT_ID,
    SWITCH_ON_EVENT_ID,
    SWITCH_OFF_EVENT_ID,
    SENTINEL_VALUE,
    EPOCH_YEAR
)
from common.logging import get_logger

logger = get_logger(__name__)


_DATE_FORMAT = "%d/%m/%Y"
_TIME_FORMAT = "%H:%M:%S.%f"
_EPOCH_DATE = "01/01/2000"

_TWIN_ZERO_OFFSET_MS = 1


class Window(NamedTuple):
    """A contiguous slice of row indices that share an invalid epoch."""

    start: int # inclusive
    end: int # inclusive
    rtc_anchor_idx: int # index of the RTC_SET event that follows this window
    rtc_anchor_dt: datetime # datetime of the RTC_SET event that follows this window

def _parse_dt(date_str: str, time_str: str) -> datetime:
    """Parse a date and time string into a datetime object. Milliseconds is normalized."""
    parts = time_str.split(".")
    if len(parts) == 2:
        frac = parts[1].ljust(6, "0")  # pad to microseconds
        time_str = f"{parts[0]}.{frac}"
    return datetime.strptime(f"{date_str} {time_str}", f"{_DATE_FORMAT} {_TIME_FORMAT}")

def _format_dt(dt: datetime) -> tuple[str, str]:
    """Format a datetime object into a date and time string."""
    date_str = dt.strftime(_DATE_FORMAT)
    time_str = dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"  # milliseconds
    return date_str, time_str

def _is_invalid_date(date_str: str) -> bool:
    """Check if a date string is invalid."""
    try:
        return datetime.strptime(date_str, _DATE_FORMAT).year == EPOCH_YEAR
    except (ValueError, TypeError):
        return False

def _is_midnight_zero(row: dict) -> bool:
    """Return True if the row carries exactly 01/01/2000 00:00:00.000."""
    return (
        row.get("event_date") == _EPOCH_DATE 
        and row.get("event_time", "").startswith("00:00:00.") 
        and int(row["event_time"].split(".")[1].ljust(3, "0")[:3]) == 0
    )

def _detect_windows(rows: list[dict]) -> list[Window]:
    """Scan the row list and return one Windows for each contiguous year-2000 block followed by a RTC_SET event."""
    windows: list[Window] = []
    n = len(rows)
    i = 0

    while i < n:
        if not _is_invalid_date(rows[i].get("event_date", "")):
            i += 1
            continue

        # Found the start of a window
        win_start = i
        while i < n and _is_invalid_date(rows[i].get("event_date", "")):
            i += 1
        win_end = i - 1 # last invalid index (inclusive)

        # Look ahead for the RTC_SET that anchors this window
        anchor_idx: int | None = None
        anchor_dt: datetime | None = None

        for j in range(i, n):
            if rows[j].get("event_id") == RTC_SET_EVENT_ID:
                try:
                    anchor_dt = _parse_dt(rows[j]["event_date"], rows[j]["event_time"])
                    anchor_idx = j
                    break
                except (ValueError, KeyError):
                    logger.warning(f"Invalid RTC_SET event at index {j}: {rows[j]}")
                    continue

        if anchor_idx is None:
            logger.warning(f"Window at indices {win_start}-{win_end} has no following RTC_SET event. Skipping.")
        else:
            windows.append(
                Window(
                    start=win_start,
                    end=win_end,
                    rtc_anchor_idx=anchor_idx,
                    rtc_anchor_dt=anchor_dt
                )
            )
            logger.debug("Window detected.", start=win_start, end=win_end, rtc_anchor_idx=anchor_idx, rtc_anchor_dt=anchor_dt)

    return windows

def _split_into_subwindows(rows: list[dict], window: Window) -> list[tuple[int, int]]:
    """Split a window into subwindows based on SWITCH_ON and SWITCH_OFF events."""
    subwindows: list[tuple[int, int]] = []
    sub_start: int | None = None

    for i in range(window.start, window.end + 1):
        event_id = rows[i].get("event_id")
        
        if event_id == SWITCH_ON_EVENT_ID:
            if sub_start is not None:
                # Anomalous ON → ON: found a SWITCH_ON without a preceding SWITCH_OFF
                logger.warning(f"Found SWITCH_ON at index {i} without preceding SWITCH_OFF. Previous subwindow will be closed.")
                subwindows.append((sub_start, i - 1))
            sub_start = i
        
        elif event_id == SWITCH_OFF_EVENT_ID:
            if sub_start is not None:
                subwindows.append((sub_start, i))
                sub_start = None
            else:
                # Orphan OFF at the beginning of the window
                logger.warning(f"Found SWITCH_OFF at index {i} without preceding SWITCH_ON. This subwindow will be closed.")
                subwindows.append((window.start, i))
    
    if sub_start is not None:
        subwindows.append((sub_start, window.end))
    
    return subwindows

def _shift_subwindow(
    rows: list[dict],
    sub_start: int,
    sub_end: int,
    delta: timedelta,
):
    """Apply *delta* to every row in the subwindow [sub_start, sub_end] (inclusive)."""
    for i in range(sub_start, sub_end + 1):
        try:
            dt = _parse_dt(rows[i]["event_date"], rows[i]["event_time"])
        except (ValueError, KeyError):
            logger.warning("Cannot parse datetime, skipping row.", index=i)
            continue
        corrected = dt + delta
        rows[i]["event_date"], rows[i]["event_time"] = _format_dt(corrected)

def _compute_delta(
    rows: list[dict],
    sub_end: int,
    anchor_dt: datetime,
) -> timedelta:
    """Compute the timedelta to add to all rows in a sub-window"""
    try:
        last_dt = _parse_dt(rows[sub_end]["event_date"], rows[sub_end]["event_time"])
    except (ValueError, KeyError):
        logger.warning("Cannot parse datetime for subwindow end, using anchor datetime.", index=sub_end)
        raise
    
    return anchor_dt - last_dt

def _make_sentinel(base_row: dict, dt: datetime, value: int) -> dict:
    """Create a sentinel row based on *base_row* with the given datetime and value."""
    sentinel = copy.deepcopy(base_row)
    sentinel["event_date"], sentinel["event_time"] = _format_dt(dt)
    sentinel["value"] = value
    sentinel["_is_sentinel"] = True
    return sentinel

def _handle_twin_zero_block(
    rows: list[dict],
    twin_zero_subwindow: tuple[int, int],
    second_window_first_corrected_dt: datetime,
) -> list[dict]:
    """Wrap the twin-zero block with two sentinels to preserve the gap between the two windows."""
    sub_start, sub_end = twin_zero_subwindow
    count = sub_end - sub_start + 1

    # Anchor point: 1 ms before the real session starts
    block_end_dt = second_window_first_corrected_dt - timedelta(milliseconds=_TWIN_ZERO_OFFSET_MS)

    block_start_dt = block_end_dt - timedelta(milliseconds=1)
    step = timedelta(microseconds=1000 // max(count, 1)) if count > 0 else timedelta(milliseconds=1)

    inner_rows: list[dict] = []
    for k, i in enumerate(range(sub_start, sub_end + 1)):
        inner = copy.deepcopy(rows[i])
        dt = block_start_dt + k * step
        inner["event_date"], inner["event_time"] = _format_dt(dt)
        inner_rows.append(inner)
    
    # Create sentinels
    sentinel_open = _make_sentinel(rows[sub_start], block_start_dt, SENTINEL_VALUE)
    sentinel_close = _make_sentinel(rows[sub_end], block_end_dt, SENTINEL_VALUE)

    logger.info("Twin-zero block handled with sentinels.", start=sub_start, end=sub_end, count=count)

    return [sentinel_open, *inner_rows, sentinel_close]

def _verify_monotonicity(rows: list[dict], start: int, end: int):
    """Verify that the timestamps in rows[start:end] are strictly increasing."""
    prev_dt: datetime | None = None
    prev_idx: int | None = None

    for idx in range(start, end + 1):
        try:
            dt = _parse_dt(rows[idx]["event_date"], rows[idx]["event_time"])
        except (ValueError, KeyError):
            continue

        if prev_dt is not None and dt < prev_dt:
            logger.warning("Monotonicity violation detected after correction.", index=idx, previous_index=prev_idx, current_dt=dt, previous_dt=prev_dt)
        
        prev_dt = dt
        prev_idx = idx

def clean_timestamps(rows: list[dict]) -> list[dict]:
    """
    Return a new list of rows with corrected timestamps.
    """
    if not rows:
        return []
    
    working: list[dict] = copy.deepcopy(rows)
    n = len(working)

    windows = _detect_windows(working)
    if not windows:
        logger.debug("No windows detected, returning original rows.")
        return working
    
    insertions: dict[int, list[dict]] = {}
    
    for win_idx, win in enumerate(windows):
        subwindows = _split_into_subwindows(working, win)

        if not subwindows:
            logger.warning("Window has no subwindows, skipping.", window_index=win_idx, start=win.start, end=win.end)
            continue

        twin_zero_subwindow: tuple[int, int] | None = None
        correctable_subwindows = list(subwindows)

        if (
            len(subwindows) == 2 
            and _is_midnight_zero(working[subwindows[0][0]]) 
            and _is_midnight_zero(working[subwindows[1][0]])
        ):
            twin_zero_subwindow = subwindows[0]
            correctable_subwindows = subwindows[1:]
            logger.info("Twin-zero block detected.", start=twin_zero_subwindow[0], end=twin_zero_subwindow[1], window_start=win.start, window_end=win.end)
        
        current_anchor_dt = win.rtc_anchor_dt
        for sub_start, sub_end in reversed(correctable_subwindows):
            try:
                delta = _compute_delta(working, sub_end, current_anchor_dt)
            except ValueError:
                logger.error("Failed to compute delta for subwindow, skipping.", sub_start=sub_start, sub_end=sub_end, window_index=win_idx)
                continue

            _shift_subwindow(working, sub_start, sub_end, delta)
            logger.debug("Subwindow timestamps corrected.", sub_start=sub_start, sub_end=sub_end, delta=delta)

            current_anchor_dt = _parse_dt(working[sub_start]["event_date"], working[sub_start]["event_time"])
        
        _verify_monotonicity(
            working,
            win.start if twin_zero_subwindow is None else correctable_subwindows[0][0],
            win.end
        )

        if twin_zero_subwindow is not None and correctable_subwindows:
            first_corrected_idx = correctable_subwindows[0][0]
            try:
                next_dt = _parse_dt(working[first_corrected_idx]["event_date"], working[first_corrected_idx]["event_time"])
            except (ValueError, KeyError):
                logger.error("Failed to parse datetime for first corrected row after twin-zero block, skipping sentinel insertion.", index=first_corrected_idx)
                continue
            twin_rows = _handle_twin_zero_block(working, twin_zero_subwindow, next_dt)
            insertions[first_corrected_idx] = twin_rows
        
    if insertions:
        result: list[dict] = []
        for idx, row in enumerate(working):
            if idx in insertions:
                result.extend(insertions[idx])
            result.append(row)
        return result
    
    return working
