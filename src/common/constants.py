from enum import IntEnum

class EventID(IntEnum):
    SWITCH_ON = 1
    SWITCH_OFF = 2
    RTC_SET = 11
    HL_DOWNLOAD = 45
    RTC_RESET = 100
    MISS_LOGS = 101
    MISS_DATA_START = 102
    MISS_DATA_END = 103
    GUESS_DATA = 104

# File extensions supported by the system
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".xlsx", ".parquet"})

# Columns to drop from Parquet files during parsing
PARQUET_DROP_COLUMNS: frozenset[str] = frozenset(
    {
        "counter",
        "extDataPresent",
        "free_1",
        "free_2",
        "free_3",
        "free_4",
    }
)
