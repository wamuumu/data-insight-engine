from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generator


class BaseFile:
    """
    Represents a discovered file with its metadata.
    """

    def __init__(self, path: Path):
        self.path = path
        self.stem = path.stem
        self.suffix = path.suffix.lower()
        self.size = path.stat().st_size
        self.modified_at = path.stat().st_mtime

    def __repr__(self):
        return f"BaseFile(path={self.path}, size={self.size}, modified_at={self.modified_at})"


class BaseCrawler(ABC):
    """
    Abstract crawler. Must yield BaseFile instances one at a time.
    """

    @abstractmethod
    def crawl(self) -> Generator[BaseFile, None, None]:
        """
        Crawl the source and yield BaseFile instances.
        """
        ...
