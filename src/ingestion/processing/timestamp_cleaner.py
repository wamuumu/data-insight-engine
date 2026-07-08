from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum

import pandas as pd

from common.constants import EventID
from common.logging import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_EPOCH_YEAR = 2000
_SENTINEL_VALUE = 1
_TIMEDELTA_OFFSET_SECOND = timedelta(seconds=1)
_TIMEDELTA_OFFSET_MILLIS = timedelta(milliseconds=1)
_TSSC_TIMESTAMP_ANCHOR = datetime(2020, 1, 1, 0, 0, 0, 0)

_SESSION_START_EVENTS = frozenset({EventID.SWITCH_ON, EventID.HL_RESET})

_COUNTER_MODULUS: int | None = None

_SENTINEL_PRIORITY = {
    EventID.RTC_MISS_END: 0,
    EventID.RTC_RESET: 1,
    EventID.RTC_GUESS: 2,
    EventID.RTC_MISS_START: 3,
    EventID.MISS_LOGS: 4,
}


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


class BreakKind(IntEnum):
    """A discontinuity detected in the *raw* log stream (pre-correction)."""

    RTC_RESET = 1
    MISS_LOGS = 2


@dataclass
class Break:
    """
    A single discontinuity anchored at a specific row position.
    
    `position` is the index of the row *after* which the break occurs.
    """

    kind: BreakKind
    position: int

@dataclass
class Window:
    """A contiguous slice of epoch-year logs."""

    start_idx: int
    end_idx: int
    rtc_anchor_idx: int | None = None
    rtc_anchor_dt: datetime | None = None
    is_guessable: bool = False
    delta: timedelta = field(default=timedelta(0))


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _make_synthetic_row(
    dt: datetime, 
    event_id: EventID, 
    value: int
) -> dict:
    """
    Construct a synthetic sentinel row dictionary with the specified parameters.

    Args:
        dt: The datetime for the synthetic row.
        event_id: The EventID for the synthetic row.
        value: The value associated with the synthetic row.
    Returns:
        A dictionary representing the synthetic sentinel row.
    """
    return {
        "counter": pd.NA,
        "date": pd.NA,
        "time": pd.NA,
        "event_id": event_id,
        "description": event_id.name.replace("_", " "),
        "value": value,
        "datetime": dt,
        "tssc": pd.NA,
    }


def _is_epoch(dt: datetime) -> bool:
    """
    Check if the given datetime is in the epoch year.

    Args:
        dt: The datetime to check.
    
    Returns:
        True if the datetime is in the epoch year, False otherwise.
    """
    return dt.year == _EPOCH_YEAR


def _counter_gap(prev_counter: int, curr_counter: int) -> bool:
    """
    Determine if there is a gap in the counter values.

    Args:
        prev_counter: The previous counter value.
        curr_counter: The current counter value.
    
    Returns:
        True if there is a gap in the counter values, False otherwise.
    """
    expected = prev_counter + 1
    if _COUNTER_MODULUS is not None:
        expected %= _COUNTER_MODULUS
    return curr_counter != expected


def _polish_result(df: pd.DataFrame):
    """
    Perform final polishing on the cleaned DataFrame, dropping unecessary columns.

    Args:
        df: The cleaned DataFrame to polish.
    """
    df.drop(columns=["counter", "description"], inplace=True)

# --------------------------------------------------------------------------- #
# Stage 1 -- parsing
# --------------------------------------------------------------------------- #


