from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel


class FileTracker(BaseModel):
    __tablename__ = "file_tracker"
    __table_args__ = (
        UniqueConstraint("checksum_sha256", name="uq_file_tracker_checksum"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── Identity ──────────────────────────────────────────────
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(128), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False) # xlsx | parquet
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_mtime: Mapped[float] = mapped_column(Float, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # ── Processing Status ─────────────────────────────────────
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending") # pending | processing | done | failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Statistics ────────────────────────────────────────────
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Timestamps ───────────────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
