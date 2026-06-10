from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables. Validates required fields and formats.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",     
        extra="ignore",             # Ignore unknown fields in .env
    )  

    # ── Logging ────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Logging verbosity level")

    # ── Validators ─────────────────────────────────────────────
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if value.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {value}. Must be one of {valid_levels}")
        return value.upper()

def load_settings() -> Settings:
    """
    Load and validate settings from environment variables. Exits on validation errors.
    """
    try:
        settings = Settings()
        return settings
    except Exception as e:
        print(f"Error loading settings: {e}")
        exit(1)