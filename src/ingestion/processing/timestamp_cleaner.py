from __future__ import annotations

import copy
from datetime import datetime, timedelta
from dataclasses import dataclass

import pandas as pd

from common.constants import EventID
from common.logging import get_logger

logger = get_logger(__name__)


_EPOCH_YEAR = 2000
_SENTINEL_VALUE = 1
_TIMEDELTA_OFFSET_SECOND = timedelta(seconds=1)
_TIMEDELTA_OFFSET_MILLIS = timedelta(milliseconds=1)

@dataclass
class Window:
    """A contiguous slice of logs identifying the timestamps that need to be shifted by some delta."""

    start_idx: int
    start_dt: datetime
    end_idx: int
    end_dt: datetime
    is_guessed: bool
    rtc_anchor_idx: int | None = None
    rtc_anchor_dt: datetime | None = None

    @property
    def is_epoch(self) -> bool:
        return self.start_dt.year == _EPOCH_YEAR
    
    @property
    def is_epoch_start(self) -> bool:
        return self.start_dt == datetime(_EPOCH_YEAR, 1, 1, 0, 0, 0, 0)

# --- Helpers for timestamp cleaning and alignment ---


def _make_synthetic_row(event_id: EventID, value: int, dt: datetime, counter: int) -> dict:
    """
    Construct a synthetic row dictionary with the specified event ID, value, datetime, and counter.

    Args:
        event_id: The EventID for the synthetic row.
        value: The value associated with the synthetic row.
        dt: The datetime for the synthetic row.
        counter: The counter for the synthetic row.
    
    Returns:
        A dictionary representing the synthetic row with keys: 'counter', 'date', 'time', 'event_id', 'description', 'value', and 'datetime'.
    """
    return {
        "counter": counter,
        "date": dt.date().strftime("%d/%m/%Y"),
        "time": dt.time().strftime("%H:%M:%S.%f")[:-3],
        "event_id": event_id,
        "description": event_id.name.replace("_", " "),
        "value": value,
        "datetime": dt,
    }


def _insert_row(df: pd.DataFrame, index: int, row: dict, after: bool = False) -> pd.DataFrame:
    """
    Insert a single row dictionary before (default) or after the specified positional index and return a clean DataFrame.
    """
    split = index + 1 if after else index

    return pd.concat(
        [
            df.iloc[:split],
            pd.DataFrame(
                [row], columns=df.columns
            ),  # Dynamically adapt to current df columns
            df.iloc[split:],
        ],
        ignore_index=True,
    )


def _increase_counter(df: pd.DataFrame, start_index: int) -> pd.DataFrame:
    """
    Update the 'counter' column in the DataFrame starting from the specified index to ensure sequential integrity.

    Args:
        df: DataFrame containing the log records.
        start_index: The index from which to start updating the counter.
    
    Returns:
        A new DataFrame with the 'counter' column updated to ensure sequential integrity.
    """
    i = start_index
    while df.at[i, "counter"] >= df.at[i - 1, "counter"]:
        df.at[i, "counter"] += 1
        i += 1
        if i >= len(df):
            break  

    return df


def _detect_windows(df: pd.DataFrame) -> list[Window]:
    """
    Detect contiguous windows of invalid epoch-year logs.

    Args:
        df: DataFrame containing the log records.
    
    Returns:
        A list of Window objects representing the detected windows.
    """
    windows: list[Window] = []

    i = 0
    while i < len(df):   
        if df.at[i, "datetime"].year != _EPOCH_YEAR:
            i += 1
            continue
        
        start_idx = i
        start_dt = df.at[i, "datetime"]
        
        end_idx = i
        end_dt = start_dt
        while (
            end_idx + 1 < len(df)
            and df.at[end_idx + 1, "datetime"].year == _EPOCH_YEAR
            and df.at[end_idx + 1, "event_id"] != EventID.RTC_RESET
        ):
            end_idx += 1
            end_dt = df.at[end_idx, "datetime"]
        
        rtc_anchor_idx: int | None = None
        rtc_anchor_dt: datetime | None = None

        if end_idx + 1 < len(df) and df.at[end_idx + 1, "event_id"] == EventID.RTC_SET:
            rtc_anchor_idx = end_idx + 1
            rtc_anchor_dt = df.at[rtc_anchor_idx, "datetime"]

        
        windows.append(
            Window(
                start_idx=start_idx,
                end_idx=end_idx,
                start_dt=start_dt,
                end_dt=end_dt,
                is_guessed=True if rtc_anchor_dt is not None else False,
                rtc_anchor_idx=rtc_anchor_idx,
                rtc_anchor_dt=rtc_anchor_dt
            )
        )
        logger.debug(
            "Detected contiguous window of epoch-year logs.",
            window=windows[-1]
        )
        i = end_idx + 1

    return windows


