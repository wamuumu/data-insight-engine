from sqlalchemy import BigInteger, Date, Time, DateTime, Integer, SmallInteger, String, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel


class HistoryLog(BaseModel):
    __tablename__ = "history_log"
    __table_args__ = (
        UniqueConstraint(
            "serial_number",
            "firmware_version",
            "event_date",
            "event_time",
            "event_id",
            name="uq_history_log_entry"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── Device identity ─────────────────────────────────────────
    serial_number: Mapped[str] = mapped_column(String(9), nullable=False)
    firmware_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Event details ───────────────────────────────────────────
    event_date: Mapped[Date] = mapped_column(Date, nullable=False)
    event_time: Mapped[Time] = mapped_column(Time, nullable=False)

    # ── Event data ──────────────────────────────────────────────
    event_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Lineage ─────────────────────────────────────────────────
    source_file_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("file_tracker.id"), nullable=True)
    
