import re
from pathlib import Path

def extract_serial_number(path: Path) -> str | None:
    """
    Extract the serial number from the file path using a regex pattern.
    The serial number is expected to be in the format 'B' followed by 8 hexadecimal characters.
    """
    _SN_PATTERN = re.compile(r"(B[0-9A-F]{8})")
    match = _SN_PATTERN.search(str(path))
    return match.group() if match else None