# Event IDs for parsing and processing history logs
SWITCH_ON_EVENT_ID = 1
SWITCH_OFF_EVENT_ID = 2
RTC_SET_EVENT_ID = 11
RTC_RESET_EVENT_ID = -11
RTC_GUESSED_EVENT_ID = -12

# Firmware version fallback
UNDEFINED_FIRMWARE_VERSION = -1

# Epoch year used by device when RTC has not been set
EPOCH_YEAR = 2000

# Sentinel marker value
SENTINEL_VALUE = -1

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
