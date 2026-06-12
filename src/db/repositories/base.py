from typing import Generic, TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")

class Base(Generic[T]):
    def __init__(self, model: T, session: Session):
        self.model = model
        self.session = session