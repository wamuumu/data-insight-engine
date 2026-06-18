from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.logging import get_logger
from db.repositories.base import BaseRepository
from db.models.device import Device

logger = get_logger(__name__)


class DeviceRepository(BaseRepository[Device]):
    def __init__(self):
        super().__init__(Device)

    def get_device_by_serial_number(
        self, session: Session, serial_number: str
    ) -> Device | None:
        """
        Retrieve a device by its serial number.
        """
        stmt = select(Device).where(Device.serial_number == serial_number)
        result = session.execute(stmt).scalar_one_or_none()
        return result

    def create_device(self, session: Session, serial_number: str) -> Device:
        """
        Create a new device record in the database.
        """
        stmt = (
            insert(Device)
            .values(serial_number=serial_number)
            .on_conflict_do_nothing(constraint="uq_device_serial_number")
            .returning(Device)
        )
        result = session.execute(stmt).scalar_one_or_none()

        if result is None:
            # If the device already exists, fetch it
            result = self.get_device_by_serial_number(session, serial_number)

        return result
