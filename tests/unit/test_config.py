from __future__ import annotations

import pytest

from config import Settings


def test_settings_normalize_log_level():
    settings = Settings(log_level="debug")

    assert settings.log_level == "DEBUG"


def test_settings_rejects_invalid_log_level():
    with pytest.raises(ValueError):
        Settings(log_level="trace")