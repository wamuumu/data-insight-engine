from datetime import time
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from common.logging import get_logger
from ingestion.pipeline import IngestionPipeline

logger = get_logger(__name__)


def build_scheduler(
    pipeline: IngestionPipeline,
    time_str: str,
    day_of_week: str | None = None,
    day: int | None = None,
    month: int | None = None,
) -> BlockingScheduler:
    """
    Build and return a configured BlockingScheduler that runs the given pipeline according to the provided cron expression.

    Args:
        pipeline (IngestionPipeline): The data ingestion pipeline to be scheduled.
        time_str (str): A time string defining the schedule for the pipeline execution.
    """

    cron_trigger = _schedule_at(
        time_str, day_of_week=day_of_week, day=day, month=month, timezone="Europe/Rome"
    )

    scheduler = BlockingScheduler(timezone="Europe/Rome")

    scheduler.add_job(
        func=pipeline.run,
        trigger=cron_trigger,
        id="ingest_job",
        name="Scheduled Ingestion Job",
        max_instances=1,  # never allow concurrent runs
        coalesce=True,  # if missed, fire only once
        misfire_grace_time=300,  # 5 minutes
    )

    scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)

    logger.info("Scheduler configured", cron_expression=str(cron_trigger))
    return scheduler


def _schedule_at(
    time_str: str,
    *,
    day_of_week: str | None = None,
    day: int | None = None,
    month: int | None = None,
    timezone: str = "Europe/Rome",
) -> CronTrigger:
    """
    Build a CronTrigger based on the provided time string and optional parameters.

    Examples:
        _schedule_at("02:00:00") # every day at 2 AM (Europe/Rome timezone)
        _schedule_at("14:30:00", day_of_week="mon-fri") # every weekday at 2:30 PM (Europe/Rome timezone)
        _schedule_at("00:00:00", day=1) # every first day of the month at midnight (Europe/Rome timezone)
        _schedule_at("10:00:00", day=25, month=12) # every Christmas at 10 AM (Europe/Rome timezone)
    """
    t = time.fromisoformat(time_str)

    return CronTrigger(
        month=month,
        day=day,
        day_of_week=day_of_week,
        hour=t.hour,
        minute=t.minute,
        second=t.second,
        timezone=ZoneInfo(timezone),
    )


def _on_job_executed(event):
    logger.info("Scheduled job completed successfully", job_id=event.job_id)


def _on_job_error(event):
    logger.error(
        "Scheduled job failed", job_id=event.job_id, error=str(event.exception)
    )
