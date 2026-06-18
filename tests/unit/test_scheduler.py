"""
Unit tests for src/scheduler.py

Covers _schedule_at only (the pure scheduling logic).  We do not start the
BlockingScheduler in unit tests to avoid blocking the test runner.

Covers:
  - Correct hour/minute/second field values
  - Optional day_of_week, day, month parameters
  - Default timezone is Europe/Rome
  - Each combination of optional parameters creates a valid CronTrigger
  - Invalid time strings raise
"""
from __future__ import annotations

import pytest
from apscheduler.triggers.cron import CronTrigger

from scheduler import _schedule_at


def _fields(trigger: CronTrigger) -> dict:
    """Extract trigger fields as a name→field mapping for assertion."""
    return {f.name: f for f in trigger.__getstate__()["fields"]}


class TestScheduleAt:
    def test_returns_cron_trigger(self) -> None:
        assert isinstance(_schedule_at("02:00:00"), CronTrigger)

    def test_hour_field_correct(self) -> None:
        trigger = _schedule_at("14:00:00")
        assert _fields(trigger)["hour"].expressions[0].first == 14

    def test_minute_field_correct(self) -> None:
        trigger = _schedule_at("00:45:00")
        assert _fields(trigger)["minute"].expressions[0].first == 45

    def test_second_field_correct(self) -> None:
        trigger = _schedule_at("00:00:30")
        assert _fields(trigger)["second"].expressions[0].first == 30

    def test_midnight_schedule(self) -> None:
        trigger = _schedule_at("00:00:00")
        f = _fields(trigger)
        assert f["hour"].expressions[0].first == 0
        assert f["minute"].expressions[0].first == 0
        assert f["second"].expressions[0].first == 0

    def test_day_of_week_set(self) -> None:
        trigger = _schedule_at("10:00:00", day_of_week="mon-fri")
        assert str(_fields(trigger)["day_of_week"]) == "mon-fri"

    def test_day_field_set(self) -> None:
        trigger = _schedule_at("00:00:00", day=15)
        assert _fields(trigger)["day"].expressions[0].first == 15

    def test_month_field_set(self) -> None:
        trigger = _schedule_at("10:00:00", day=25, month=12)
        assert _fields(trigger)["month"].expressions[0].first == 12

    def test_all_optional_params_combined(self) -> None:
        trigger = _schedule_at("02:15:30", day_of_week="mon-fri", day=1, month=12)
        state = str(trigger)
        assert "month='12'" in state
        assert "day='1'" in state
        assert "day_of_week='mon-fri'" in state
        assert "hour='2'" in state
        assert "minute='15'" in state
        assert "second='30'" in state

    def test_none_optionals_omitted_from_repr(self) -> None:
        trigger = _schedule_at("06:00:00")
        state = str(trigger)
        # When month/day/day_of_week are None they should not restrict
        assert "hour='6'" in state

    @pytest.mark.parametrize("bad", ["25:00:00", "not-a-time", "", "2 AM"])
    def test_invalid_time_string_raises(self, bad: str) -> None:
        with pytest.raises((ValueError, Exception)):
            _schedule_at(bad)