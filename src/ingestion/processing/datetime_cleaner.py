from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import NamedTuple

import pandas as pd

from common.constants import (
    RTC_SET_EVENT_ID,
    RTC_RESET_EVENT_ID,
    RTC_GUESSED_EVENT_ID,
    SWITCH_ON_EVENT_ID,
    SENTINEL_VALUE,
    EPOCH_YEAR,
)
from common.logging import get_logger

logger = get_logger(__name__)


class Window(NamedTuple):
    """A contiguous slice of logs identifying the timestamps that need to be shifted by some delta."""

    start_idx: int
    start_dt: datetime
    end_idx: int
    end_dt: datetime
    rtc_anchor_idx: int
    rtc_anchor_dt: datetime
    is_guessed: bool = False


# --- Helpers for timestamp cleaning and alignment ---


def _make_synthetic_row(event_id: int, value: int | str, dt: datetime) -> dict:
    """Build a dict for a single synthetic row (RTC_RESET or RTC_GUESSED)."""
    return {
        "counter": -1 if event_id == RTC_RESET_EVENT_ID else -2,
        "event_id": event_id,
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
    windows: list[Window] = []

    for i in range(len(df)):
        row = df.iloc[i]

        if row["event_id"] != RTC_SET_EVENT_ID:
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

            if df.at[j, "event_id"] == RTC_RESET_EVENT_ID:
                start_idx = j
                start_dt = dt
                break

            if dt.year == EPOCH_YEAR:
                continue

            if dt.date() != end_dt.date():
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
            last_win_is_epoch = last_win.start_dt == datetime(
                EPOCH_YEAR, 1, 1, 0, 0, 0, 0
            )
            current_win_is_epoch = win.start_dt == datetime(
                EPOCH_YEAR, 1, 1, 0, 0, 0, 0
            )

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
        if df.at[i, "event_id"] != RTC_RESET_EVENT_ID:
            continue

        already_covered = any(win.start_idx <= i <= win.end_idx for win in merged)
        if already_covered:
            continue

        # Walk forward to find the end of this epoch block
        block_end_idx = i
        for j in range(i + 1, len(df)):
            if (
                df.at[j, "event_id"] == RTC_RESET_EVENT_ID
                or df.at[j, "datetime"].year != EPOCH_YEAR
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
                rtc_anchor_idx=-1,
                rtc_anchor_dt=datetime.min,
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
    delta = window.rtc_anchor_dt - df.at[window.end_idx, "datetime"]

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
            if df.at[row_idx, "event_id"] == RTC_RESET_EVENT_ID:
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
            RTC_GUESSED_EVENT_ID,
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


def _parse_stage(df: pd.DataFrame) -> pd.DataFrame:
    df = copy.deepcopy(df).reset_index(drop=True)

    df["datetime"] = pd.to_datetime(
        df["date"].astype(str) + " " + df["time"].astype(str),
        dayfirst=True,
    )

    df.drop(columns=["date", "time", "description"], inplace=True)

    return df


def _normalize_stage(df: pd.DataFrame) -> pd.DataFrame:
    i = 1

    while i < len(df):
        prev_dt = df.at[i - 1, "datetime"]
        curr_dt = df.at[i, "datetime"]

        # --- epoch detection ---
        if curr_dt == datetime(EPOCH_YEAR, 1, 1, 0, 0, 0, 0):
            logger.info(
                "Detected epoch timestamp, inserting synthetic RTC_RESET event.",
                index=i,
            )
            reset = _make_synthetic_row(RTC_RESET_EVENT_ID, SENTINEL_VALUE, curr_dt)
            df = _insert_row(df, i, reset)
            i += 2
            continue

        # --- backward jump within epoch ---
        if (
            prev_dt.year == EPOCH_YEAR
            and curr_dt.year == EPOCH_YEAR
            and curr_dt < prev_dt
            and (prev_dt - curr_dt) > timedelta(seconds=1)
        ):
            logger.info(
                "Detected backward jump within epoch, inserting synthetic RTC_RESET event.",
                index=i,
            )
            reset = _make_synthetic_row(RTC_RESET_EVENT_ID, SENTINEL_VALUE, curr_dt)
            df = _insert_row(df, i, reset)
            i += 2
            continue

        # --- SWITCH_ON correction ---
        if (
            curr_dt.replace(microsecond=0) == prev_dt.replace(microsecond=0)
            and curr_dt < prev_dt
        ):
            if df.at[i, "event_id"] == SWITCH_ON_EVENT_ID:
                logger.debug(
                    "Detected SWITCH_ON event with backward timestamp, adjusting.",
                    index=i,
                )
                df.at[i, "datetime"] = prev_dt + timedelta(milliseconds=1)
            else:
                logger.warning(
                    "Detected backward timestamp without SWITCH_ON event, skipping correction.",
                    index=i,
                )

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

            # single epoch window
            if len(run) == 1:
                if win.rtc_anchor_idx == -1:
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
                    (w for w in reversed(run) if w.rtc_anchor_idx != -1), None
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
                            rtc_anchor_idx=w.rtc_anchor_idx + offset
                            if w.rtc_anchor_idx != -1
                            else -1,
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


def _rollover_stage(df: pd.DataFrame) -> tuple[pd.DataFrame, int | None]:
    key_cols = ["datetime", "counter"]

    sorted_df = df.sort_values(key_cols).reset_index(drop=True)

    first_real = (
        df[df["counter"] >= 0].iloc[0] if not df[df["counter"] >= 0].empty else None
    )

    rollover_idx: int | None = None

    if first_real is not None:
        first_dt = first_real["datetime"]
        first_counter = first_real["counter"]

        mask = (
            (sorted_df["datetime"] == first_dt)
            & (sorted_df["counter"] == first_counter)
            & (sorted_df["counter"] >= 0)
        )
        idxs = sorted_df.index[mask]
        rollover_idx = int(idxs[0]) if len(idxs) > 0 and idxs[0] > 0 else None

    sorted_df["rollover"] = False

    if rollover_idx is not None:
        logger.info(
            "Detected rollover in logs, marking rows after rollover index.",
            rollover_index=rollover_idx,
        )
        sorted_df.loc[rollover_idx:, "rollover"] = True
    else:
        logger.debug("No rollover detected in logs.")

    return sorted_df, rollover_idx


def clean_timestamps(df: pd.DataFrame) -> tuple[pd.DataFrame, int | None]:

    if df.empty:
        return df.copy(), None

    df = _parse_stage(df)
    df = _normalize_stage(df)
    df = _align_stage(df)

    df, rollover_idx = _rollover_stage(df)

    return df, rollover_idx
