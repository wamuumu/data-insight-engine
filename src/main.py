import argparse
import logging
from pathlib import Path

from prometheus_client import start_http_server

from common.logging import setup_logging, get_logger
from config import load_settings
from db.session import init_db
from ingestion.crawler.base import BaseFile
from ingestion.pipeline import IngestionPipeline
from ingestion.registry import get_parser
from scheduler import build_scheduler

# Load settings
settings = load_settings()

# Set up logging
setup_logging(log_level=settings.log_level, log_format=settings.log_format)
logger = get_logger(__name__)

def build_parser() -> argparse.ArgumentParser:
    """
    Build the command-line argument parser.
    """
    parser = argparse.ArgumentParser(description="Data Insight Engine - ETL pipeline for device history data")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    # ── ingest ───────────────────────────────────────
    ingest_parser = subparsers.add_parser("ingest", help="Crawl a directory and ingest all supported files")
    ingest_parser.add_argument("path", type=str, help="Root path to crawl")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Parse files and validate output without writing to the database")
    ingest_parser.set_defaults(func=handle_ingest)

    # ── file ─────────────────────────────────────────
    file_parser = subparsers.add_parser("file", help="Parse (and optionally ingest) a single file")
    file_parser.add_argument("file_path", type=str, help="Path to the file")
    file_parser.add_argument("--dry-run", action="store_true", help="Parse the file and validate output without writing to the database")
    file_parser.set_defaults(func=handle_file)

    # ── scheduler ───────────────────────────────────
    scheduler_parser = subparsers.add_parser("schedule", help="Start the scheduler and run ingestion at configured intervals")
    scheduler_parser.add_argument("--time", type=str, help="Time to run the ingestion job (e.g., '02:00:00' for 2 AM daily)")
    scheduler_parser.add_argument("--day-of-week", type=str, help="Day of the week to run the job (e.g., 'mon', 'tue', 'mon-fri', etc.)")
    scheduler_parser.add_argument("--day", type=int, help="Day of the month to run the job")
    scheduler_parser.add_argument("--month", type=int, help="Month to run the job (1-12)")
    scheduler_parser.set_defaults(func=handle_scheduler)

    return parser

def handle_ingest(args: argparse.Namespace):
    """
    Handle the 'ingest' command to crawl a directory and ingest files.
    """
    root = Path(args.path)

    logger.info("Starting ingestion process", path=str(root), dry_run=args.dry_run)

    # Initialize database connection
    session_factory = init_db(settings.db_url)

    pipeline = IngestionPipeline(root=root, session_factory=session_factory, dry_run=args.dry_run)
    stats = pipeline.run()

    if stats.files_failed:
        logger.warning("Ingestion finished with some failures", failed_files=stats.files_failed)

def handle_file(args: argparse.Namespace):
    """
    Parse a single file and optionally ingest it into the database.
    """
    file_path = Path(args.file_path)

    logger.info("Starting file parsing process", file_path=str(file_path), dry_run=args.dry_run)

    base_file = BaseFile(file_path)

    parser = get_parser(base_file)

    if not parser:
        logger.error("Unsupported file type", file_type=base_file.suffix, file_path=str(file_path))
        return
    
    if args.dry_run:
        for record in parser.parse(base_file):
            logger.info("Parsed record", record=record)
        return
    
    # Non-dry run: ingest the file
    session_factory = init_db(settings.db_url, log_level=settings.log_level)
    pipeline = IngestionPipeline(root=file_path.parent, session_factory=session_factory, dry_run=False)

    parser_instance = get_parser(base_file)
    if parser_instance:
        pipeline._process_one(base_file, stats=type("Stats", (), {
            "files_discovered": 0, "files_parsed": 0, "files_skipped": 0,
            "files_deduplicated": 0, "files_failed": 0, "records_produced": 0,
            "records_inserted": 0, "errors": [],
        }))

def handle_scheduler(args: argparse.Namespace):
    """
    Start the scheduler to run the ingestion pipeline at configured intervals.
    """
    logger.info("Starting scheduler mode", time=args.time, day_of_week=args.day_of_week, day=args.day, month=args.month)
    session_factory = init_db(settings.db_url, log_level=settings.log_level)
    pipeline = IngestionPipeline(root=Path(settings.data_root), session_factory=session_factory, dry_run=False)
    scheduler = build_scheduler(pipeline, time_str=args.time, day_of_week=args.day_of_week, day=args.day, month=args.month)
    logger.info("Scheduler started successfully, wait for the next scheduled run")
    scheduler.start()

if __name__ == "__main__":

    # Start Prometheus metrics server
    start_http_server(settings.metrics_port)
    logger.info("Prometheus metrics server started", port=str(settings.metrics_port))

    # Build and parse command-line arguments
    arg_parser = build_parser()
    args = arg_parser.parse_args()
    
    # Run the appropriate command handler
    args.func(args)