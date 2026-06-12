import re
import hashlib
from pathlib import Path

def extract_serial_number(path: Path) -> str | None:
    """
    Extract the serial number from the file path using a regex pattern.
    The serial number is expected to be in the format 'B' followed by 8 hexadecimal characters.
    """
    _SN_PATTERN = re.compile(r"(B[0-9A-F]{8})")
    match = _SN_PATTERN.search(str(path))
    return match.group() if match else None

def compute_sha256(path: Path) -> str:
    """
    Compute the SHA-256 hash of the file at the given path.
    """
    _CHUNK = 1024 * 1024  # Read in 1 MB chunks
    sha256_hash = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def fast_file_identity(path: Path) -> tuple[str, int, float]:
    """
    Return a (path, size, mtime) tuple for quick equality checks of file identity.
    """
    stat = path.stat()
    return (str(path), stat.st_size, stat.st_mtime)