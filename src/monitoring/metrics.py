from enum import StrEnum

from prometheus_client import Counter, Gauge, Histogram


class MetricStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    INCOMPLETE = "incomplete"
    DEDUPLICATED = "deduplicated"


# ── File-level counters ───────────────────────────────────────
files_processed = Counter(
    "die_files_processed_total",
    "Total number of files processed by the ingestion pipeline.",
    labelnames=["status", "file_type"],
)

# ── Record-level counters ─────────────────────────────────────
records_ingested = Counter(
    "die_records_ingested_total",
    "Total number of records successfully written to the database.",
    labelnames=["table"],
)

# ── Latency histograms ────────────────────────────────────────
file_processing_duration = Histogram(
    "die_file_processing_duration_seconds",
    "Wall-clock time to fully parse and persist a single file.",
    labelnames=["file_type"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600, 1800],
)

# ── Pipeline-level gauges ─────────────────────────────────────
pipeline_last_run = Gauge(
    "die_pipeline_last_run_timestamp_seconds",
    "Timestamp of the last completed pipeline run.",
)

pipeline_active = Gauge(
    "die_pipeline_active",
    "Whether the ingestion pipeline is currently running (1) or idle (0).",
)
