import logging
from pathlib import Path
from typing import Generator

from common.constants import SUPPORTED_EXTENSIONS
from ingestion.crawler.base import BaseCrawler, BaseFile

logger = logging.getLogger(__name__)

class DriveCrawler(BaseCrawler):
    """
    Crawler for local/network drive. Recursively searches for files with supported extensions.
    Generator-based: yields one file at a time, safe for large directories.
    """
    def __init__(self, root_path: Path):
        if not root_path.exists():
            raise FileNotFoundError(f"Root path {root_path} does not exist.")
        if not root_path.is_dir():
            raise NotADirectoryError(f"Root path {root_path} is not a directory.")
        self.root = root_path
    
    def crawl(self) -> Generator[BaseFile, None, None]:
        """
        Recursively crawl the root directory and yield BaseFile instances for supported files.
        """
        logger.info("Starting crawl", extra={"root": str(self.root)})
        discovered_files = 0
        skipped_files = 0

        for path in self.root.rglob('*'):
            if not path.is_file():
                continue
            
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                skipped_files += 1
                continue
            
            discovered_files += 1
            logger.debug("Discovered file", extra={"file": str(path)})
            yield BaseFile(path)

        logger.info("Crawl completed", extra={"discovered": discovered_files, "skipped": skipped_files})