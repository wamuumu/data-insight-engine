from enum import IntEnum

class EventID(IntEnum):
    SWITCH_ON = 1
    SWITCH_OFF = 2
    RTC_SET = 11
    HL_DOWNLOAD = 45
    MISS_LOGS = 100
    RTC_RESET = 101
    RTC_GUESS = 102
    RTC_MISS_START = 103
    RTC_MISS_END = 104

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
