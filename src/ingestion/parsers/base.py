from abc import ABC, abstractmethod
from typing import Any, Iterator


class HistoryLogRecord:
    """
    Container for a history log record.
    """

    __slots__ = ["source_file", "data", "is_rollover"]

    def __init__(
        self, source_file: str, data: dict[str, Any]
    ):
        self.source_file = source_file
        self.data = data

    def __repr__(self):
        return f"HistoryLogRecord(source_file={self.source_file}, data={self.data})"


class SpecialEventRecord:
    """
    Container for a special event record.
    """

    __slots__ = ["source_file", "data"]

    def __init__(self, source_file: str, data: dict[str, Any]):
        self.source_file = source_file
        self.data = data

    def __repr__(self):
        return f"SpecialEventRecord(source_file={self.source_file}, data={self.data})"


class BaseParser(ABC):
    """
    Abstract parser. Must yield records one at a time.
    """

    @abstractmethod
    def can_handle(self, file: Any) -> bool:
        """
        Determine if this parser can handle the given file.
        """
        ...

    @abstractmethod
    def parse(self, file: Any) -> Iterator[HistoryLogRecord] | SpecialEventRecord:
        """
        Parse the given file and yield either history log records or a special event record.
        """
        ...
