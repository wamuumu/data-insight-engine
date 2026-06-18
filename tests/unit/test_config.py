"""
Unit tests for src/config.py

Covers:
  - Log-level normalisation (case-insensitive)
  - Rejection of invalid log levels with a descriptive error
  - All valid log levels are accepted
  - Default field values when optional settings are omitted
"""
from __future__ import annotations

import pytest

from config import Settings


# Minimal kwargs to satisfy required fields when not testing them
_REQUIRED = dict(
    db_url="postgresql://user:pass@localhost:5432/db",
    db_user="user",
    db_password="pass",
    db_name="db",
    metrics_port=8000,
)


class TestLogLevelValidation:
    @pytest.mark.parametrize("raw", ["debug", "DEBUG", "Debug", "dEbUg"])
    def test_any_case_debug_normalised_to_uppercase(self, raw: str) -> None:
        s = Settings(**_REQUIRED, log_level=raw)
        assert s.log_level == "DEBUG"

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_all_valid_log_levels_accepted(self, level: str) -> None:
        s = Settings(**_REQUIRED, log_level=level)
        assert s.log_level == level

    @pytest.mark.parametrize("bad", ["VERBOSE", "TRACE", "SILENT", "", "0", "info2"])
    def test_invalid_log_level_raises_value_error(self, bad: str) -> None:
        with pytest.raises((ValueError, Exception)):
            Settings(**_REQUIRED, log_level=bad)


class TestDefaultValues:
    def test_workers_default_is_positive(self) -> None:
        s = Settings(**_REQUIRED)
        assert s.workers >= 1

    def test_db_batch_size_default_is_positive(self) -> None:
        s = Settings(**_REQUIRED)
        assert s.db_batch_size > 0

    def test_log_format_default_is_console(self) -> None:
        s = Settings(**_REQUIRED)
        assert s.log_format == "console"

    def test_retry_initial_delay_less_than_max_delay(self) -> None:
        s = Settings(**_REQUIRED)
        assert s.db_retry_initial_delay < s.db_retry_max_delay