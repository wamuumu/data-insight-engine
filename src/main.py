import argparse
from pathlib import Path

from logger import setup_logging
from config import load_settings
from ingestion.pipeline import IngestionPipeline

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

    return parser

def handle_ingest(args: argparse.Namespace):
    """
    Handle the 'ingest' command. This is where the crawling and parsing logic will be implemented.
    """
    root = Path(args.path)

    logger.info(f"Starting ingestion process for path: {root}, dry_run={args.dry_run}")

    pipeline = IngestionPipeline(root=root, dry_run=args.dry_run)
    stats = pipeline.run()

    if stats.files_failed > 0:
        logger.warning(f"Ingestion completed with some errors. Failed files: {stats.files_failed}, Errors: {stats.errors}")

if __name__ == "__main__":
    arg_parser = build_parser()
    args = arg_parser.parse_args()

    # Override log level from command-line argument if provided
    if hasattr(args, "log_level") and args.log_level:
        logger.setLevel(args.log_level)
    
    # Run the appropriate command handler
    args.func(args)