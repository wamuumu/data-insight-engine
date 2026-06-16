from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import BaseModel


class Device(BaseModel):
    __tablename__ = "device"
    __table_args__ = (
        UniqueConstraint("serial_number", name="uq_device_serial_number"),
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(9), nullable=False)
    