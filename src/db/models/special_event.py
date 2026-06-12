from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Time, DateTime, Double, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel


class SpecialEvent(BaseModel):
    __tablename__ = "special_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # ── Lineage ─────────────────────────────────────────────────
    source_file_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("file_tracker.id"), nullable=True)

    # ── Accelerometer data ──────────────────────────────────────
    acc_x: Mapped[float | None] = mapped_column(Float, nullable=False)
    acc_y: Mapped[float | None] = mapped_column(Float, nullable=False)
    acc_z: Mapped[float | None] = mapped_column(Float, nullable=False)

    # ── Gyroscope data ─────────────────────────────────────────
    gyro_x: Mapped[float | None] = mapped_column(Float, nullable=False)
    gyro_y: Mapped[float | None] = mapped_column(Float, nullable=False)
    gyro_z: Mapped[float | None] = mapped_column(Float, nullable=False)

    # ── GPS data ───────────────────────────────────────────────
    hdop: Mapped[float | None] = mapped_column(Float, nullable=False)
    lat: Mapped[float | None] = mapped_column(Double, nullable=False)
    lon: Mapped[float | None] = mapped_column(Double, nullable=False)
    speed: Mapped[float | None] = mapped_column(Float, nullable=False)
    gps_fix: Mapped[bool | None] = mapped_column(Boolean, nullable=False)

    # ── Time infos ─────────────────────────────────────────────
    time: Mapped[Time] = mapped_column(Time, nullable=False)

    # ── Alarms & flags ─────────────────────────────────────────
    alarms: Mapped[int | None] = mapped_column(Integer, nullable=False)
    algo_ignited: Mapped[bool | None] = mapped_column(Boolean, nullable=False)
    algo_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False)
