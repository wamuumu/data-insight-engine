import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.repositories.base import Base
from db.models.special_event import SpecialEvent
from ingestion.parsers.base import SpecialEventRecord

logger = logging.getLogger(__name__)


class SpecialEventRepository(Base[SpecialEvent]):
    def __init__(self, session: Session):
        super().__init__(SpecialEvent, session)

    def upsert_special_events(
        self,
        records: list[SpecialEventRecord],
        source_file_id: int | None = None
    ) -> int:
        """
        Batch-upsert special event records into the database. Duplicates are checked using file_tracker. Returns the number of records successfully inserted.
        """
        if not records:
            return 0
        
        rows = [self._special_event_to_row(r, source_file_id) for r in records]
        result = self.session.execute(insert(SpecialEvent).values(rows))
        return result.rowcount

    def _special_event_to_row(self, record: SpecialEventRecord, source_file_id: int | None) -> dict:
        """
        Convert a SpecialEventRecord to a dictionary suitable for database insertion.
        """
        
        return {
            "source_file_id": source_file_id,
            "acc_x": record.data.get("acc_x"),
            "acc_y": record.data.get("acc_y"),
            "acc_z": record.data.get("acc_z"),
            "gyro_x": record.data.get("gyro_x"),
            "gyro_y": record.data.get("gyro_y"),
            "gyro_z": record.data.get("gyro_z"),
            "hdop": record.data.get("hdop"),
            "lat": record.data.get("lat"),
            "lon": record.data.get("lon"),
            "speed": record.data.get("speed"),
            "gps_fix": bool(record.data.get("gps_fix")) if record.data.get("gps_fix") is not None else None,
            "hour": record.data.get("hour"),
            "minute": record.data.get("minute"),
            "second": record.data.get("second"),
            "centisecond": record.data.get("centisecond"),
            "alarms": record.data.get("alarms"),
            "ext_data_present": bool(record.data.get("ext_data_present")) if record.data.get("ext_data_present") is not None else None,
            "algo_ignited": bool(record.data.get("algo_ignited")) if record.data.get("algo_ignited") is not None else None,
            "algo_enabled": bool(record.data.get("algo_enabled")) if record.data.get("algo_enabled") is not None else None,
        }