def _shift_window(df: pd.DataFrame, window: Window):
    """
    Shift the timestamps in the specified window by the delta between the RTC anchor and the last row in the window.

    Args:
        df: DataFrame containing the log records.
        window: Window object representing the contiguous slice of logs to be shifted.
    """
    
    anchor_dt = window.rtc_anchor_dt
    last_dt = df.at[window.end_idx, "datetime"]

    if anchor_dt is None:
        logger.warning(
            "No RTC anchor found for window, skipping shift.",
            window=window,
        )
        return
    
    delta = anchor_dt - last_dt

    for i in range(window.start_idx, window.end_idx + 1):
        df.at[i, "datetime"] = df.at[i, "datetime"] + delta


# --- Timestamp cleaning and alignment stages ---

def _rollover_stage(df: pd.DataFrame) -> tuple[bool | None, int | None]:
    """
    Detect whether a rollover has occurred by identifying the HL Download event.

    Args:
        df: DataFrame containing the log records.

    Returns:
        A tuple ``(rollover_detected, rollover_head_index)``, where
        ``rollover_detected`` is ``True`` if a rollover is detected, and
        ``rollover_head_index`` is the index of the rollover head or ``None``
        if no rollover is detected.
    """

    hl_download_rows = df[df["event_id"] == EventID.HL_DOWNLOAD]

    if hl_download_rows.empty:
        logger.error("No HL Download event found in logs, impossible state.")
        return None, None
    
    if hl_download_rows["datetime"].dt.year.eq(_EPOCH_YEAR).any():
        logger.warning("Detected HL Download event with epoch-year timestamp, skipping rollover detection.")
        return None, None

    sorted_hl_download_rows = hl_download_rows.sort_values(by="datetime", ascending=False)
    most_recent_row = sorted_hl_download_rows.index[0]
    next_row = df.iloc[most_recent_row + 1] if most_recent_row + 1 < len(df) else None

    if next_row is None:
        logger.debug("HL Download event is the last row, no rollover detected.")
        return False, None
    
    return True, most_recent_row


