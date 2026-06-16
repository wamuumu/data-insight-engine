from datetime import time

from sqlalchemy import BigInteger, Boolean, Time, Float, Index, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel

_REAL = Float(precision=24) # Use for 32-bit float values

class SpecialEvent(BaseModel):
    __tablename__ = "special_event"
    __table_args__ = (
        Index("idx_special_event_device_id", "device_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── Device identity ─────────────────────────────────────────
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("device.id"), nullable=False)

    # ── Accelerometer data ──────────────────────────────────────
    acc_x: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z: Mapped[float] = mapped_column(_REAL, nullable=False)

    # ── Gyroscope data ─────────────────────────────────────────
    gyro_x: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z: Mapped[float] = mapped_column(_REAL, nullable=False)

    # ── GPS data ───────────────────────────────────────────────
    hdop: Mapped[float] = mapped_column(_REAL, nullable=False)
    lat: Mapped[float] = mapped_column(_REAL, nullable=False)
    lon: Mapped[float] = mapped_column(_REAL, nullable=False)
    speed: Mapped[float] = mapped_column(_REAL, nullable=False)
    gps_fix: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # ── Time infos ─────────────────────────────────────────────
    time: Mapped[time] = mapped_column(Time, nullable=False)

    # ── Alarms & flags ─────────────────────────────────────────
    alarms: Mapped[int] = mapped_column(Integer, nullable=False)
    algo_ignited: Mapped[bool] = mapped_column(Boolean, nullable=False)
    algo_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # ── Lineage ─────────────────────────────────────────────────
    source_file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("file_tracker.id"), nullable=True)
