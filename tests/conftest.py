"""
Shared pytest fixtures for the data-insight-engine test suite.

Fixtures are scoped deliberately:
  - session-scoped: expensive one-time setup (DB engine, schema creation).
  - function-scoped: per-test isolation (sessions, repositories).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Path bootstrap ──────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from sqlalchemy.orm import sessionmaker

from db.models.base import BaseModel
from db.session import build_engine, get_db_session

# ── Minimal env vars so Settings() doesn't crash during collection ──────────
_TEST_DB_URL = "postgresql://postgres:postgres@localhost:5432/test_db"

os.environ.setdefault("DB_URL", _TEST_DB_URL)
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "postgres")
os.environ.setdefault("DB_NAME", "test_db")


# ── Database fixtures ───────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def pg_url() -> str:
    """
    Prefer a real Postgres container (testcontainers) when the package is
    available; fall back to the env-var URL so CI environments with a
    pre-started Postgres also work.
    """
    try:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:17") as pg:
            yield pg.get_connection_url()
    except Exception:
        yield os.environ["DB_URL"]


@pytest.fixture(scope="session")
def db_engine(pg_url: str):
    """Single engine for the whole test session; schema created once."""
    engine = build_engine(pg_url, verbose=False)
    BaseModel.metadata.create_all(engine)
    yield engine
    BaseModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(db_engine) -> sessionmaker:
    """Fresh sessionmaker bound to the test engine."""
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture
def db_session(session_factory):
    """
    Yield a real DB session and roll back after every test so the
    database state is clean for the next one.
    """
    with get_db_session(session_factory) as session:
        yield session


# ── XLSX / Parquet helper factories ─────────────────────────────────────────


@pytest.fixture
def make_xlsx(tmp_path):
    """
    Factory that writes a minimal but valid XLSX history-log file.

    Usage::
        path = make_xlsx(rows=[(1, 100, "17/06/2026", "08:00:00.000"), ...])
    """
    import openpyxl

    def _factory(
        rows: list[tuple],
        header: list[str] | None = None,
        sheet_name: str = "history",
        filename: str = "device_B12345678.xlsx",
    ) -> Path:
        header = header or ["Event ID", "Value", "Date", "Time"]
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_name
        ws.append(header)
        for row in rows:
            ws.append(list(row))
        path = tmp_path / filename
        wb.save(path)
        return path

    return _factory


@pytest.fixture
def make_parquet(tmp_path):
    """
    Factory that writes a minimal valid Parquet special-event file.

    Usage::
        path = make_parquet(n_rows=3)
        path = make_parquet(overrides={"ACC_X": [9.0, 9.1]})
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    _DEFAULTS: dict[str, list] = {
        "ACC_X": [1.1, 2.2],
        "ACC_Y": [3.3, 4.4],
        "ACC_Z": [5.5, 6.6],
        "GYRO_X": [7.7, 8.8],
        "GYRO_Y": [9.9, 10.1],
        "GYRO_Z": [11.2, 12.3],
        "HDOP": [13.4, 14.5],
        "lat": [45.1, 45.2],
        "long": [9.1, 9.2],
        "speed_km_h": [30.0, 31.5],
        "Hour": [12, 12],
        "Min": [30, 31],
        "Sec": [40, 41],
        "Cent": [5, 6],
        "Alarms": [1, 2],
        "algoIgnited": [1, 0],
        "algoEnabled": [0, 1],
        "GPS_Fix": [True, False],
        "counter": [99, 98],
        "extDataPresent": [1, 1],
    }

    def _factory(
        overrides: dict | None = None,
        filename: str = "device_B12345678.parquet",
    ) -> Path:
        data = {**_DEFAULTS, **(overrides or {})}
        table = pa.table(data)
        path = tmp_path / filename
        pq.write_table(table, path)
        return path

    return _factory
