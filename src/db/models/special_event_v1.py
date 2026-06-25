from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, ForeignKey, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel

_REAL = Float(precision=24)


# TODO: add zero cross with two thresholds: first subtract the mean, then zero-cross.

class SpecialEventAggregate(BaseModel):
    __tablename__ = "special_event_aggregate"
    __table_args__ = (
        Index("idx_special_event_device_id", "device_id"),
        Index("idx_special_event_source_file_id", "source_file_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── Device identity ──────────────────────────────────────────────────────
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("device.id"), nullable=False
    )

    # ── Temporal identity ────────────────────────────────────────────────────
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # ── Acc per-axis statistics (m/s²) ───────────────────────────────────────
    acc_x_mean: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y_mean: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z_mean: Mapped[float] = mapped_column(_REAL, nullable=False)

    acc_x_std: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y_std: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z_std: Mapped[float] = mapped_column(_REAL, nullable=False)

    # Keep min/max instead of abs to preserve directionality
    acc_x_min: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y_min: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z_min: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_x_max: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y_max: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z_max: Mapped[float] = mapped_column(_REAL, nullable=False)

    acc_x_p05: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y_p05: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z_p05: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_x_p95: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y_p95: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z_p95: Mapped[float] = mapped_column(_REAL, nullable=False)

    acc_x_rms: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y_rms: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z_rms: Mapped[float] = mapped_column(_REAL, nullable=False)

    acc_x_skew: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y_skew: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z_skew: Mapped[float] = mapped_column(_REAL, nullable=False)

    acc_x_kurtosis: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_y_kurtosis: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_z_kurtosis: Mapped[float] = mapped_column(_REAL, nullable=False)

    zero_crossings_acc_x: Mapped[int] = mapped_column(Integer, nullable=False)
    zero_crossings_acc_y: Mapped[int] = mapped_column(Integer, nullable=False)
    zero_crossings_acc_z: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Gyro per-axis statistics (deg/s) ────────────────────────────────────
    gyro_x_mean: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y_mean: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z_mean: Mapped[float] = mapped_column(_REAL, nullable=False)

    gyro_x_std: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y_std: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z_std: Mapped[float] = mapped_column(_REAL, nullable=False)

    # Keep min/max instead of abs to preserve directionality
    gyro_x_min: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y_min: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z_min: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_x_max: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y_max: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z_max: Mapped[float] = mapped_column(_REAL, nullable=False)

    gyro_x_p05: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y_p05: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z_p05: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_x_p95: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y_p95: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z_p95: Mapped[float] = mapped_column(_REAL, nullable=False)

    gyro_x_rms: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y_rms: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z_rms: Mapped[float] = mapped_column(_REAL, nullable=False)

    gyro_x_skew: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y_skew: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z_skew: Mapped[float] = mapped_column(_REAL, nullable=False)

    gyro_x_kurtosis: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_y_kurtosis: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_z_kurtosis: Mapped[float] = mapped_column(_REAL, nullable=False)

    zero_crossings_gyro_x: Mapped[int] = mapped_column(Integer, nullable=False)
    zero_crossings_gyro_y: Mapped[int] = mapped_column(Integer, nullable=False)
    zero_crossings_gyro_z: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Acc magnitude statistics (√(x²+y²+z²), m/s²) ─────────────────────────
    # Per sample magnitude, then aggregated over the event.
    acc_magnitude_mean: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_magnitude_std: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_magnitude_max: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_magnitude_p05: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_magnitude_p95: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_magnitude_skew: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_magnitude_kurtosis: Mapped[float] = mapped_column(_REAL, nullable=False)

    # ── Gyro magnitude statistics (√(x²+y²+z²), deg/s) ───────────────────────
    # Per sample magnitude, then aggregated over the event.
    gyro_magnitude_mean: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_magnitude_std: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_magnitude_max: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_magnitude_p05: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_magnitude_p95: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_magnitude_skew: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_magnitude_kurtosis: Mapped[float] = mapped_column(_REAL, nullable=False)

    # ── Jerk (Δmagnitude / Δt) ───────────────────────────────────────────────
    acc_jerk_mean: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_jerk_std: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_jerk_p95: Mapped[float] = mapped_column(_REAL, nullable=False)

    gyro_jerk_mean: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_jerk_std: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_jerk_p95: Mapped[float] = mapped_column(_REAL, nullable=False)

    # ── Total rotation (deg) ─────────────────────────────────────────────────
    total_angular_displacement_deg: Mapped[float] = mapped_column(_REAL, nullable=False)

    # ── Inter-Axis Linear Correlation (Pearson r ∈ [-1, 1]) ──────────────────
    acc_xy_corr: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_xz_corr: Mapped[float] = mapped_column(_REAL, nullable=False)
    acc_yz_corr: Mapped[float] = mapped_column(_REAL, nullable=False)

    gyro_xy_corr: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_xz_corr: Mapped[float] = mapped_column(_REAL, nullable=False)
    gyro_yz_corr: Mapped[float] = mapped_column(_REAL, nullable=False)

    # ── GPS statistics ───────────────────────────────────────────────────────
    lat_mean: Mapped[float] = mapped_column(_REAL, nullable=True)
    lon_mean: Mapped[float] = mapped_column(_REAL, nullable=True)
    hdop_mean: Mapped[float] = mapped_column(_REAL, nullable=False)

    # ── Speed context at event boundaries ────────────────────────────────────
    speed_max: Mapped[float] = mapped_column(_REAL, nullable=True)
    speed_at_start: Mapped[float] = mapped_column(_REAL, nullable=True)
    speed_at_ignition: Mapped[float] = mapped_column(_REAL, nullable=True)
    speed_at_end: Mapped[float] = mapped_column(_REAL, nullable=True)

    # ── Quality metrics ──────────────────────────────────────────────────────
    n_samples: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    gps_fix_ratio: Mapped[float] = mapped_column(_REAL, nullable=False)
    algo_enabled_start: Mapped[bool] = mapped_column(Boolean, nullable=False)
    algo_enabled_end: Mapped[bool] = mapped_column(Boolean, nullable=False)
    algo_enabled_ratio: Mapped[float] = mapped_column(_REAL, nullable=False)
    algo_ignited: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # ── Lineage ──────────────────────────────────────────────────────────────
    source_file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("file_tracker.id"), nullable=True
    )
