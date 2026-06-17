from __future__ import annotations

import pytest

from config import Settings


def test_settings_normalizes_log_level():
    settings = Settings(
        db_url="postgresql://user:pass@localhost:5432/db",
        db_user="user",
        db_password="pass",
        db_name="db",
        metrics_port=8000,
        log_level="debug",
    )

    assert settings.log_level == "DEBUG"


def test_settings_rejects_invalid_log_level():
    with pytest.raises(ValueError, match="Invalid log level"):
        Settings(
            db_url="postgresql://user:pass@localhost:5432/db",
            db_user="user",
            db_password="pass",
            db_name="db",
            metrics_port=8000,
            log_level="verbose",
        )