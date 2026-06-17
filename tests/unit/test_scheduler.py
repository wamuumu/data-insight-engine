from __future__ import annotations

from apscheduler.triggers.cron import CronTrigger

from scheduler import _schedule_at


def test_schedule_at_builds_cron_trigger():
    trigger = _schedule_at("02:15:30", day_of_week="mon-fri", day=1, month=12)
    state = trigger.__getstate__()
    fields = {field.name: field for field in state["fields"]}

    assert isinstance(trigger, CronTrigger)
    assert str(trigger) == "cron[month='12', day='1', day_of_week='mon-fri', hour='2', minute='15', second='30']"
    assert fields["month"].expressions[0].first == 12
    assert fields["day"].expressions[0].first == 1
    assert str(fields["day_of_week"]) == "mon-fri"


def test_schedule_at_uses_time_components():
    trigger = _schedule_at("14:05:06")
    state = trigger.__getstate__()
    fields = {field.name: field for field in state["fields"]}

    assert fields["hour"].expressions[0].first == 14
    assert fields["minute"].expressions[0].first == 5
    assert fields["second"].expressions[0].first == 6