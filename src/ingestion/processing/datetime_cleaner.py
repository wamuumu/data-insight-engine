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

_TOLERANCE = timedelta(milliseconds=500)


class Window(NamedTuple):
    """A contiguous slice of row indices that share an invalid epoch."""

    start: int # inclusive
    end: int # inclusive
    rtc_anchor_idx: int | None = None
    rtc_anchor_dt: datetime | None = None

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

def _detect_windows(rows: list[dict]) -> list[Window]:
    windows: list[Window] = []
    n = len(rows)

    i = 0

    while i < n:

        # skip non-invalid rows
        try:
            dt = _parse_dt(rows[i]["event_date"], rows[i]["event_time"])
        except Exception:
            i += 1
            continue

        if dt.year != EPOCH_YEAR:
            i += 1
            continue

        start = i
        max_dt = dt

        i += 1

        while i < n:
            try:
                dt = _parse_dt(rows[i]["event_date"], rows[i]["event_time"])
            except Exception:
                break

            if dt.year != EPOCH_YEAR:
                break

            # forward progress
            if dt >= max_dt:
                max_dt = dt
                i += 1
                continue

            # backward jitter (accept, but DO NOT update max_dt)
            if max_dt - dt <= _TOLERANCE:
                i += 1
                continue

            # real break
            break

        end = i - 1

        rtc_anchor_idx = None
        rtc_anchor_dt = None

        if i < n and rows[i].get("event_id") == RTC_SET_EVENT_ID:
            rtc_anchor_idx = i
            rtc_anchor_dt = _parse_dt(
                rows[i]["event_date"],
                rows[i]["event_time"]
            )

        windows.append(Window(start=start, end=end, rtc_anchor_idx=rtc_anchor_idx, rtc_anchor_dt=rtc_anchor_dt))

    return windows

def _shift_window(
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
    
    for win in windows:
        logger.info("Window detected.", 
            start_date=rows[win.start].get("event_date"), 
            start_time=rows[win.start].get("event_time"),
            start_event_id=rows[win.start].get("event_id"),
            end_date=rows[win.end].get("event_date"),
            end_time=rows[win.end].get("event_time"),
            end_event_id=rows[win.end].get("event_id"),
            rtc_date=rows[win.rtc_anchor_idx].get("event_date") if win.rtc_anchor_idx is not None else None,
            rtc_time=rows[win.rtc_anchor_idx].get("event_time") if win.rtc_anchor_idx is not None else None,
        )

        # delta = _compute_delta(working, win.end, win.rtc_anchor_dt)
        # logger.info("Applying correction to window.", start=win.start, end=win.end, delta=str(delta))

        # _shift_window(working, win.start, win.end, delta)
    
    return working
