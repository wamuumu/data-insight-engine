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
    rtc_anchor_idx: int | None = None
    rtc_anchor_dt: datetime | None = None
    is_guessed: bool = False

    @property
    def is_epoch(self) -> bool:
        return self.start_dt.year == _EPOCH_YEAR
    
    @property
    def is_epoch_start(self) -> bool:
        return self.start_dt == datetime(_EPOCH_YEAR, 1, 1, 0, 0, 0, 0)

# --- Helpers for timestamp cleaning and alignment ---


def _make_synthetic_row(event_id: EventID, value: int, dt: datetime, counter: int | None = None) -> dict:
    """Build a dict for a single synthetic row (RTC_RESET or RTC_GUESSED)."""
    return {
        "counter": counter,
        "date": dt.date().strftime("%d/%m/%Y"),
        "time": dt.time().strftime("%H:%M:%S.%f")[:-3],
        "event_id": event_id,
        "description": event_id.name.replace("_", " "),
        "value": value,
        "datetime": dt,
    }


def _insert_row(df: pd.DataFrame, index: int, row: dict) -> pd.DataFrame:
    """
    Insert a single row dictionary before positional index and return a clean DataFrame.
    """
    return pd.concat(
        [
            df.iloc[:index],
            pd.DataFrame(
                [row], columns=df.columns
            ),  # Dynamically adapt to current df columns
            df.iloc[index:],
        ],
        ignore_index=True,
    )


def _detect_windows(df: pd.DataFrame) -> list[Window]:
    """
    Detect contiguous windows of invalid epoch-year logs.

    Args:
        df: DataFrame containing the log records.
    
    Returns:
        A list of Window objects representing the detected windows.
    """
    windows: list[Window] = []

    start_idx: int | None = None
    end_idx: int | None = None
    start_dt: datetime | None = None
    end_dt: datetime | None = None

    #TODO: check this logic

    i = 0
    while i < len(df):
        if df.at[i, "event_id"] == EventID.RTC_SET:
            last_win = windows[-1] if windows else None
            if last_win and last_win.end_idx >= i and last_win.rtc_anchor_idx is None:
                last_win.rtc_anchor_idx = i
                last_win.rtc_anchor_dt = df.at[i, "datetime"]    

        if df.at[i, "datetime"].year != _EPOCH_YEAR:
            i += 1
            continue
        
        start_idx = i
        start_dt = df.at[i, "datetime"]
        
        end_idx = i
        while (
            end_idx + 1 < len(df)
            and df.at[end_idx + 1, "datetime"].year == _EPOCH_YEAR
            and df.at[end_idx + 1, "event_id"] != EventID.RTC_RESET
        ):
            end_idx += 1
            end_dt = df.at[end_idx, "datetime"]
        
        windows.append(
            Window(
                start_idx=start_idx,
                end_idx=end_idx,
                start_dt=start_dt,
                end_dt=end_dt
            )
        )
        i = end_idx + 1
        

            

def _detect_windows(df: pd.DataFrame) -> list[Window]:
    windows: list[Window] = []

    for i in range(len(df)):
        row = df.iloc[i]

        if row["event_id"] != EventID.RTC_SET:
            continue

        rtc_idx = i
        rtc_dt = row["datetime"]

        start_idx: int | None = None
        end_idx: int | None = None
        start_dt: datetime | None = None
        end_dt: datetime | None = None

        for j in range(i - 1, -1, -1):
            dt = df.at[j, "datetime"]

            if end_dt is None:
                end_idx = j
                end_dt = dt
                continue

            if df.at[j, "event_id"] == EventID.RTC_RESET:
                start_idx = j
                start_dt = dt
                break
            
            if dt.year != _EPOCH_YEAR:
                start_idx = j + 1
                start_dt = df.at[start_idx, "datetime"]
                break

        if start_dt is not None and end_dt is None:
            end_idx = len(df) - 1
            end_dt = df.at[end_idx, "datetime"]

        if end_dt is not None and start_dt is None:
            start_idx = 0
            start_dt = df.at[start_idx, "datetime"]

        windows.append(
            Window(
                start_idx=start_idx,
                end_idx=end_idx,
                start_dt=start_dt,
                end_dt=end_dt,
                rtc_anchor_idx=rtc_idx,
                rtc_anchor_dt=rtc_dt,
            )
        )

    return _merge_overlapping_windows(df, windows)


