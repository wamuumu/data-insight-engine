from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Integer, LargeBinary, String, Text, Date, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel


class FileStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# TODO: is file available? is deleted?
# TODO: add rows_inserted field?


class FileTracker(BaseModel):
    __tablename__ = "file_tracker"
    __table_args__ = (
        UniqueConstraint("checksum_sha256", name="uq_file_tracker_checksum"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Identity ──────────────────────────────────────────────
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    checksum_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)

    # ── Processing ────────────────────────────────────────────
    status: Mapped[FileStatus] = mapped_column(
        String(16), nullable=False, default=FileStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
