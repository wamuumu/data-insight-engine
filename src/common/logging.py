import logging
import sys
from datetime import datetime
from pathlib import Path

import structlog

_RUN_TIMESTAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)  # Timestamp for the current run, used in log file naming
_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_FILE = _LOG_DIR / f"app_{_RUN_TIMESTAMP}.log"


def setup_logging(log_level: str, log_format: str):
    """
    Configure structured JSON-formatted logging for the application.
    """
    log_level_int = getattr(logging, log_level.upper(), logging.INFO)

    renderer = (
        structlog.processors.JSONRenderer()
        if log_format.strip().lower() == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    def uppercase_log_level(_, __, event_dict):
        for key in ("level", "levelname"):
            if key in event_dict and isinstance(event_dict[key], str):
                event_dict[key] = event_dict[key].upper()
        return event_dict

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        uppercase_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [stdout_handler]

    # If not running inside a container mounting the logs directory, ensure it exists before trying to write log files
    if not _LOG_DIR.exists():
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8", delay=True)
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)

    root_logger = logging.getLogger()
    root_logger.handlers = []
    for handler in handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(log_level_int)

    if log_level_int > logging.DEBUG:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
        logging.getLogger("apscheduler").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger."""
    return structlog.get_logger(name)
