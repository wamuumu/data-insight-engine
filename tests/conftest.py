from __future__ import annotations

import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

os.environ.setdefault("DB_URL", "postgresql://postgres:postgres@localhost:5432/data_insight_test")
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "postgres")
os.environ.setdefault("DB_NAME", "data_insight_test")
os.environ.setdefault("METRICS_PORT", "8000")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("LOG_FORMAT", "console")
os.environ.setdefault("DATA_ROOT", "data")
os.environ.setdefault("PARQUET_BATCH_SIZE", "100")
os.environ.setdefault("DB_BATCH_SIZE", "100")
os.environ.setdefault("WORKERS", "1")
os.environ.setdefault("DB_RETRY_ATTEMPTS", "1")
os.environ.setdefault("DB_RETRY_INITIAL_DELAY", "0.01")
os.environ.setdefault("DB_RETRY_MAX_DELAY", "0.01")
os.environ.setdefault("FILE_RETRY_TIMEOUT", "30")
os.environ.setdefault("MAX_BATCH_SPLIT_DEPTH", "2")

import pytest
from sqlalchemy.orm import sessionmaker

from db.models.base import BaseModel
from db.session import build_engine, get_db_session

@pytest.fixture(scope="session")
def pg_url():
    try:
        from testcontainers.postgres import PostgresContainer
        with PostgresContainer("postgres:17") as pg:
            yield pg.get_connection_url()
    except Exception:
        # Fallback to environment variable or default
        yield "postgresql://postgres:postgres@localhost:5432/test_db"

@pytest.fixture(scope="session")
def db_engine(pg_url):
    engine = build_engine(pg_url, echo=False)
    BaseModel.metadata.create_all(engine)
    yield engine
    BaseModel.metadata.drop_all(engine)
    engine.dispose()

@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)

@pytest.fixture
def db_session(session_factory):
    with get_db_session(session_factory) as session:
        yield session    