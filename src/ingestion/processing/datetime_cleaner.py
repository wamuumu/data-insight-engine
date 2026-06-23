from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import NamedTuple

from common.constants import (
    RTC_SET_EVENT_ID,
    RTC_RESET_EVENT_ID,
    RTC_GUESSED_EVENT_ID,
    SWITCH_ON_EVENT_ID,
    SENTINEL_VALUE,
    EPOCH_YEAR
)
from common.logging import get_logger

logger = get_logger(__name__)


_DATE_FORMAT = "%d/%m/%Y"
_TIME_FORMAT = "%H:%M:%S.%f"


class Window(NamedTuple):
    """A contiguous slice of logs identifying the timestamps that need to be shifted by some delta."""

    start_idx: int
    start_dt: datetime
    end_idx: int
    end_dt: datetime
    rtc_anchor_idx: int
    rtc_anchor_dt: datetime
    is_guessed: bool = False

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
            _insert_rtc_reset(rows, i, current_dt)
            i += 1
        
        # If the current timestamp is less than the previous timestamp and both are in the epoch year, we assume a clock reset
        if (
            current_dt.year == EPOCH_YEAR 
            and previous_dt.year == EPOCH_YEAR 
            and current_dt < previous_dt 
            and (previous_dt - current_dt) > timedelta(seconds=1)
        ):
            logger.warning(
                "Detected backward time jump within epoch date, treating as implicit RTC Reset.",
                index=i,
                previous_time=previous["event_time"],
                current_time=current["event_time"],
            )
            _insert_rtc_reset(rows, i, current_dt)

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
                
                if rows[j].get("event_id") == RTC_RESET_EVENT_ID:
                    start_idx = j
                    start_dt = previous_dt
                    break

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

            windows.append(Window(
                start_idx=start_idx,
                start_dt=start_dt, 
                end_idx=end_idx, 
                end_dt=end_dt,
                rtc_anchor_idx=rtc_anchor_idx, 
                rtc_anchor_dt=rtc_anchor_dt
            ))
    
    # detect all windows overlapping and merge them into a single window
    merged_windows: list[Window] = []
    for win in windows:
        if not merged_windows:
            merged_windows.append(win)
            continue

        last_win = merged_windows[-1]

        if win.start_idx <= last_win.end_idx:
            # Only merge if neither boundary is a sentinel-started epoch block.
            # Two consecutive epoch windows must remain separate for guessing correctly.

            last_is_epoch = last_win.start_dt == datetime(EPOCH_YEAR, 1, 1, 0, 0, 0, 0)
            current_is_epoch = win.start_dt == datetime(EPOCH_YEAR, 1, 1, 0, 0, 0, 0)

            if last_is_epoch and current_is_epoch:
                merged_windows.append(win)
            else:
                new_start = min(last_win.start_idx, win.start_idx)
                new_start_dt = min(last_win.start_dt, win.start_dt)
                new_end = max(last_win.end_idx, win.end_idx)
                new_end_dt = max(last_win.end_dt, win.end_dt)
                merged_windows[-1] = Window(
                    start_idx=new_start, 
                    end_idx=new_end, 
                    start_dt=new_start_dt, 
                    end_dt=new_end_dt, 
                    rtc_anchor_idx=win.rtc_anchor_idx, 
                    rtc_anchor_dt=win.rtc_anchor_dt
                )
        else:
            merged_windows.append(win)
    
    uncovered: list[Window] = []
    for k, row in enumerate(rows):
        if row.get("event_id") != RTC_RESET_EVENT_ID:
            continue

        already_covered = any(win.start_idx <= k <= win.end_idx for win in merged_windows)
        if already_covered:
            continue

        block_end_idx = k
        for m in range(k + 1, len(rows)):
            try:
                dt = _parse_dt(rows[m]["event_date"], rows[m]["event_time"])
            except Exception:
                continue
            if dt.year != EPOCH_YEAR or rows[m].get("event_id") == RTC_RESET_EVENT_ID:
                block_end_idx = m - 1
                break
        else:
            block_end_idx = len(rows) - 1
        
        try:
            block_start_dt = _parse_dt(rows[k]["event_date"], rows[k]["event_time"])
            block_end_dt = _parse_dt(rows[block_end_idx]["event_date"], rows[block_end_idx]["event_time"])
        except Exception:
            continue

        uncovered.append(Window(
            start_idx=k,
            end_idx=block_end_idx,
            start_dt=block_start_dt,
            end_dt=block_end_dt,
            rtc_anchor_idx=-1,
            rtc_anchor_dt=datetime.min,
            is_guessed=True
        ))

        if uncovered:
            merged_windows = sorted(merged_windows + uncovered, key=lambda w: w.start_idx)

    return merged_windows