def _merge_overlapping_windows(df: pd.DataFrame, windows: list[Window]) -> list[Window]:
    """
    Merge overlapping windows. Two windows overlap if the start of one is
    before or at the end of the other.

    Also detects uncovered epoch blocks (rows with epoch-year timestamps not
    spanned by any merged window) and appends them as guessed windows.
    """
    if not windows:
        return []

    merged: list[Window] = []
    for win in windows:
        if not merged:
            merged.append(win)
            continue

        last_win = merged[-1]

        if win.start_idx <= last_win.end_idx:
            last_win_is_epoch = last_win.is_epoch_start
            current_win_is_epoch = win.is_epoch_start

            if last_win_is_epoch and current_win_is_epoch:
                # Keep consecutive epoch windows separate so guessing works correctly
                merged.append(win)
            else:
                new_start_idx = min(last_win.start_idx, win.start_idx)
                new_end_idx = max(last_win.end_idx, win.end_idx)
                new_start_dt = min(last_win.start_dt, win.start_dt)
                new_end_dt = max(last_win.end_dt, win.end_dt)

                merged[-1] = Window(
                    start_idx=new_start_idx,
                    end_idx=new_end_idx,
                    start_dt=new_start_dt,
                    end_dt=new_end_dt,
                    rtc_anchor_idx=last_win.rtc_anchor_idx,
                    rtc_anchor_dt=last_win.rtc_anchor_dt,
                )
        else:
            merged.append(win)

    uncovered: list[Window] = []

    for i in range(len(df)):
        if df.at[i, "event_id"] != EventID.RTC_RESET:
            continue

        already_covered = any(win.start_idx <= i <= win.end_idx for win in merged)
        if already_covered:
            continue

        # Walk forward to find the end of this epoch block
        block_end_idx = i
        for j in range(i + 1, len(df)):
            if (
                df.at[j, "event_id"] == EventID.RTC_RESET
                or df.at[j, "datetime"].year != _EPOCH_YEAR
            ):
                block_end_idx = j - 1
                break
        # for…else: loop exhausted without break → block runs to EOF
        else:
            block_end_idx = len(df) - 1

        uncovered.append(
            Window(
                start_idx=i,
                end_idx=block_end_idx,
                start_dt=df.at[i, "datetime"],
                end_dt=df.at[block_end_idx, "datetime"],
                rtc_anchor_idx=None,
                rtc_anchor_dt=None,
                is_guessed=True,
            )
        )

    if uncovered:
        logger.warning(
            "Detected uncovered windows that will be guessed.",
            uncovered_windows=uncovered,
        )
        merged = sorted(merged + uncovered, key=lambda w: w.start_idx)

    return merged


def _shift_window(df: pd.DataFrame, window: Window):
    """Shift every row in [window.start_idx, window.end_idx] by the delta
    computed from the distance between the window's last row and its RTC anchor."""
    anchor_dt = window.rtc_anchor_dt
    last_dt = df.at[window.end_idx, "datetime"]

    if anchor_dt < last_dt:
        logger.warning(
            "RTC anchor is earlier than last row in window, skipping shift.",
            window=window,
        )
        return
    
    delta = anchor_dt - last_dt

    for i in range(window.start_idx, window.end_idx + 1):
        df.at[i, "datetime"] = df.at[i, "datetime"] + delta


def _guess_epoch_windows(
    df: pd.DataFrame,
    epoch_windows: list[Window],
) -> tuple[pd.DataFrame, int]:
    """
    Iteratively shift and annotate orphan epoch windows by guessing their
    anchor from the next known window.

    Returns the (possibly enlarged) DataFrame and the total number of rows inserted.
    """
    if len(epoch_windows) < 2:
        return df, 0

    inserted_rows = 0

    # Walk backwards so each guessed window can use the already-corrected one after it
    for i in range(len(epoch_windows) - 2, -1, -1):
        current = epoch_windows[i]
        next_window = epoch_windows[i + 1]
        guess_depth = len(epoch_windows) - i - 1

        current_start = current.start_idx + inserted_rows
        current_end = current.end_idx + inserted_rows
        next_start = next_window.start_idx + inserted_rows
        next_end = next_window.end_idx + inserted_rows

        # Find the first non-RTC_RESET timestamp in the next window
        guessed_anchor_dt = None
        for row_idx in range(next_start, next_end + 1):
            if df.at[row_idx, "event_id"] == EventID.RTC_RESET:
                continue

            guessed_anchor_dt = df.at[row_idx, "datetime"]
            break

        if guessed_anchor_dt is None:
            logger.warning(
                "Could not find a valid datetime to guess for epoch window, skipping.",
                current_window=current,
                next_window=next_window,
            )
            continue

        _shift_window(
            df,
            Window(
                start_idx=current_start,
                start_dt=current.start_dt,
                end_idx=current_end,
                end_dt=current.end_dt,
                rtc_anchor_idx=next_start,
                rtc_anchor_dt=guessed_anchor_dt,
                is_guessed=True,
            ),
        )

        guessed_row = _make_synthetic_row(
            EventID.GUESS_DATA,
            guess_depth,
            guessed_anchor_dt,
        )

        df = _insert_row(df, current_end + 1, guessed_row)

        logger.debug(
            "Inserted RTC GUESSED event.",
            index=current_end + 1,
            guessed_anchor_dt=guessed_anchor_dt,
            guess_depth=guess_depth,
        )

        inserted_rows += 1

    return df, inserted_rows


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
        
        # --- epoch normalization ---
        if (
            prev.datetime.year == _EPOCH_YEAR 
            and curr.datetime.year == _EPOCH_YEAR 
            and curr.datetime < prev.datetime
        ): 

            # --- backward jump within epoch ---
            if (prev.datetime - curr.datetime) > _TIMEDELTA_OFFSET_SECOND:
                logger.info(
                    "Detected backward jump within epoch, inserting synthetic RTC_RESET event.",
                    index=i,
                )
                reset = _make_synthetic_row(EventID.RTC_RESET, _SENTINEL_VALUE, curr.datetime - _TIMEDELTA_OFFSET_MILLIS)
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
            miss = _make_synthetic_row(EventID.MISS_LOGS, curr.counter, curr.datetime - _TIMEDELTA_OFFSET_MILLIS)
            df = _insert_row(df, i, miss)
            i += 2
            continue

        i += 1

    return df


