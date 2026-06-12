from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Double, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class SpecialEvent(Base):
    __tablename__ = "special_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # ── Lineage ─────────────────────────────────────────────────
    source_file_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("file_tracker.id"), nullable=True)

    # ── Accelerometer data ──────────────────────────────────────
    acc_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    acc_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    acc_z: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Gyroscope data ─────────────────────────────────────────
    gyro_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    gyro_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    gyro_z: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── GPS data ───────────────────────────────────────────────
    hdop: Mapped[float | None] = mapped_column(Float, nullable=True)
    lat: Mapped[float | None] = mapped_column(Double, nullable=True)
    lon: Mapped[float | None] = mapped_column(Double, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_fix: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── Timestamps ─────────────────────────────────────────────
    hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    second: Mapped[int | None] = mapped_column(Integer, nullable=True)
    centisecond: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Alarms & flags ─────────────────────────────────────────
    alarms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ext_data_present: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    algo_ignited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    algo_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False)
