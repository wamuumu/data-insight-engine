from abc import ABC, abstractmethod
from typing import Generator, Any

class ParsedRecord:
    """
    Minimal container for a single parsed record.
    To be replaced once a proper DB schema is defined.
    """
    def __init__(self, source_file: str, record_type: str, data: dict[str, Any]):
        self.source_file = source_file
        self.record_type = record_type
        self.data = data
    
    def __repr__(self):
        return f"ParsedRecord(source_file={self.source_file}, record_type={self.record_type}, data={self.data})"

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
    def parse(self, file) -> Generator[ParsedRecord, None, None]:
        """
        Parse the given file and yield ParsedRecord instances.
        """
        ...