def _align_stage(df: pd.DataFrame) -> pd.DataFrame:
    windows = _detect_windows(df)

    if not windows:
        logger.debug("No windows detected, skipping alignment stage.")
        return df

    offset = 0
    i = 0

    while i < len(windows):
        win = windows[i]

        if win.is_epoch:
            run: list[Window] = [win]
            j = i + 1

            while (
                j < len(windows)
                and windows[j].is_epoch
                and windows[j].start_idx == windows[j - 1].end_idx + 1
            ):
                run.append(windows[j])
                j += 1

            # single epoch window
            if len(run) == 1:
                if win.rtc_anchor_idx is None:
                    logger.warning(
                        "Detected single epoch window without RTC anchor, skipping correction.",
                        window=win,
                    )
                else:
                    _shift_window(
                        df,
                        Window(
                            start_idx=win.start_idx + offset,
                            start_dt=win.start_dt,
                            end_idx=win.end_idx + offset,
                            end_dt=win.end_dt,
                            rtc_anchor_idx=win.rtc_anchor_idx + offset,
                            rtc_anchor_dt=win.rtc_anchor_dt,
                            is_guessed=win.is_guessed,
                        ),
                    )
            else:
                # Multiple consecutive epoch windows — apply guessing
                anchor = next(
                    (w for w in reversed(run) if w.rtc_anchor_idx is not None), None
                )

                if anchor:
                    logger.warning(
                        "Detected multiple consecutive epoch windows, guessing will be applied.",
                        windows=run,
                    )
                    _shift_window(
                        df,
                        Window(
                            start_idx=anchor.start_idx + offset,
                            start_dt=anchor.start_dt,
                            end_idx=anchor.end_idx + offset,
                            end_dt=anchor.end_dt,
                            rtc_anchor_idx=anchor.rtc_anchor_idx + offset,
                            rtc_anchor_dt=anchor.rtc_anchor_dt,
                            is_guessed=anchor.is_guessed,
                        ),
                    )

                    adjusted_run = [
                        Window(
                            start_idx=w.start_idx + offset,
                            start_dt=w.start_dt,
                            end_idx=w.end_idx + offset,
                            end_dt=w.end_dt,
                            rtc_anchor_idx=w.rtc_anchor_idx + offset if w.rtc_anchor_idx is not None else None,
                            rtc_anchor_dt=w.rtc_anchor_dt,
                            is_guessed=w.is_guessed,
                        )
                        for w in run
                    ]
                    df, inserted = _guess_epoch_windows(df, adjusted_run)
                    offset += inserted
                else:
                    logger.warning(
                        "Detected multiple consecutive epoch windows without RTC anchor, skipping correction.",
                        windows=run,
                    )

            i = j

        else:
            logger.debug("Detected non-epoch window, applying shift.", window=win)
            _shift_window(
                df,
                Window(
                    start_idx=win.start_idx + offset,
                    start_dt=win.start_dt,
                    end_idx=win.end_idx + offset,
                    end_dt=win.end_dt,
                    rtc_anchor_idx=win.rtc_anchor_idx + offset,
                    rtc_anchor_dt=win.rtc_anchor_dt,
                    is_guessed=win.is_guessed,
                ),
            )
            i += 1

    return df


def _validate_stage(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """
    Validate that the DataFrame has no backward jumps in timestamps and that
    all epoch-year timestamps are covered by a window.
    """
    remaining_epoch = df[df["datetime"].dt.year == _EPOCH_YEAR]

    if not remaining_epoch.empty:
        dropped_count = len(remaining_epoch)
        logger.warning(
            "Dropping unresolved epoch-year rows (no RTC_SET event found).",
            dropped_count=dropped_count,
        )
        df = df[df["datetime"].dt.year != _EPOCH_YEAR].reset_index(drop=True)
    
    backward_jumps = df[df["datetime"].diff() < timedelta(0)]

    if not backward_jumps.empty:
        logger.error(
            "Validation failed: backward jumps in timestamps detected.",
            backward_jump_rows=backward_jumps,
        )
        return df, False
    
    logger.info("Validation passed successfully.")
    return df, True
            

def clean_timestamps(
        df: pd.DataFrame
) -> tuple[pd.DataFrame | None, int | None]:

    if df.empty:
        return df.copy(), None

    df, parse_success = _parse_datetime_stage(df)

    if not parse_success:
        logger.error("Failed to parse datetime values in all rows.")
        return None, None
    
    initial_len = len(df)

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
    # df = _align_stage(df)
    
    inserted_count = len(df) - initial_len

    return df, rollover_head_idx
