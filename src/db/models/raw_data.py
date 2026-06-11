from datetime import datetime
from sqlalchemy import (
    String,
    BigInteger,
    DateTime,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class RawData(Base):
    __tablename__ = "raw_data"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
