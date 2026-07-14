from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import REAL, BYTEA

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():

    # ── Device ────────────────────────────────────────────
    op.create_table(
        "device",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("serial_number", sa.String(9), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial_number", name="uq_device_serial_number"),
    )

    # ── FileTracker ───────────────────────────────────────
    op.create_table(
        "file_tracker",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("checksum_sha256", BYTEA(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_inserted", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum_sha256", name="uq_file_tracker_checksum"),
    )

    # ── HistoryRecord ───────────────────────────────────────
    op.create_table(
        "history_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "device_id", sa.Integer(), sa.ForeignKey("device.id"), nullable=False
        ),
        sa.Column("firmware_version", sa.Integer(), nullable=False),
        sa.Column("event_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.SmallInteger(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("tssc", sa.BigInteger(), nullable=False),
        sa.Column(
            "source_file_id",
            sa.Integer(),
            sa.ForeignKey("file_tracker.id"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_id",
            "event_ts",
            "event_id",
            name="uq_history_log_row",
        ),
    )

    # ── SpecialEvent ───────────────────────────────────────
    op.create_table(
        "special_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "device_id", sa.Integer(), sa.ForeignKey("device.id"), nullable=False
        ),
        sa.Column("acc_x_mean", REAL(), nullable=False),
        sa.Column("acc_y_mean", REAL(), nullable=False),
        sa.Column("acc_z_mean", REAL(), nullable=False),
        sa.Column("acc_x_std", REAL(), nullable=False),
        sa.Column("acc_y_std", REAL(), nullable=False),
        sa.Column("acc_z_std", REAL(), nullable=False),
        sa.Column("acc_x_min", REAL(), nullable=False),
        sa.Column("acc_y_min", REAL(), nullable=False),
        sa.Column("acc_z_min", REAL(), nullable=False),
        sa.Column("acc_x_max", REAL(), nullable=False),
        sa.Column("acc_y_max", REAL(), nullable=False),
        sa.Column("acc_z_max", REAL(), nullable=False),
        sa.Column("acc_x_p05", REAL(), nullable=False),
        sa.Column("acc_y_p05", REAL(), nullable=False),
        sa.Column("acc_z_p05", REAL(), nullable=False),
        sa.Column("acc_x_p95", REAL(), nullable=False),
        sa.Column("acc_y_p95", REAL(), nullable=False),
        sa.Column("acc_z_p95", REAL(), nullable=False),
        sa.Column("acc_x_rms", REAL(), nullable=False),
        sa.Column("acc_y_rms", REAL(), nullable=False),
        sa.Column("acc_z_rms", REAL(), nullable=False),
        sa.Column("acc_x_skew", REAL(), nullable=False),
        sa.Column("acc_y_skew", REAL(), nullable=False),
        sa.Column("acc_z_skew", REAL(), nullable=False),
        sa.Column("acc_x_kurtosis", REAL(), nullable=False),
        sa.Column("acc_y_kurtosis", REAL(), nullable=False),
        sa.Column("acc_z_kurtosis", REAL(), nullable=False),
        sa.Column("acc_x_zero_crossings", sa.Integer(), nullable=False),
        sa.Column("acc_y_zero_crossings", sa.Integer(), nullable=False),
        sa.Column("acc_z_zero_crossings", sa.Integer(), nullable=False),
        sa.Column("gyro_x_mean", REAL(), nullable=False),
        sa.Column("gyro_y_mean", REAL(), nullable=False),
        sa.Column("gyro_z_mean", REAL(), nullable=False),
        sa.Column("gyro_x_std", REAL(), nullable=False),
        sa.Column("gyro_y_std", REAL(), nullable=False),
        sa.Column("gyro_z_std", REAL(), nullable=False),
        sa.Column("gyro_x_min", REAL(), nullable=False),
        sa.Column("gyro_y_min", REAL(), nullable=False),
        sa.Column("gyro_z_min", REAL(), nullable=False),
        sa.Column("gyro_x_max", REAL(), nullable=False),
        sa.Column("gyro_y_max", REAL(), nullable=False),
        sa.Column("gyro_z_max", REAL(), nullable=False),
        sa.Column("gyro_x_p05", REAL(), nullable=False),
        sa.Column("gyro_y_p05", REAL(), nullable=False),
        sa.Column("gyro_z_p05", REAL(), nullable=False),
        sa.Column("gyro_x_p95", REAL(), nullable=False),
        sa.Column("gyro_y_p95", REAL(), nullable=False),
        sa.Column("gyro_z_p95", REAL(), nullable=False),
        sa.Column("gyro_x_rms", REAL(), nullable=False),
        sa.Column("gyro_y_rms", REAL(), nullable=False),
        sa.Column("gyro_z_rms", REAL(), nullable=False),
        sa.Column("gyro_x_skew", REAL(), nullable=False),
        sa.Column("gyro_y_skew", REAL(), nullable=False),
        sa.Column("gyro_z_skew", REAL(), nullable=False),
        sa.Column("gyro_x_kurtosis", REAL(), nullable=False),
        sa.Column("gyro_y_kurtosis", REAL(), nullable=False),
        sa.Column("gyro_z_kurtosis", REAL(), nullable=False),
        sa.Column("gyro_x_zero_crossings", sa.Integer(), nullable=False),
        sa.Column("gyro_y_zero_crossings", sa.Integer(), nullable=False),
        sa.Column("gyro_z_zero_crossings", sa.Integer(), nullable=False),
        sa.Column("acc_magnitude_mean", REAL(), nullable=False),
        sa.Column("acc_magnitude_std", REAL(), nullable=False),
        sa.Column("acc_magnitude_max", REAL(), nullable=False),
        sa.Column("acc_magnitude_p05", REAL(), nullable=False),
        sa.Column("acc_magnitude_p95", REAL(), nullable=False),
        sa.Column("acc_magnitude_skew", REAL(), nullable=False),
        sa.Column("acc_magnitude_kurtosis", REAL(), nullable=False),
        sa.Column("gyro_magnitude_mean", REAL(), nullable=False),
        sa.Column("gyro_magnitude_std", REAL(), nullable=False),
        sa.Column("gyro_magnitude_max", REAL(), nullable=False),
        sa.Column("gyro_magnitude_p05", REAL(), nullable=False),
        sa.Column("gyro_magnitude_p95", REAL(), nullable=False),
        sa.Column("gyro_magnitude_skew", REAL(), nullable=False),
        sa.Column("gyro_magnitude_kurtosis", REAL(), nullable=False),
        sa.Column("acc_jerk_mean", REAL(), nullable=False),
        sa.Column("acc_jerk_std", REAL(), nullable=False),
        sa.Column("acc_jerk_p95", REAL(), nullable=False),
        sa.Column("gyro_jerk_mean", REAL(), nullable=False),
        sa.Column("gyro_jerk_std", REAL(), nullable=False),
        sa.Column("gyro_jerk_p95", REAL(), nullable=False),
        sa.Column("total_angular_displacement_deg", REAL(), nullable=False),
        sa.Column("acc_xy_correlation", REAL(), nullable=False),
        sa.Column("acc_xz_correlation", REAL(), nullable=False),
        sa.Column("acc_yz_correlation", REAL(), nullable=False),
        sa.Column("gyro_xy_correlation", REAL(), nullable=False),
        sa.Column("gyro_xz_correlation", REAL(), nullable=False),
        sa.Column("gyro_yz_correlation", REAL(), nullable=False),
        sa.Column("lat_mean", REAL(), nullable=False),
        sa.Column("lon_mean", REAL(), nullable=False),
        sa.Column("hdop_mean", REAL(), nullable=False),
        sa.Column("speed_max", REAL(), nullable=False),
        sa.Column("speed_at_start", REAL(), nullable=False),
        sa.Column("speed_at_ignition", REAL(), nullable=False),
        sa.Column("speed_at_end", REAL(), nullable=False),
        sa.Column("n_samples", sa.SmallInteger(), nullable=False),
        sa.Column("gps_fix_ratio", REAL(), nullable=False),
        sa.Column("algo_enabled_start", sa.Boolean(), nullable=False),
        sa.Column("algo_enabled_end", sa.Boolean(), nullable=False),
        sa.Column("algo_enabled_ratio", REAL(), nullable=False),
        sa.Column("algo_ignited", sa.Boolean(), nullable=False),
        sa.Column(
            "source_file_id",
            sa.Integer(),
            sa.ForeignKey("file_tracker.id"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_special_event_device_id", "special_event", ["device_id"])


def downgrade():
    op.drop_table("special_event")
    op.drop_table("history_log")
    op.drop_table("file_tracker")
    op.drop_table("device")
