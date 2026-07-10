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
        extra="ignore",  # Ignore unknown fields in .env
    )

    # ── Parsing ────────────────────────────────────────────────
    parquet_batch_size: int = Field(
        default=100,
        description="Number of rows to read at a time when parsing Parquet files",
    )

    # ── Database ───────────────────────────────────────────────
    db_url: str = Field(
        ...,
        description="SQLAlchemy database URL for connecting to the PostgreSQL database",
    )
    db_user: str = Field(..., description="Database username for authentication")
    db_password: str = Field(..., description="Database password for authentication")
    db_name: str = Field(
        ..., description="Name of the PostgreSQL database to connect to"
    )
    db_batch_size: int = Field(
        default=100,
        description="Number of records to insert into the database in a single batch",
    )

    # ── Ingestion ──────────────────────────────────────────────
    workers: int = Field(
        default=4, description="Number of parallel workers for file ingestion"
    )
    db_retry_initial_delay: float = Field(
        default=0.5,
        description="Initial delay in seconds before retrying a failed database operation",
    )
    db_retry_max_delay: float = Field(
        default=8.0,
        description="Maximum delay in seconds between retries for database operations",
    )
    db_retry_timeout: float = Field(
        default=300,
        description="Maximum time in seconds to retry processing a file before giving up",
    )

    # ── Scheduler ──────────────────────────────────────────────
    data_root: str = Field(
        default="data", description="Root directory to crawl for data files"
    )

    # ── Metrics ───────────────────────────────────────────────
    metrics_port: int = Field(..., description="Port to expose Prometheus metrics on")

    # ── Logging ────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Logging verbosity level")
    log_format: str = Field(
        default="console",
        description="Logging format: 'console' for human-readable or 'json' for structured JSON logs",
    )

    # ── Validators ─────────────────────────────────────────────
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if value.upper() not in valid_levels:
            raise ValueError(
                f"Invalid log level: {value}. Must be one of {valid_levels}"
            )
        return value.upper()


def load_settings() -> Settings:
    """
    Load and validate settings from environment variables. Exits on validation errors.
    """
    try:
        return Settings()
    except Exception as e:
        print(f"Error loading settings: {e}")
        exit(1)
