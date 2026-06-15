from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# TODO: revisit column types and fields, try to avoid memory inefficiencies
# For example, event_date and event_time could be combined into a single timestamp field
# Consider removing created_at, source_file_id, and potenially "useless" fields

def upgrade():

    # ── FileTracker ───────────────────────────────────────
    op.create_table(
        "file_tracker",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(128), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("file_mtime", sa.Float(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum_sha256", name="uq_file_tracker_checksum"),
    )
    op.create_index("idx_file_tracker_status", "file_tracker", ["status"])

    # ── HistoryRecord ───────────────────────────────────────
    op.create_table(
        "history_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("serial_number", sa.String(9), nullable=False),
        sa.Column("firmware_version", sa.Integer(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Time(), nullable=False),
        sa.Column("event_id", sa.SmallInteger(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("source_file_id", sa.BigInteger(), sa.ForeignKey("file_tracker.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial_number", "firmware_version", "event_date", "event_time", "event_id", name="uq_history_log_entry"),
    )

    # ── SpecialEvent ───────────────────────────────────────
    op.create_table(
        "special_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_file_id", sa.BigInteger(), sa.ForeignKey("file_tracker.id"), nullable=True),
        sa.Column("acc_x", sa.Float(), nullable=False),
        sa.Column("acc_y", sa.Float(), nullable=False),
        sa.Column("acc_z", sa.Float(), nullable=False),
        sa.Column("gyro_x", sa.Float(), nullable=False),
        sa.Column("gyro_y", sa.Float(), nullable=False),
        sa.Column("gyro_z", sa.Float(), nullable=False),
        sa.Column("hdop", sa.Float(), nullable=False),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("gps_fix", sa.Boolean(), nullable=False),
        sa.Column("time", sa.Time(), nullable=False),
        sa.Column("alarms", sa.Integer(), nullable=False),
        sa.Column("algo_ignited", sa.Boolean(), nullable=False),
        sa.Column("algo_enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

def downgrade():
    op.drop_table("special_event")
    op.drop_table("history_log")
    op.drop_table("file_tracker")