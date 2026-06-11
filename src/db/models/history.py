from datetime import datetime
from sqlalchemy import (
    String,
    BigInteger,
    Integer,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base



class HistoryLog(Base):
    __tablename__ = "history_log"
    __table_args__ = (
        UniqueConstraint(
            "serial_number",
            "firmware_version",
            "date",
            "time",
            "event_id",
            name="uq_history_log_entry"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    serial_number: Mapped[str] = mapped_column(String(16), nullable=False)
    firmware_version: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[str] = mapped_column(String(16), nullable=False)
    time: Mapped[str] = mapped_column(String(20), nullable=False)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    
