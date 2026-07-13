class ApplicationError(Exception):
    """Base class for all application-specific errors."""


# --------------------------------------------------------------------------- #
# Recoverable, per-file errors.
# --------------------------------------------------------------------------- #


class FileProcessingError(ApplicationError):
    """Base class for errors tied to processing a single file. Safe to skip."""


class PipelineError(FileProcessingError):
    """A file could not be discovered, read or hashed from the source drive."""


class ParsingError(FileProcessingError):
    """A file's structure or content could not be parsed into a DataFrame."""


class TimestampCleaningError(ParsingError):
    """The timestamp-cleaning pipeline could not reconcile the log stream."""


class FirmwareLookupError(ParsingError):
    """Firmware version lookup failed for one or more rows in the DataFrame."""


# --------------------------------------------------------------------------- #
# Non recoverable, infrastructure errors.
# --------------------------------------------------------------------------- #


class InfrastructureError(ApplicationError):
    """Base class for system-level failures unrelated to a specific file."""


class ConfigurationError(InfrastructureError):
    """The application configuration is invalid or incomplete."""


class DatabaseRetryTimeout(InfrastructureError):
    """The retry deadline was reached before a database operation succeeded."""


class QuarantineFailure(InfrastructureError):
    """Failed to record a file's failure state in the database (double-failure)."""
