import logging
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
import shutil

def setup_logging(log_level: str, log_dir: str = "logs") -> Logger:
    """
    Set up logging configuration with a rotating file handler.
    """
    # Create logs directory if it doesn't exist, or clear it if it does
    LOG_DIR = Path(log_dir)
    if LOG_DIR.exists():
        shutil.rmtree(LOG_DIR)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Logging format
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%d-%m-%Y %H:%M:%S")

    # File handler 
    file_handler = RotatingFileHandler(LOG_DIR / "system.log", maxBytes=10*1024*1024, backupCount=5)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Return a logger instance for the specified name
    return logger