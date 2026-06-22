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


class Window(NamedTuple):
    """A contiguous slice of row indices that share an invalid epoch."""

    start_idx: int # inclusive
    start_dt: datetime
    end_idx: int # inclusive
    end_dt: datetime
    rtc_anchor_idx: int
    rtc_anchor_dt: datetime

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

def _pre_process_timestamps(rows: list[dict]) -> list[dict]:
    """Return the rows with corrected timestamps, if any."""

    # Look for every pair of consecutive rows where the date is the same but the time goes backwards, and correct the second one
    # This is a simple heuristic to correct for clock resets on SWITCH_ON_EVENT_ID, since we expect logs are chronologically ordered 
    
    i = 1 # Start from second row to compare with previous

    while i < len(rows):

        previous = rows[i - 1]
        current = rows[i]

        previous_dt = _parse_dt(previous["event_date"], previous["event_time"])
        current_dt = _parse_dt(current["event_date"], current["event_time"])

        # If the current timestamp is exactly the epoch timestamp, we insert an RTC RESET event before it
        if current_dt == datetime(EPOCH_YEAR, 1, 1, 0, 0, 0, 0):
            logger.warning("Detected epoch timestamp, adding RTC Reset event.", index=i)
            rtc_reset_row = {
                "event_id": SENTINEL_VALUE,
                "value": SENTINEL_VALUE,
                "event_date": current["event_date"],
                "event_time": current["event_time"],
            }
            rows.insert(i, rtc_reset_row)
            i += 1

        # If the current timestamp is the same as the previous timestamp (ignoring microseconds) but the current timestamp is less than the previous timestamp, we assume a clock reset has occurred and correct the current timestamp to be after the previous timestamp
        if current_dt.replace(microsecond=0) == previous_dt.replace(microsecond=0) and current_dt < previous_dt:
                            
            # Probably a clock reset due to memory, correct current timestamp to be after previous. Should happen only on SWITCH_ON_EVENT_ID
            if current.get("event_id") == SWITCH_ON_EVENT_ID:
                logger.info("Detected backward time jump due to SWITCH_ON_EVENT_ID, correcting timestamp.", index=i, previous_event_id=previous.get("event_id"), previous_date=previous.get("event_date"), previous_time=previous.get("event_time"), current_event_id=current.get("event_id"), current_date=current.get("event_date"), current_time=current.get("event_time"))
                corrected_dt = previous_dt + timedelta(milliseconds=1)
                current["event_date"], current["event_time"] = _format_dt(corrected_dt)
            else:
                logger.warning("Detected backward time jump, but not due to SWITCH_ON_EVENT_ID, skipping correction.", index=i, previous_event_id=previous.get("event_id"), previous_date=previous.get("event_date"), previous_time=previous.get("event_time"), current_event_id=current.get("event_id"), current_date=current.get("event_date"), current_time=current.get("event_time"))
        
        i += 1

def _detect_windows(rows: list[dict]) -> list[Window]:
    windows: list[Window] = []

    for i, row in enumerate(rows):
        try:
            current_dt = _parse_dt(row["event_date"], row["event_time"])
        except Exception:
            continue

        if row.get("event_id") == RTC_SET_EVENT_ID:
            rtc_anchor_idx = i
            rtc_anchor_dt = current_dt
            
            start_idx: int | None = None
            start_dt: datetime | None = None
            end_idx: int | None = None
            end_dt: datetime | None = None

            for j in range(i - 1, -1, -1):
                try:
                    previous_dt = _parse_dt(rows[j]["event_date"], rows[j]["event_time"])
                except Exception:
                    continue

                if end_dt is None:
                    end_idx = j
                    end_dt = previous_dt
                    continue

                if previous_dt.year == EPOCH_YEAR:
                    continue
                
                if previous_dt.date() != end_dt.date():
                    start_idx = j + 1
                    start_dt = _parse_dt(rows[start_idx]["event_date"], rows[start_idx]["event_time"])
                    break
            
            if end_dt is not None and (start_dt is None or start_idx is None):
                # End of window is valid but start is not, assume window starts at the beginning of the file
                start_idx = 0
                start_dt = _parse_dt(rows[0]["event_date"], rows[0]["event_time"])
            
            if start_dt is not None and (end_dt is None or end_idx is None):
                # Start of window is valid but end is not, assume window ends at the end of the file
                end_idx = len(rows) - 1
                end_dt = _parse_dt(rows[-1]["event_date"], rows[-1]["event_time"])

            windows.append(
                Window(
                    start_idx=start_idx,
                    start_dt=start_dt, 
                    end_idx=end_idx, 
                    end_dt=end_dt,
                    rtc_anchor_idx=rtc_anchor_idx, 
                    rtc_anchor_dt=rtc_anchor_dt
                )
            )
    
    # detect all windows overlapping and merge them into a single window
    merged_windows: list[Window] = []
    for win in windows:
        if not merged_windows:
            merged_windows.append(win)
            continue

        last_win = merged_windows[-1]

        if win.start_idx <= last_win.end_idx:
            # merge windows
            new_start = min(last_win.start_idx, win.start_idx)
            new_start_dt = min(last_win.start_dt, win.start_dt)
            new_end = max(last_win.end_idx, win.end_idx)
            new_end_dt = max(last_win.end_dt, win.end_dt)
            merged_windows[-1] = Window(start_idx=new_start, end_idx=new_end, start_dt=new_start_dt, end_dt=new_end_dt, rtc_anchor_idx=win.rtc_anchor_idx, rtc_anchor_dt=win.rtc_anchor_dt)
        else:
            merged_windows.append(win)

    return merged_windows

