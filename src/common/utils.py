import re
import hashlib
from pathlib import Path
from datetime import datetime, date

from common.exceptions import PipelineError


def extract_serial_number(path: Path) -> str:
    """
    Extract the serial number from the file path using a regex pattern.
    The serial number is expected to be in the format 'B' followed by 8 hexadecimal characters.
    """
    _SN_PATTERN = re.compile(r"(B[0-9A-F]{8})")
    match = _SN_PATTERN.search(str(path))
    if not match:
        raise PipelineError(f"Failed to extract serial number from path: {path}")
    return match.group()


def extract_date(path: Path) -> date | None:
    """
    Extract the date from the file path using a regex pattern.
    """
    _DATE_PATTERN = re.compile(r"\b\d{2,4}-\d{2}-\d{2,4}\b")
    _DATE_FORMATS = (
        "%Y-%m-%d",  # YYYY-MM-DD
        "%y-%m-%d",  # YY-MM-DD
        "%d-%m-%Y",  # DD-MM-YYYY
        "%d-%m-%y",  # DD-MM-YY
    )
    match = _DATE_PATTERN.search(str(path))
    
    if not match:
        return None
    
    value = match.group()

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    
    return None


def compute_sha256(path: Path) -> bytes:
    """
    Compute the SHA-256 hash of the file at the given path.
    Returns raw bytes of the hash (32 bytes).
    """
    _CHUNK = 1024 * 1024  # Read in 1 MB chunks
    sha256_hash = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while chunk := f.read(_CHUNK):
                sha256_hash.update(chunk)
        return sha256_hash.digest()
    except OSError as e:
        raise PipelineError(f"Failed to read file for hashing: {path}") from e
