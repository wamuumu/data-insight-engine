from abc import ABC, abstractmethod
from typing import Generator, Any, Union

class HistoryLogRecord:
    """
    Container for a history log record.
    """
    def __init__(self, source_file: str, data: dict[str, Any]):
        self.source_file = source_file
        self.data = data
    
    def __repr__(self):
        return f"HistoryLogRecord(source_file={self.source_file}, data={self.data})"

class RawDataRecord:
    """
    Container for a raw data record.
    """
    def __init__(self, source_file: str, data: dict[str, Any]):
        self.source_file = source_file
        self.data = data
    
    def __repr__(self):
        return f"RawDataRecord(source_file={self.source_file}, data={self.data})"

class BaseParser(ABC):
    """
    Abstract parser. Must yield records one at a time.
    """
    @abstractmethod
    def can_handle(self, file) -> bool:
        """
        Determine if this parser can handle the given file.
        """
        ...
    
    @abstractmethod
    def parse(self, file) -> Generator[Union[HistoryLogRecord, RawDataRecord], None, None]:
        """
        Parse the given file and yield record instances (either HistoryLogRecord or RawDataRecord).
        """
        ...