def _find_date_groups(rows: list[dict], window: Window) -> list[tuple[int, int]]:
    """Return a list of (start_idx, end_idx) tuples for each contiguous group of rows with the same date in the window."""
    date_groups: list[tuple[int, int]] = []
    current_date: datetime | None = None
    current_start: int | None = None

    for i in range(window.start_idx, window.end_idx + 1):
        try:
            dt = _parse_dt(rows[i]["event_date"], rows[i]["event_time"])
        except (ValueError, KeyError):
            logger.warning("Cannot parse datetime, skipping row.", index=i)
            continue

        if current_date is None:
            current_date = dt.date()
            current_start = i
        elif dt.date() != current_date:
            date_groups.append((current_start, i - 1))
            current_date = dt.date()
            current_start = i

    if current_start is not None:
        date_groups.append((current_start, window.end_idx))

    return date_groups

def _shift_window(
    rows: list[dict],
    window: Window
):
    """Apply *delta* to every row in the subwindow [sub_start, sub_end] (inclusive)."""
    # for i in range(sub_start, sub_end + 1):
    #     try:
    #         dt = _parse_dt(rows[i]["event_date"], rows[i]["event_time"])
    #     except (ValueError, KeyError):
    #         logger.warning("Cannot parse datetime, skipping row.", index=i)
    #         continue
    #     corrected = dt + delta
    #     rows[i]["event_date"], rows[i]["event_time"] = _format_dt(corrected)

    date_groups = _find_date_groups(rows, window)

    prev_delta = None

    for sub_start, sub_end in date_groups:
        # TODO: based on the offset, start from 0 to groups_offset and apply the delta to each group
        # Decide wheter to do a positive or negative delta based on the current group date and the anchor date
        
        delta = _compute_delta(rows, sub_end, window.rtc_anchor_dt)

        if prev_delta is None:
            prev_delta = delta
        else:
            logger.info("Delta diff.", diff=delta - prev_delta, prev_delta=prev_delta, delta=delta)
        logger.info("Applying delta to date group.", anchor_dt=window.rtc_anchor_dt, end=rows[sub_end]["event_date"], delta=delta)

def _compute_delta(
    rows: list[dict],
    sub_end: int,
    anchor_dt: datetime
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

    # TODO: there can be RTC SET also for non invalid rows
    # If previous row is invalid, correct date and then time
    # If previous row has time < current row time, then add delta otherwise remove delta
    # For non-invalid rows, manage deltas until previous SWITCH_ON_EVENT_ID or for same dateadd

    # TODO: RTC GUESSED before two or more consecutive blocks starting with 01/01/2000 00:00:00.000 (always):
    # specifically, adjust previous block of RTC SET, guess the others recursively

    working = copy.deepcopy(rows)

    # First pass: correct timestamps and add RTC RESET events
    _pre_process_timestamps(working)

    windows = _detect_windows(working)
    if not windows:
        logger.debug("No windows detected, returning original rows.")
        return working    
    
    for win in windows:
        logger.info("Window detected.", 
            start_idx=win.start_idx,
            start_dt=win.start_dt,
            end_idx=win.end_idx,
            end_dt=win.end_dt,
            rtc_anchor_idx=win.rtc_anchor_idx,
            rtc_anchor_dt=win.rtc_anchor_dt,
            is_rtc_reset=working[win.start_idx].get("event_id") == SENTINEL_VALUE
        )

        _shift_window(working, win)
    
    return working

