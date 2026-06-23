from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel


class HistoryLog(BaseModel):
    __tablename__ = "history_log"
    __table_args__ = (Index("idx_history_log_device_ts", "device_id", "event_ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── Device identity ─────────────────────────────────────────
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("device.id"), nullable=False
    )

    # ── Firmware and event details ──────────────────────────────
    firmware_version: Mapped[int] = mapped_column(Integer, nullable=True)
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Lineage ─────────────────────────────────────────────────
    source_file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("file_tracker.id"), nullable=True
    )
