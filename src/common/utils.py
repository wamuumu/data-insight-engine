import re
import hashlib
from pathlib import Path
from datetime import datetime, date, time, timezone


def extract_serial_number(path: Path) -> str | None:
    """
    Extract the serial number from the file path using a regex pattern.
    The serial number is expected to be in the format 'B' followed by 8 hexadecimal characters.
    """
    _SN_PATTERN = re.compile(r"(B[0-9A-F]{8})")
    match = _SN_PATTERN.search(str(path))
    return match.group() if match else None


def extract_date(path: Path) -> date | None:
    """
    Extract the date from the file path using a regex pattern.
    """
    _DATE_PATTERN = re.compile(r"(?P<ymd>\d{4}-\d{2}-\d{2})|(?P<dmy>\d{2}-\d{2}-\d{2})")
    match = _DATE_PATTERN.search(str(path))
    
    if not match:
        return None

    if match.group("ymd"):
        return datetime.strptime(match.group("ymd"), "%Y-%m-%d").date()

    return datetime.strptime(match.group("dmy"), "%d-%m-%y").date()


def compute_sha256(path: Path) -> bytes | None:
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
    except OSError:
        return None


def combine_date_time(
    date_str: str, time_str: str, format_str: str = "%d/%m/%Y %H:%M:%S.%f"
) -> datetime:
    """
    Combine date and time strings into a single datetime object.
    """
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", format_str)
    except ValueError:
        dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M:%S")

    return dt.replace(tzinfo=timezone.utc)


def construct_time(hour: int, minute: int, second: int, centisecond: int) -> time:
    """
    Construct a datetime.time object from hour, minute, second, and centisecond components.
    """
    microsecond = min(max(centisecond, 0), 99) * 10_000
    return time(hour=hour, minute=minute, second=second, microsecond=microsecond)