def _parse_datetime_stage(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """
    Parse the 'date' and 'time' columns into a single 'datetime' column, handling errors gracefully.

    Args:
        df: DataFrame containing the log records.

    Returns:
        A tuple ``(df, success)``, where
        ``df`` is a deepcopy of the DataFrame with the parsed datetime column, and
        ``success`` is ``True`` if all datetime values were parsed successfully, and ``False`` otherwise.
    """

    df = copy.deepcopy(df).reset_index(drop=True)

    date = pd.to_datetime(df["date"], dayfirst=True, format="mixed", errors="coerce").dt.strftime("%d/%m/%Y")
    time = pd.to_datetime(df["time"], format="mixed", errors="coerce").dt.strftime("%H:%M:%S.%f").str[:-3]

    df["datetime"] = pd.to_datetime(date + " " + time, format="%d/%m/%Y %H:%M:%S.%f", errors="coerce")

    # check if any datetime parsing failed
    if df["datetime"].isnull().any():
        logger.error("Failed to parse some datetime values")
        return df, False

    return df, True


def _normalize_stage(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect backward jumps in timestamps and counter discontinuities, and insert synthetic events to normalize the DataFrame.

    Args:
        df: DataFrame containing the log records.
    
    Returns:
        A new DataFrame with synthetic events inserted to normalize the timestamps and counters.
    """
    i = 1

    while i < len(df):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        
        # --- backward jump ---
        if  (
            (prev.datetime - curr.datetime) > _TIMEDELTA_OFFSET_SECOND
            and curr.event_id != EventID.RTC_SET
        ):
            logger.info(
                "Detected backward jump in timestamps not caused by RTC_SET, inserting synthetic RTC_RESET event.",
                index=i,
                prev_datetime=prev.datetime,
                curr_datetime=curr.datetime,
            )
            reset = _make_synthetic_row(EventID.RTC_RESET, _SENTINEL_VALUE, prev.datetime + _TIMEDELTA_OFFSET_SECOND, prev.counter + 1)
            df = _insert_row(df, i, reset)
            i += 2
            continue
        
        # --- counter discontinuity ---
        if (
            prev.event_id == EventID.SWITCH_OFF
            and curr.counter != 0
        ):
            logger.info(
                "Detected counter discontinuity not caused by rollover, inserting synthetic MISS_LOGS event.",
                index=i,
                prev_counter=prev.counter,
                curr_counter=curr.counter,
            )
            miss = _make_synthetic_row(EventID.MISS_LOGS, curr.counter, curr.datetime - _TIMEDELTA_OFFSET_MILLIS, curr.counter - 1)
            df = _insert_row(df, i, miss)
            i += 2
            continue

        i += 1

    return df


def _align_stage(df: pd.DataFrame) -> pd.DataFrame:
    """
    Perform alignment of epoch-year timestamps by detecting contiguous windows and applying shifts to the ones that have an RTC anchor.
    """
    windows = _detect_windows(df)

    if not windows:
        logger.debug("No windows detected, skipping alignment stage.")
        return df

    reversed_windows = list(reversed(windows))

    last_win: Window | None = None
    for i, win in enumerate(reversed_windows):
        if win.rtc_anchor_dt is None:
            if i == 0:
                logger.warning("Detected last window without RTC anchor, using HL Download event as anchor for guessing.", window=win)
                hl_download_rows = df[df["event_id"] == EventID.HL_DOWNLOAD].sort_values(by="datetime", ascending=False)
                last_row_idx = hl_download_rows.index[0]
                win.rtc_anchor_idx = last_row_idx
                win.rtc_anchor_dt = df.at[last_row_idx, "datetime"]
            else:
                logger.warning("Detected window without RTC anchor, using last known window's start as anchor for guessing.", window=win, last_window=last_win)
                win.rtc_anchor_idx = last_win.start_idx
                win.rtc_anchor_dt = df.at[last_win.start_idx, "datetime"]
        _shift_window(df, win)
        last_win = win

    markers = [EventID.RTC_RESET, EventID.MISS_LOGS, EventID.RTC_GUESS, EventID.RTC_MISS_START, EventID.RTC_MISS_END]

    for win in reversed_windows:
        if win.is_guessed:
            logger.info("Detected window with RTC anchor, adding synthetic RTC_GUESS event.", window=win)
            opens_with_marker = df.at[win.start_idx, "event_id"] in markers
            guess_idx = win.start_idx + 1 if opens_with_marker else win.start_idx
            guess_dt = df.at[guess_idx, "datetime"] - _TIMEDELTA_OFFSET_MILLIS
            guess = _make_synthetic_row(EventID.RTC_GUESS, _SENTINEL_VALUE, guess_dt, 0)
            df = _insert_row(df, guess_idx, guess)
            df = _increase_counter(df, guess_idx + 1)
        else:
            logger.info("Detected window without RTC anchor, adding synthetic RTC_MISS_START and RTC_MISS_END events.", window=win)
            opens_with_marker = df.at[win.start_idx, "event_id"] in markers
            start_idx = win.start_idx if win.start_idx > 0 and opens_with_marker else 0
            start_dt = df.at[start_idx, "datetime"] + _TIMEDELTA_OFFSET_MILLIS if start_idx > 0 else df.at[start_idx, "datetime"] - _TIMEDELTA_OFFSET_MILLIS
            start_counter = df.at[start_idx, "counter"] + 1 if start_idx > 0 else 0
            miss_start = _make_synthetic_row(EventID.RTC_MISS_START, _SENTINEL_VALUE, start_dt, start_counter)
            df = _insert_row(df, start_idx, miss_start, after=True) if start_idx > 0 else _insert_row(df, start_idx, miss_start)
            
            if start_idx == 0:
                df = _increase_counter(df, start_idx + 1)
            
            closes_with_marker = df.at[win.end_idx, "event_id"] in markers
            end_idx = win.end_idx + 1 if closes_with_marker else win.end_idx
            end_dt = df.at[end_idx, "datetime"] - _TIMEDELTA_OFFSET_MILLIS if end_idx < len(df) else df.at[end_idx - 1, "datetime"] + _TIMEDELTA_OFFSET_MILLIS
            end_counter = df.at[end_idx, "counter"] + 1 if end_idx < len(df) else df.at[end_idx - 1, "counter"] + 1
            miss_end = _make_synthetic_row(EventID.RTC_MISS_END, _SENTINEL_VALUE, end_dt, end_counter)
            df = _insert_row(df, end_idx, miss_end, after=True) if end_idx < len(df) else _insert_row(df, end_idx, miss_end)


    # row_offset = 0
    # for win in windows:

    #     if win.is_guessed:
    #         logger.info("Detected window with RTC anchor, adding synthetic RTC_GUESS event.", window=win)
    #         idx = win.start_idx + row_offset
    #         opens_with_marker = df.at[idx, "event_id"] in markers

    #         if opens_with_marker:
    #             anchor_dt = df.at[idx + 1, "datetime"] + _TIMEDELTA_OFFSET_MILLIS
    #             guess = _make_synthetic_row(EventID.RTC_GUESS, _SENTINEL_VALUE, anchor_dt, df.at[idx + 1, "counter"])
    #             df = _insert_row(df, win.start_idx + row_offset, guess, after=True)
    #             df = _increase_counter(df, win.start_idx + row_offset + 2)
    #         else:
    #             anchor_dt = df.at[idx, "datetime"] - _TIMEDELTA_OFFSET_MILLIS
    #             guess = _make_synthetic_row(EventID.RTC_GUESS, _SENTINEL_VALUE, anchor_dt, df.at[idx, "counter"])
    #             df = _insert_row(df, win.start_idx + row_offset, guess)
    #             df = _increase_counter(df, win.start_idx + row_offset + 1)

    #         row_offset += 1

    #     else:
    #         logger.info("Detected window without RTC anchor, adding synthetic RTC_MISS_START and RTC_MISS_END events.", window=win)

    #         start_idx = win.start_idx + row_offset - 1
    #         end_idx = win.end_idx + row_offset + 1

    #         opens_with_marker = df.at[start_idx + 1, "event_id"] in markers
    #         closes_with_marker = df.at[end_idx - 1, "event_id"] in markers

    #         if start_idx < 0:
    #             start_dt = df.at[0, "datetime"] - _TIMEDELTA_OFFSET_MILLIS
    #             miss_start = _make_synthetic_row(EventID.RTC_MISS_START, _SENTINEL_VALUE, start_dt, 0)
    #             df = _insert_row(df, 0, miss_start)
    #             df = _increase_counter(df, 1)
    #         else:
    #             start_dt = df.at[start_idx, "datetime"] + _TIMEDELTA_OFFSET_MILLIS
    #             start_counter = df.at[start_idx, "counter"] + 1
    #             miss_start = _make_synthetic_row(EventID.RTC_MISS_START, _SENTINEL_VALUE, start_dt, start_counter)
    #             df = _insert_row(df, start_idx, miss_start, after=True)
            
    #         row_offset += 1
    #         end_idx += 1
            
    #         if end_idx >= len(df):
    #             end_dt = df.at[len(df) - 1, "datetime"] + _TIMEDELTA_OFFSET_MILLIS
    #             end_counter = df.at[len(df) - 1, "counter"] + 1
    #             miss_end = _make_synthetic_row(EventID.RTC_MISS_END, _SENTINEL_VALUE, end_dt, end_counter)
    #             df = _insert_row(df, len(df) - 1, miss_end, after=True)
    #         else:
    #             end_dt = df.at[end_idx, "datetime"] - _TIMEDELTA_OFFSET_MILLIS
    #             miss_end = _make_synthetic_row(EventID.RTC_MISS_END, _SENTINEL_VALUE, end_dt, 0)
    #             df = _insert_row(df, end_idx, miss_end)
    #             df = _increase_counter(df, end_idx + 1)

    #         row_offset += 1


    for i, log in enumerate(df.itertuples(index=False)):
        logger.debug(
            "Post-alignment log entry.",
            index=i,
            counter=log.counter,
            datetime=log.datetime,
            event_id=log.event_id
        )


def _align_stage_v1(df: pd.DataFrame) -> pd.DataFrame:
    """
    Align epoch windows and insert synthetic markers.

    Windows are processed from the end of the dataframe so that inserting rows
    never invalidates the indices of windows that still have to be processed.
    """

    windows = _detect_windows(df)

    if not windows:
        logger.debug("No windows detected.")
        return df

    #
    # ---------------------------------------------------------------
    # First pass:
    # Guess anchors and shift timestamps.
    # ---------------------------------------------------------------
    #

    last_window: Window | None = None

    for i, win in enumerate(reversed(windows)):

        if win.rtc_anchor_dt is None:

            if i == 0:
                logger.warning(
                    "Last window has no RTC anchor. Using latest HL_DOWNLOAD."
                )

                hl = (
                    df[df.event_id == EventID.HL_DOWNLOAD]
                    .sort_values("datetime", ascending=False)
                    .iloc[0]
                )

                win.rtc_anchor_idx = hl.name
                win.rtc_anchor_dt = hl.datetime

            else:
                logger.warning(
                    "Window has no RTC anchor. Guessing from next window."
                )

                win.rtc_anchor_idx = last_window.start_idx
                win.rtc_anchor_dt = last_window.start_dt

        _shift_window(df, win)
        last_window = win

    #
    # ---------------------------------------------------------------
    # Second pass:
    # Insert sentinels.
    #
    # Again backwards -> indices never change for remaining windows.
    # ---------------------------------------------------------------
    #

    for win in reversed(windows):

        #
        # ===========================================================
        # RTC_GUESS
        # ===========================================================
        #

        if win.is_guessed:

            insert_idx = win.start_idx

            if (
                insert_idx > 0
                and df.at[insert_idx - 1, "event_id"] == EventID.RTC_RESET
            ):
                #
                # RTC_RESET
                # RTC_GUESS
                # first log
                #
                guess = _make_synthetic_row(
                    EventID.RTC_GUESS,
                    _SENTINEL_VALUE,
                    df.at[insert_idx, "datetime"],
                    df.at[insert_idx, "counter"],
                )

                df = _insert_row(df, insert_idx - 1, guess, after=True)

                _increase_counter(df, insert_idx + 1)

            else:
                #
                # RTC_GUESS
                # first log
                #
                guess = _make_synthetic_row(
                    EventID.RTC_GUESS,
                    _SENTINEL_VALUE,
                    df.at[insert_idx, "datetime"],
                    df.at[insert_idx, "counter"],
                )

                df = _insert_row(df, insert_idx, guess)

                _increase_counter(df, insert_idx + 1)

        #
        # ===========================================================
        # RTC_MISS_START / RTC_MISS_END
        # ===========================================================
        #

        else:

            #
            # ----- START -----
            #

            if win.start_idx == 0:

                start_dt = df.at[0, "datetime"]
                start_counter = 0

                miss_start = _make_synthetic_row(
                    EventID.RTC_MISS_START,
                    _SENTINEL_VALUE,
                    start_dt - _TIMEDELTA_OFFSET_MILLIS,
                    start_counter,
                )

                df = _insert_row(df, 0, miss_start)

                _increase_counter(df, 1)

            else:

                prev_idx = win.start_idx - 1

                miss_start = _make_synthetic_row(
                    EventID.RTC_MISS_START,
                    _SENTINEL_VALUE,
                    df.at[prev_idx, "datetime"] + _TIMEDELTA_OFFSET_MILLIS,
                    df.at[prev_idx, "counter"] + 1,
                )

                df = _insert_row(df, prev_idx, miss_start, after=True)

            #
            # Since we inserted BEFORE the window,
            # its end shifted by +1.
            #

            end_idx = win.end_idx + 1

            #
            # ----- END -----
            #

            if end_idx + 1 >= len(df):

                miss_end = _make_synthetic_row(
                    EventID.RTC_MISS_END,
                    _SENTINEL_VALUE,
                    df.at[end_idx, "datetime"] + _TIMEDELTA_OFFSET_MILLIS,
                    df.at[end_idx, "counter"] + 1,
                )

                df = _insert_row(df, end_idx, miss_end, after=True)

            else:

                next_idx = end_idx + 1

                miss_end = _make_synthetic_row(
                    EventID.RTC_MISS_END,
                    _SENTINEL_VALUE,
                    df.at[next_idx, "datetime"] - _TIMEDELTA_OFFSET_MILLIS,
                    df.at[end_idx, "counter"] + 1, 
                )

                df = _insert_row(df, next_idx, miss_end)
    
    for i, log in enumerate(df.itertuples(index=False)):
        logger.debug(
            "Post-alignment log entry.",
            index=i,
            counter=log.counter,
            datetime=log.datetime,
            event_id=log.event_id
        )

    return df



def clean_timestamps(
        df: pd.DataFrame
) -> tuple[pd.DataFrame | None, int | None]:

    if df.empty:
        return df.copy(), None

    df, parse_success = _parse_datetime_stage(df)

    if not parse_success:
        logger.error("Failed to parse datetime values in all rows.")
        return None, None

    rollover_detected, rollover_head_idx = _rollover_stage(df)

    if rollover_detected:
        logger.info("Traslating dataframe to account for rollover.", rollover_head_index=rollover_head_idx)
        df =pd.concat(
            [
                df.iloc[rollover_head_idx + 1:],
                df.iloc[:rollover_head_idx + 1],
            ],
            ignore_index=True,
        )

    df = _normalize_stage(df)
    df = _align_stage_v1(df)

    exit(0)

    return df, rollover_head_idx
