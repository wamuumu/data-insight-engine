# Event IDs for firmware version tracking
SWITCH_ON_EVENT_ID = 1
SWITCH_OFF_EVENT_ID = 2

# Sentinel value for undefined firmware version
UNDEFINED_FIRMWARE_VERSION = -1

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