def _shift_window(
    rows: list[dict],
    window: Window
):
    """Apply *delta* to every row in the subwindow [sub_start, sub_end] (inclusive)."""

    _delta = _compute_delta(rows, window.end_idx, window.rtc_anchor_dt)

    for i in range(window.start_idx, window.end_idx + 1):
        try:
            dt = _parse_dt(rows[i]["event_date"], rows[i]["event_time"])
        except (ValueError, KeyError):
            logger.warning("Cannot parse datetime, skipping row.", index=i)
            continue

        corrected = dt + _delta
        rows[i]["event_date"], rows[i]["event_time"] = _format_dt(corrected)

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

def _insert_rtc_reset(rows: list[dict], index: int, reset_dt: datetime) -> int:
    date_str, time_str = _format_dt(reset_dt)
    rtc_reset_row = {
        "event_id": RTC_RESET_EVENT_ID,
        "value": SENTINEL_VALUE,
        "event_date": date_str,
        "event_time": time_str
    }
    rows.insert(index, rtc_reset_row)
    logger.info("Inserted RTC RESET event.", index=index, reset_date=date_str, reset_time=time_str)
    return 1

def _insert_rtc_guessed(rows: list[dict], index: int, guessed_dt: datetime, guess_depth: int) -> int:
    date_str, time_str = _format_dt(guessed_dt)
    rtc_guessed_row = {
        "event_id": RTC_GUESSED_EVENT_ID,
        "value": guess_depth,
        "event_date": date_str,
        "event_time": time_str
    }
    rows.insert(index, rtc_guessed_row)
    logger.info("Inserted RTC GUESSED event.", index=index, guessed_date=date_str, guessed_time=time_str, guess_depth=guess_depth)
    return 1

def _guess_epoch_windows(rows: list[dict], epoch_windows: list[Window]):

    if len(epoch_windows) < 2:
        return
    
    offset = 0

    for i in range(len(epoch_windows) - 2, -1, -1):
        current_win = epoch_windows[i]
        next_win = epoch_windows[i + 1]
        guess_depth = len(epoch_windows) - i - 1

        adj_current_start = current_win.start_idx + offset
        adj_current_end = current_win.end_idx + offset
        adj_next_start = next_win.start_idx + offset
        adj_next_end = next_win.end_idx + offset

        guessed_anchor_dt: datetime | None = None
        for m in range(adj_next_start, adj_next_end + 1):
            if rows[m].get("event_id") == RTC_RESET_EVENT_ID:
                continue
            
            try:
                guessed_anchor_dt = _parse_dt(rows[m]["event_date"], rows[m]["event_time"])
                break
            except (ValueError, KeyError):
                continue
        
        if guessed_anchor_dt is None:
            logger.warning("Could not find a valid datetime to guess for epoch window, skipping.", current_window=current_win, next_window=next_win)
            continue

        guessed_window = Window(
            start_idx=adj_current_start,
            start_dt=current_win.start_dt,
            end_idx=adj_current_end,
            end_dt=current_win.end_dt,
            rtc_anchor_idx=adj_next_start,
            rtc_anchor_dt=guessed_anchor_dt,
            is_guessed=True
        )

        _shift_window(rows, guessed_window)

        inserted = _insert_rtc_guessed(rows, adj_current_end + 1, guessed_anchor_dt, guess_depth)
        offset += inserted

def clean_timestamps(rows: list[dict]) -> list[dict]:
    """
    Return a new list of rows with corrected timestamps.
    """
    if not rows:
        return []

    working = copy.deepcopy(rows)

    # First pass: correct timestamps and add RTC RESET events
    _pre_process_timestamps(working)

    windows = _detect_windows(working)
    if not windows:
        logger.debug("No windows detected, returning original rows.")
        return working    
    
    i = 0
    while i < len(windows):
        win = windows[i]

        # Look ahead: collect a contiguous run of epoch windows
        if win.start_dt.year == EPOCH_YEAR:
            run: list[Window] = [win]
            
            j = i + 1
            while (
                j < len(windows) 
                and windows[j].start_dt.year == EPOCH_YEAR 
                and windows[j].start_idx == windows[j - 1].end_idx + 1
            ):
                run.append(windows[j])
                j += 1
            
            if len(run) == 1:
                if win.rtc_anchor_idx == -1:
                    logger.warning("Detected single epoch window without RTC anchor, skipping correction.", window=win)
                else:
                    logger.info("Detected single epoch window, normal correction will be applied.", window=win)
                    _shift_window(working, win)                    
            else:
                anchor_win_idx = next(
                    (idx for idx in range(len(run) - 1, -1, -1) if run[idx].rtc_anchor_idx != -1),
                    None,
                )
                if anchor_win_idx is None:
                    logger.warning("Detected multiple consecutive epoch windows without RTC anchor, skipping correction.", run=run)
                else:
                    logger.info("Detected multiple consecutive epoch windows, guessing will be applied.", run=run)
                    _shift_window(working, run[anchor_win_idx])
                    _guess_epoch_windows(working, run)
            i = j
        else:
            logger.info("Normal window detected, applying correction.", window=win)
            _shift_window(working, win)
            i += 1
    
    return working

