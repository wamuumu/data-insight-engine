import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base
# Import models to register them with the Base class
from db.models.history import HistoryLog
from db.models.raw_data import RawData

logger = logging.getLogger(__name__)


def build_engine(db_url: str):
    """
    Create a SQLAlchemy engine using the provided database URL.
    """
    try:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,  # Enable connection health checks
            pool_size=5,
            max_overflow=10,
            echo=True,
        )
        return engine
    except Exception as e:
        logger.error(f"Error creating database engine: {e}")
        raise

def init_db(db_url: str) -> sessionmaker:
    """
    Initialize the database connection and create tables if they do not exist.
    """
    engine = build_engine(db_url)
    
    logger.info("Running database connectivity test...")
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    logger.info("Database connectivity OK.")

    logger.info("Creating database tables if they do not exist...")
    Base.metadata.create_all(engine)
    logger.info("Database initialization complete.")

    return sessionmaker(bind=engine, autocommit=False, autoflush=False)

@contextmanager
def get_db_session(session_factory: sessionmaker) -> Generator[Session, None, None]:
    """
    Context manager for obtaining a database session.
    """
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"Database session error: {e}")
        session.rollback()
        raise
    finally:
        session.close()