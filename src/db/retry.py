from __future__ import annotations

from time import monotonic, sleep
from typing import Callable, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from common.logging import get_logger
from config import load_settings
from db.session import get_db_session

logger = get_logger(__name__)
settings = load_settings()

T = TypeVar("T")


class DbRetryTimeout(RuntimeError):
    """The retry deadline was reached before the operation succeeded."""


def with_db_retry(
    session_factory: sessionmaker,
    fn: Callable[[Session], T],
    *,
    op_name: str = "db_operation",
) -> T:
    """
    Run a database operation with automatic retry on failure, using exponential backoff.

    Args:
        session_factory: SQLAlchemy sessionmaker to create new sessions.
        fn: function to call with a fresh session.
        op_name: short label used in log messages only.

    Returns:
        The return value of the provided function `fn`.

    Raises:
        DbRetryTimeout: deadline reached before a successful attempt.
    """
    deadline = monotonic() + settings.db_retry_timeout

    attempt = 0
    while True:
        try:
            with get_db_session(session_factory) as session:
                return fn(session)
        except Exception as e:
            delay = min(
                settings.db_retry_max_delay,
                settings.db_retry_initial_delay * (2**attempt),
            )
            logger.warning(
                f"{op_name} failed, will retry after delay.",
                attempt=attempt,
                delay=delay,
                error=str(e),
            )

            if monotonic() + delay >= deadline:
                raise DbRetryTimeout(op_name) from e

            sleep(delay)
            attempt += 1