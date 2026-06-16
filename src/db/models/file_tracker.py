from enum import StrEnum
from pathlib import Path

from sqlalchemy import Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel

class FileStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

class FileTracker(BaseModel):
    __tablename__ = "file_tracker"
    __table_args__ = (
        UniqueConstraint("checksum_sha256", name="uq_file_tracker_checksum"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Identity ──────────────────────────────────────────────
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)

    # ── Processing ────────────────────────────────────────────
    status: Mapped[FileStatus] = mapped_column(String(16), nullable=False, default=FileStatus.PENDING.value)

    @property
    def file_name(self) -> str:
        """Derive the file name from the file path."""
        return Path(self.file_path).name
    
    @property
    def file_type(self) -> str:
        """Derive the file type from the file name."""
        return Path(self.file_path).suffix[1:].lower()  # Get extension without dot and convert to lower case
    
    @property
    def file_size(self) -> int:
        """Get the file size in bytes."""
        return Path(self.file_path).stat().st_size
    
    @property
    def file_mtime(self) -> float:
        """Get the file modification time in seconds since the epoch."""
        return Path(self.file_path).stat().st_mtime