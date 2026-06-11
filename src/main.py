import argparse
from pathlib import Path

from config import load_settings
from common.logging import setup_logging
from db.session import init_db
from ingestion.pipeline import IngestionPipeline
from ingestion.crawler.base import BaseFile
from ingestion.parsers.xlsx import XLSXParser
from ingestion.parsers.parquet import ParquetParser

# Load settings
settings = load_settings()

# Set up logging
logger = setup_logging(log_level=settings.log_level)

def build_parser() -> argparse.ArgumentParser:
    """
    Build the command-line argument parser.
    """
    parser = argparse.ArgumentParser(description="Data Insight Engine - Ingestion Service")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    # Subparsers for different commands can be added here (e.g., crawl, parse, etc.)
    ingest_parser = subparsers.add_parser("ingest", help="Crawl a directory and ingest all supported files")
    ingest_parser.add_argument("path", type=str, help="Root path to crawl")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without actual ingestion on the database")
    ingest_parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging verbosity level for this command")
    ingest_parser.set_defaults(func=handle_ingest)

    file_parser = subparsers.add_parser("file", help="Ingest a single file")
    file_parser.add_argument("file_path", type=str, help="Path to the file to ingest")
    file_parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without actual ingestion on the database")
    file_parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging verbosity level for this command")
    file_parser.set_defaults(func=handle_file)

    return parser

def handle_ingest(args: argparse.Namespace):
    """
    Handle the 'ingest' command. This is where the crawling and parsing logic will be implemented.
    """
    root = Path(args.path)

    logger.info(f"Starting ingestion process for path: {root}, dry_run={args.dry_run}")

    # Initialize database at startup if not already initialized
    session_factory = init_db(settings.db_url)

    pipeline = IngestionPipeline(root=root, sessionfactory=session_factory, dry_run=args.dry_run)
    stats = pipeline.run()

    if stats.files_failed > 0:
        logger.warning(f"Ingestion completed with some errors. Failed files: {stats.files_failed}, Errors: {stats.errors}")

def handle_file(args: argparse.Namespace):
    """
    Handle the 'file' command to ingest a single file.
    """
    file_path = Path(args.file_path)

    logger.info(f"Starting ingestion process for file: {file_path}, dry_run={args.dry_run}")

    # Parse the file in a log file using the proper parser, without db
    if file_path.suffix == ".xlsx":
        parser = XLSXParser()
    elif file_path.suffix == ".parquet":
        parser = ParquetParser()
    else:
        logger.error(f"Unsupported file type for file: {file_path}")
        return
    
    try:
        for record in parser.parse(BaseFile(path=file_path, size=file_path.stat().st_size)):
            logger.debug(f"Parsed record from file {file_path}: {record}")
    except Exception as e:
        logger.error(f"Error parsing file: {file_path}, error: {e}")

if __name__ == "__main__":
    arg_parser = build_parser()
    args = arg_parser.parse_args()

    # Override log level from command-line argument if provided
    if hasattr(args, "log_level") and args.log_level:
        logger.setLevel(args.log_level)
    
    # Run the appropriate command handler
    args.func(args)