def _parse_datetime_stage(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse the 'date' and 'time' columns into a single 'datetime' column, handling errors gracefully.

    Args:
        df: DataFrame containing the log records.

    Returns:
        A DataFrame with the parsed datetime column.
    """

    df = df.copy(deep=True).reset_index(drop=True)

    try:
        dt = pd.to_datetime(df["date"] + " " + df["time"], dayfirst=True, format="%d/%m/%Y %H:%M:%S.%f")
    except Exception as e:
        raise ValueError("Failed to parse 'date' and 'time' columns into datetime.") from e

    df["datetime"] = dt

    return df


# --------------------------------------------------------------------------- #
# Memory rollover detection and rotation
# --------------------------------------------------------------------------- #


def _rollover_stage(df: pd.DataFrame) -> int | None:
    """
    Detect whether a rollover has occurred by identifying the HL Download event.

    Args:
        df: DataFrame containing the log records.

    Returns:
        The index of the rollover head or ``None`` if no rollover is detected.
    """

    hl_rows = df[df["event_id"] == EventID.HL_DOWNLOAD]

    if hl_rows.empty:
        raise LookupError("No HL Download event found in logs, impossible state.")
    
    if hl_rows["datetime"].dt.year.eq(_EPOCH_YEAR).any():
        raise ValueError("HL Download event has epoch-year timestamp, cannot determine rollover.")

    # Deterministic tie-break
    ordered = hl_rows.sort_values(by="datetime", ascending=False, kind="stable")
    ordered = ordered.loc[ordered["datetime"] == ordered["datetime"].iloc[0]].sort_index(ascending=False)
    most_recent_idx = ordered.index[0]


    if most_recent_idx == len(df) - 1:
        logger.debug("HL Download event is the last row, no rollover detected.")
        return None
    
    return int(most_recent_idx)


def _rotate_for_rollover(df: pd.DataFrame, rollover_head_idx: int) -> pd.DataFrame:
    """
    Rotate the DataFrame to account for rollover by moving the rows after the rollover head to the front.

    Args:
        df: DataFrame containing the log records.
        rollover_head_idx: The index of the rollover head.
    
    Returns:
        A new DataFrame with the rows after the rollover head moved to the front.
    """
    return pd.concat(
        [
            df.iloc[rollover_head_idx + 1:],
            df.iloc[:rollover_head_idx + 1],
        ],
        ignore_index=True
    )


# --------------------------------------------------------------------------- #
# Discontinuity / break detection
# --------------------------------------------------------------------------- #


def _detect_breaks(df: pd.DataFrame, seam_idx: int | None) -> list[Break]:
    """
    Detect breaks in the log stream, which are discontinuities in the timestamps or counters.

    Args:
        df: DataFrame containing the log records.
        seam_idx: The index of the rollover seam, if any.
    
    Returns:
        A list of Break objects representing the detected breaks.
    """
    breaks: list[Break] = []
    n = len(df)

    for i in range(1, n):
        if i == seam_idx:
            # Skip the seam index, as it is a known discontinuity due to rollover.
            continue

        prev_dt = df.at[i - 1, "datetime"]
        curr_dt = df.at[i, "datetime"]
        curr_event = df.at[i, "event_id"]

        if (
            prev_dt - curr_dt > _TIMEDELTA_OFFSET_SECOND
            and curr_event != EventID.RTC_SET
        ):
            breaks.append(Break(
                kind=BreakKind.RTC_RESET, 
                position=i
            ))
            continue

        curr_counter = df.at[i, "counter"]
        prev_counter = df.at[i - 1, "counter"]

        if curr_event in _SESSION_START_EVENTS:
            # Skip session start events, as they may reset the counter.
            continue

        if _counter_gap(prev_counter, curr_counter):
            breaks.append(Break(
                kind=BreakKind.MISS_LOGS, 
                position=i
            ))
    
    logger.debug(f"Detected {len(breaks)} breaks in the log stream:")
    for b in breaks:
        logger.debug(f"  {b.kind.name} (position {b.position})")

    return breaks


# --------------------------------------------------------------------------- #
# Invalid window detection
# --------------------------------------------------------------------------- #


def _detect_windows(df: pd.DataFrame, breaks: list[Break]) -> list[Window]:
    """
    Detect contiguous windows of invalid epoch-year logs, additionally splitting a run 
    whenever a `Break` is encountered.

    Args:
        df: DataFrame containing the log records.
        breaks: A list of Break objects representing the detected breaks.
    Returns:
        A list of Window objects representing the detected windows.
    """
    break_positions = {b.position for b in breaks}
    windows: list[Window] = []
    n = len(df)

    i = 0
    while i < n:   
        if not _is_epoch(df.at[i, "datetime"]):
            i += 1
            continue
        
        start_idx = i
        end_idx = i
        
        while (
            end_idx + 1 < n
            and _is_epoch(df.at[end_idx + 1, "datetime"])
            and (end_idx + 1) not in break_positions
        ):
            end_idx += 1
        
        rtc_anchor_idx: int | None = None
        rtc_anchor_dt: datetime | None = None

        if (
            end_idx + 1 < n
            and not _is_epoch(df.at[end_idx + 1, "datetime"])
        ):
            rtc_anchor_idx = end_idx + 1
            rtc_anchor_dt = df.at[rtc_anchor_idx, "datetime"]

        
        windows.append(
            Window(
                start_idx=start_idx,
                end_idx=end_idx,
                rtc_anchor_idx=rtc_anchor_idx,
                rtc_anchor_dt=rtc_anchor_dt,
                is_guessable=rtc_anchor_dt is not None
            )
        )
        i = end_idx + 1

    logger.debug(f"Detected {len(windows)} contiguous windows of epoch-year logs:")
    for win in windows:
        logger.debug(f"  start={win.start_idx}, end={win.end_idx}, is_guessable={win.is_guessable}")

    return windows


# --------------------------------------------------------------------------- #
# Window resolution and datetime shifting (in-place)
# --------------------------------------------------------------------------- #


def _resolve_and_shift(df: pd.DataFrame, windows: list[Window]):
    """
    Resolve the detected windows and apply necessary shifts to the datetime values.

    Args:
        df: DataFrame containing the log records.
        windows: A list of Window objects representing the detected windows.
    """
    next_chain_reference_dt: datetime | None = None

    for win in reversed(windows):

        if win.is_guessable:
            # Use the RTC anchor as the reference datetime for this window
            reference_dt = win.rtc_anchor_dt
        else:
            reference_dt = next_chain_reference_dt
            if reference_dt is None:
                raise RuntimeError("Cannot resolve unguessable window: no reference datetime available.")

        last_dt = df.at[win.end_idx, "datetime"]
        delta = reference_dt - last_dt - _TIMEDELTA_OFFSET_MILLIS

        for i in range(win.start_idx, win.end_idx + 1):
            df.at[i, "datetime"] += delta
        
        win.delta = delta

        next_chain_reference_dt = df.at[win.start_idx, "datetime"] - _TIMEDELTA_OFFSET_MILLIS


# --------------------------------------------------------------------------- #
# Sentinel creation
# --------------------------------------------------------------------------- #


def _bucket_add(
    buckets: dict[int, list[tuple[int, dict]]],
    position: int,
    row: dict
):
    """
    Add a row to the appropriate bucket for insertion.

    Args:
        buckets: A dictionary where keys are positions and values are lists of rows to insert.
        position: The index at which the row should be inserted.
        row: The row dictionary to insert.
    """
    priority = _SENTINEL_PRIORITY[row["event_id"]]
    buckets.setdefault(position, []).append((priority, row))


def _build_sentinels(
    df: pd.DataFrame, 
    windows: list[Window], 
    breaks: list[Break]
) -> tuple[dict[int, list[tuple[int, dict]]], dict[int, list[tuple[int, dict]]]]:
    """
    Build every sentinel row keyed by the position it must be inserted at.

    Args:
        df: DataFrame containing the log records.
        windows: A list of Window objects representing the detected windows.
        breaks: A list of Break objects representing the detected breaks.
    
    Returns:
        A tuple of two dictionaries (before, after):
        - `before[i]` holds rows to insert immediately before original row `i`.
        - `after[i]` holds rows to insert immediately after original row `i`.
    """
    n = len(df)
    before: dict[int, list[tuple[int, dict]]] = {}
    after: dict[int, list[tuple[int, dict]]] = {}


    # Handle sentinel rows for each break
    for b in breaks:
        i = b.position
        prev_dt = df.at[i - 1, "datetime"]

        if b.kind is BreakKind.RTC_RESET:
            row = _make_synthetic_row(
                dt=prev_dt + _TIMEDELTA_OFFSET_MILLIS,
                event_id=EventID.RTC_RESET,
                value=_SENTINEL_VALUE
            )
        else:
            curr_dt = df.at[i, "datetime"]
            curr_counter = df.at[i, "counter"]
            row = _make_synthetic_row(
                dt=curr_dt - _TIMEDELTA_OFFSET_MILLIS,
                event_id=EventID.MISS_LOGS,
                value=curr_counter
            )
        
        _bucket_add(before, i, row)
    

    # Handle sentinel rows for each window
    for win in windows:
        if win.is_guessable:
            # Window bounded to a valid RTC anchor, can be corrected by guessing RTC
            start_dt = df.at[win.start_idx, "datetime"]
            row = _make_synthetic_row(
                dt=start_dt - _TIMEDELTA_OFFSET_MILLIS,
                event_id=EventID.RTC_GUESS,
                value=_SENTINEL_VALUE
            )
            _bucket_add(before, win.start_idx, row)
            continue
        
        # Invalid windows with no RTC anchor require MISS_START and MISS_END sentinels

        if win.start_idx == 0:
            miss_start_dt = df.at[0, "datetime"] - _TIMEDELTA_OFFSET_MILLIS
        else:
            miss_start_dt = df.at[win.start_idx - 1, "datetime"] + _TIMEDELTA_OFFSET_MILLIS
        
        row = _make_synthetic_row(
            dt=miss_start_dt,
            event_id=EventID.RTC_MISS_START,
            value=_SENTINEL_VALUE
        )
        _bucket_add(before, win.start_idx, row)

        if win.end_idx + 1 >= n:
            # EOF reached
            miss_end_dt = df.at[win.end_idx, "datetime"] + _TIMEDELTA_OFFSET_MILLIS
        else:
            miss_end_dt = df.at[win.end_idx + 1, "datetime"] - _TIMEDELTA_OFFSET_MILLIS
        
        row = _make_synthetic_row(
            dt=miss_end_dt,
            event_id=EventID.RTC_MISS_END,
            value=_SENTINEL_VALUE
        )
        _bucket_add(after, win.end_idx, row)
    
    logger.debug(f"Detected sentinels to insert before:")
    for position in sorted(before):
        for priority, row in before[position]:
            logger.debug(f"    {EventID(row['event_id']).name} (position {position}) (priority {priority})")

    logger.debug(f"Detected sentinels to insert after:")
    for position in sorted(after):
        for priority, row in after[position]:
            logger.debug(f"    {EventID(row['event_id']).name} (position {position}) (priority {priority})")
    
    return before, after


# --------------------------------------------------------------------------- #
# Real dataset + synthetic rows assembly (single pass, no row insertion yet)
# --------------------------------------------------------------------------- #


def _assemble(
    df: pd.DataFrame,
    before: dict[int, list[tuple[int, dict]]],
    after: dict[int, list[tuple[int, dict]]]
) -> pd.DataFrame:
    """
    Assemble the final DataFrame by inserting sentinel rows before and after the original rows.

    Args:
        df: DataFrame containing the log records.
        before: A dictionary where keys are positions and values are lists of rows to insert before.
        after: A dictionary where keys are positions and values are lists of rows to insert after.
    
    Returns:
        A new DataFrame with the sentinel rows inserted.
    """
    n = len(df)
    rows: list[dict] = []

    for i in range(n):
        # Prepend sentinels before the current row
        before_priorities = sorted(before.get(i, []), key=lambda x: x[0])
        for _, row in before_priorities:
            rows.append(row)

        # Current row
        rows.append(df.iloc[i].to_dict())

        # Postpend sentinels after the current row
        after_priorities = sorted(after.get(i, []), key=lambda x: x[0])
        for _, row in after_priorities:
            rows.append(row)
    
    return pd.DataFrame(rows, columns=df.columns).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# TSSC calculation (Timestamp session start + counter)
# --------------------------------------------------------------------------- #


def _compute_tssc(df: pd.DataFrame, seam_idx: int | None = None):
    """
    Calculate the Timestamp Session Start + Counter (TSSC) for each row in the DataFrame.

    Args:
        df: DataFrame containing the log records.
        seam_idx: Index of the seam row, if applicable.
    """
    session_start_dt: datetime | None = None

    tssc_values: list[int] = []

    for i, row in df.iterrows():
        event_id = row["event_id"]
        counter = row["counter"]
        dt = row["datetime"]
        
        is_truncated = False
        if i > 0 and i != seam_idx:
            prev_counter = df.at[i - 1, "counter"]
            if _counter_gap(prev_counter, counter):
                is_truncated = True

        if event_id in _SESSION_START_EVENTS or is_truncated:
            session_start_dt = dt

        if session_start_dt is None:
            raise RuntimeError("Cannot compute TSSC: no session start event found before row.")

        tssc = int((session_start_dt - _TSSC_TIMESTAMP_ANCHOR).total_seconds() * 1000) + counter
        tssc_values.append(tssc)

    df["tssc"] = tssc_values

    if df["tssc"].isnull().any():
        raise AssertionError("TSSC computation failed: some rows have NaN TSSC values.")


def _assign_sentinel_tssc(df: pd.DataFrame):
    """
    Assign TSSC values to every synthetic row (sentinel) inserted by the cleaning process.

    Args:
        df: DataFrame containing the log records, including synthetic rows.
    """
    if df["tssc"].notna().all():
        return

    n = len(df)
    tssc = df["tssc"].to_numpy(copy=True)

    for i in range(n):

        if pd.notna(tssc[i]):
            continue

        prev_real = None
        next_real = None

        if i > 0 and pd.notna(tssc[i - 1]):
            prev_real = i - 1

        if i + 1 < n and pd.notna(tssc[i + 1]):
            next_real = i + 1

        if prev_real is None and next_real is None:
            raise RuntimeError("Cannot assign TSSC to sentinel: no real neighbours found.")

        anchor = None
        if (
            prev_real is not None
            and df.at[i, "datetime"] == df.at[prev_real, "datetime"] + _TIMEDELTA_OFFSET_MILLIS
        ):
            anchor = prev_real

        elif (
            next_real is not None
            and df.at[i, "datetime"] == df.at[next_real, "datetime"] - _TIMEDELTA_OFFSET_MILLIS
        ):
            anchor = next_real

        elif prev_real is not None and next_real is None:
            anchor = prev_real

        elif next_real is not None and prev_real is None:
            anchor = next_real

        else:
            # Fallback
            prev_delta = abs((df.at[i, "datetime"] - df.at[prev_real, "datetime"]).total_seconds())
            next_delta = abs((df.at[next_real, "datetime"] - df.at[i, "datetime"]).total_seconds())

            anchor = prev_real if prev_delta <= next_delta else next_real

        anchor_tssc = int(tssc[anchor])

        if anchor == prev_real:
            value = anchor_tssc + 1
        else:
            value = anchor_tssc - 1

        if anchor == prev_real:

            j = i - 1
            while j >= 0 and pd.isna(df.at[j, "tssc"]):
                j -= 1

            value = max(value, anchor_tssc + (i - anchor))

        else:

            j = i + 1
            while j < n and pd.isna(df.at[j, "tssc"]):
                j += 1

            value = min(value, anchor_tssc - (anchor - i))

        tssc[i] = value

    df["tssc"] = tssc.astype("int64")

    if df["tssc"].isna().any():
        raise RuntimeError("Failed to assign TSSC to synthetic rows: some rows still have NaN TSSC values.")


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #


def clean_timestamps(
        df: pd.DataFrame
) -> tuple[pd.DataFrame | None, int | None]:
    """
    Orchestrate the entire timestamp cleaning process, including parsing, rollover detection,
    break detection, window detection, resolution, and sentinel insertion.

    Args:
        df: DataFrame containing the log records.
    
    Returns:
        A tuple ``(cleaned_df, rollover_head_index)``, where
        ``cleaned_df`` is a cleaned deepcopy of the DataFrame with corrected timestamps and inserted sentinels, and
        ``rollover_head_index`` is the index of the rollover head if a rollover was detected, or ``None`` otherwise.
    """

    try:
        
        df = _parse_datetime_stage(df)

        rollover_head_idx = _rollover_stage(df)

        seam_idx: int | None = None
        if rollover_head_idx is not None:
            logger.info("Rotating dataframe to account for memory rollover.", rollover_head_index=rollover_head_idx)
            seam_idx = len(df) - (rollover_head_idx + 1) # Position where the "old head" now begins post-rotation
            df = _rotate_for_rollover(df, rollover_head_idx)

        breaks = _detect_breaks(df, seam_idx)
        windows = _detect_windows(df, breaks)
        _resolve_and_shift(df, windows)

        _compute_tssc(df)

        before, after = _build_sentinels(df, windows, breaks)
        result = _assemble(df, before, after)
        _assign_sentinel_tssc(result)

        _polish_result(result)

        return result, rollover_head_idx

    except Exception as e:
        logger.error("Failed during timestamp cleaning process.", error=str(e))
        return None, None
