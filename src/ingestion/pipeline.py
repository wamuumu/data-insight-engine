import logging
from dataclasses import dataclass, field
from pathlib import Path

from ingestion.crawler.drive import DriveCrawler
from ingestion.registry import get_parser

logger = logging.getLogger(__name__)

@dataclass
class PipelineStats:
    """
    Tracks statistics about the ingestion pipeline execution.
    """
    files_discovered: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    records_produced: int = 0
    errors: list[str] = field(default_factory=list)

class IngestionPipeline:
    """
    Orchestrates the crawling and parsing of files for ingestion.
    """
    def __init__(self, root: Path, dry_run: bool = False):
        self.root = root
        self.dry_run = dry_run
        self.crawler = DriveCrawler(root)
    
    def run(self) -> PipelineStats:
        stats = PipelineStats()
        
        for file in self.crawler.crawl():
            stats.files_discovered += 1
            logger.debug(f"Discovered file: {file.path} (size: {file.size} bytes)")
            
            parser = get_parser(file)

            if not parser:
                logger.info(f"No parser found for file: {file.path}, skipping.")
                stats.files_skipped += 1
                continue

            try:
                for record in parser.parse(file):
                    if record.record_type == "raw_data":
                        with open("logs/raw.log", "a") as f:
                            f.write(f"{record.data}\n")
                    else:
                        with open("logs/history.log", "a") as f:
                            f.write(f"{record.data}\n")
                    stats.records_produced += 1
                
                stats.files_parsed += 1
            except Exception as e:
                logger.error(f"Error occurred while parsing file: {file.path}, skipping.")
                stats.files_failed += 1
                stats.errors.append(str(e))
                continue
        
        logger.info(f"Ingestion completed. Stats: {stats}")
        return stats