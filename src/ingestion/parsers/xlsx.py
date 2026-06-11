import re
import logging
from typing import Generator

import openpyxl

from ingestion.crawler.base import BaseFile
from ingestion.parsers.base import BaseParser, ParsedRecord

logger = logging.getLogger(__name__)

class XLSXParser(BaseParser):
    """
    Parser for XLSX files.
    """

    # TODO: Add firmware label to each row (search between ON and OFF)
    # TODO: Prepend to each row the serial number of the device (search in filename using regex something like "B" + 8 hexadecimal characters)
    # TODO: Create a local postgres database and insert all the records there (use SQLAlchemy and migrations)

    CHUNK_SIZE = 100  # Number of rows to read at a time to manage memory usage

    def can_handle(self, file: BaseFile) -> bool:
        """
        Check if the file is an XLSX file based on its extension.
        """
        return file.suffix == ".xlsx"
    
    def parse(self, file: BaseFile) -> Generator[ParsedRecord, None, None]:
        """
        Parse the XLSX file and yield records as dictionaries.
        """
        logger.info(f"Parsing XLSX file: {file.path} (size: {file.size / 1e6:.2f} MB)")

        # Extract SN from filename using regex (e.g., "B" followed by 8 hexadecimal characters)
        sn_match = re.search(r"(B[0-9A-F]{8})", str(file.path))
        sn = sn_match.group() if sn_match else None
        
        try:
            workbook = openpyxl.load_workbook(file.path, read_only=True, data_only=True)
        except Exception as e:
            logger.error(f"Failed to open XLSX file: {file.path}, error: {e}")
            raise
        
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            rows = sheet.iter_rows(values_only=True)

            # Read header, assuming the first row contains column names
            try:
                header = [str(h).strip() if h is not None else f"column_{i}" for i, h in enumerate(next(rows))]
            except StopIteration:
                logger.warning(f"Sheet {sheet_name} in file {file.path} is empty, skipping.")
                continue

            for row in rows:
                if all(cell is None for cell in row):
                    continue  # Skip empty rows

                record_data = dict(zip(header, row))
                record_data["Serial Number"] = sn

                yield ParsedRecord(source_file=file.path, record_type="history_log", data=record_data)
        
        workbook.close()