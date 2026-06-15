from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from common.logging import get_logger

logger = get_logger(__name__)


def build_engine(db_url: str, verbose: bool = False):
    """
    Create a SQLAlchemy engine using the provided database URL.

    Args:
        db_url (str): The database connection URL.
        verbose (bool): If True, log all emitted SQL. Only pass True at DEBUG level.
    """
    try:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,  # Enable connection health checks
            pool_size=5,
            max_overflow=5,
            echo=verbose,
        )
        return engine
    except Exception as e:
        logger.error("Failed to create database engine", db_url=db_url, error=str(e))
        raise

def init_db(db_url: str, log_level: str = "INFO") -> sessionmaker:
    """
    Initialize the database connection and returns a session factory.

    Args:
        db_url (str): The database connection URL.
        log_level (str): Application log level; enables SQL verbose at DEBUG level.
    """
    verbose = log_level.upper() == "DEBUG"
    engine = build_engine(db_url, verbose=verbose)

    logger.info("Testing database connectivity...")
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    logger.info("Database connectivity OK")

    return sessionmaker(bind=engine, autocommit=False, autoflush=False)

@contextmanager
def get_db_session(session_factory: sessionmaker) -> Generator[Session, None, None]:
    """
    Context manager that yields a SQLAlchemy session and ensures proper commit/rollback and cleanup.
    """
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error("Database session error", error=str(e))
        session.rollback()
        raise
    finally:
        session.close()