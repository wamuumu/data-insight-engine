from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel


class HistoryLog(BaseModel):
    __tablename__ = "history_log"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "event_ts",
            "event_id",
            name="uq_history_log_row",
        ),    
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── Device identity ─────────────────────────────────────────
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("device.id"), nullable=False
    )

    # ── Firmware and event details ──────────────────────────────
    firmware_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Lineage ─────────────────────────────────────────────────
    source_file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("file_tracker.id"), nullable=False
    )
