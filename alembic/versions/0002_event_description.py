from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_description",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("description", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        INSERT INTO event_description (id, description) VALUES
            (0, 'None'),
            (1, 'Switch On'),
            (2, 'Switch Off'),
            (3, 'Alarm On'),
            (4, 'Alarm Off'),
            (5, '[SYS] Ready'),
            (6, '[SYS] Armed'),
            (7, 'Logging'),
            (8, '[SYS] Charging'),
            (9, 'Charge Completed'),
            (10, '[SYS] Uploading'),
            (11, 'RTC Set'),
            (12, 'GGM Reset'),
            (13, 'Batt Fault'),
            (14, 'Batt mSOC'),
            (15, 'Batt mV'),
            (16, 'Arming Mode'),
            (17, 'Riding Mode'),
            (18, 'Gps Fix'),
            (19, 'Gps Latitude'),
            (20, 'Gps Longitude'),
            (21, 'Gps Speed'),
            (22, 'Set Charger'),
            (23, 'Squib Read'),
            (24, 'Cap mV'),
            (25, 'History Log Error'),
            (26, 'Ble Connected'),
            (27, 'Ble Update'),
            (28, 'User Command'),
            (29, '[SYS] Unknown'),
            (30, 'SOC Forced'),
            (31, 'Updater update start'),
            (32, 'Self Test Result'),
            (33, '[SYS] Active'),
            (34, '[SYS] Arming Disabled'),
            (35, 'Entering Deep Sleep'),
            (36, 'SEV Request'),
            (37, 'SEV Unable to Save'),
            (38, 'Updater update ended'),
            (39, 'App update requested'),
            (40, '[SYS] Error'),
            (41, '[SYS] Shutdown'),
            (42, '[SYS] Unregistered'),
            (43, 'HL Reset'),
            (44, 'SEV Download'),
            (45, 'HL Download'),
            (46, 'Upd run detected'),
            (47, 'Reset detected'),
            (48, 'Algorithm period us'),
            (49, 'Task number'),
            (50, 'GPS Max Period Reached'),
            (51, 'GPS Settings Error'),
            (52, 'Dbg Download'),
            (53, 'GPS Anomaly Detected'),
            (54, 'Command Payload 1st byte'),
            (55, 'Alarm Reset'),
            (56, 'GPS Reset'),
            (57, 'BLE Overload'),
            (-11, 'RTC Reset'),
            (-12, 'RTC Guess')
        """
    )


def downgrade():
    op.drop_table("event_description")
