from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import REAL, BYTEA

from db.models.file_tracker import FileStatus

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# TODO: revisit column types and fields, try to avoid memory inefficiencies
# For example, event_date and event_time could be combined into a single timestamp field
# Consider removing created_at, source_file_id, and potenially "useless" fields

# Actual numbers: 
# FileTracker:
    # 2 files, table_size = 8192 bytes, indexes_size = 32 KB, total_size = 48 KB
# HistoryRecord:
    # 1811 records, table_size = 152 KB, indexes_size = 56 KB, total_size = 240 KB, xlsx log file = 60 KB
# SpecialEvent:
    # 8726 records, table_size = 1432 KB, indexes_size = 208 KB, total_size = 1672 KB, parquet special event file = 139 KB

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
        sa.Column("checksum_sha256", BYTEA(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=FileStatus.PENDING),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum_sha256", name="uq_file_tracker_checksum"),
    )

    # ── HistoryRecord ───────────────────────────────────────
    op.create_table(
        "history_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("device.id"), nullable=False),
        sa.Column("firmware_version", sa.Integer(), nullable=False),
        sa.Column("event_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.SmallInteger(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("file_tracker.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_history_log_device_ts", "history_log", ["device_id", "event_ts"])

    # ── SpecialEvent ───────────────────────────────────────
    op.create_table(
        "special_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("device.id"), nullable=False),
        sa.Column("acc_x", REAL(), nullable=False),
        sa.Column("acc_y", REAL(), nullable=False),
        sa.Column("acc_z", REAL(), nullable=False),
        sa.Column("gyro_x", REAL(), nullable=False),
        sa.Column("gyro_y", REAL(), nullable=False),
        sa.Column("gyro_z", REAL(), nullable=False),
        sa.Column("hdop", REAL(), nullable=False),
        sa.Column("lat", REAL(), nullable=False),
        sa.Column("lon", REAL(), nullable=False),
        sa.Column("speed", REAL(), nullable=False),
        sa.Column("gps_fix", sa.Boolean(), nullable=False),
        sa.Column("time", sa.Time(), nullable=False),
        sa.Column("alarms", sa.Integer(), nullable=False),
        sa.Column("algo_ignited", sa.Boolean(), nullable=False),
        sa.Column("algo_enabled", sa.Boolean(), nullable=False),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("file_tracker.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_special_event_device_id", "special_event", ["device_id"])

def downgrade():
    op.drop_table("special_event")
    op.drop_table("history_log")
    op.drop_table("file_tracker")
    op.drop_table("device")