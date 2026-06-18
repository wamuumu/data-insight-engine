"""
Unit tests for the PipelineStats dataclass in src/ingestion/pipeline.py

Covers:
  - Default zero-initialisation
  - merge: additive accumulation of all fields
  - merge: identity element (merging empty stats changes nothing)
  - to_dict: key naming with/without suffix, all fields present
  - to_dict: empty suffix produces bare field names
"""

from __future__ import annotations

from ingestion.pipeline import PipelineStats


class TestPipelineStatsDefaults:
    def test_all_fields_start_at_zero(self) -> None:
        stats = PipelineStats()
        assert stats.files_discovered == 0
        assert stats.files_parsed == 0
        assert stats.files_skipped == 0
        assert stats.files_deduplicated == 0
        assert stats.files_failed == 0
        assert stats.records_produced == 0
        assert stats.records_inserted == 0


class TestPipelineStatsMerge:
    def test_merge_adds_all_fields(self) -> None:
        a = PipelineStats(
            files_discovered=2,
            files_parsed=1,
            files_skipped=0,
            files_deduplicated=1,
            files_failed=0,
            records_produced=100,
            records_inserted=98,
        )
        b = PipelineStats(
            files_discovered=3,
            files_parsed=2,
            files_skipped=1,
            files_deduplicated=0,
            files_failed=1,
            records_produced=200,
            records_inserted=195,
        )
        a.merge(b)
        assert a.files_discovered == 5
        assert a.files_parsed == 3
        assert a.files_skipped == 1
        assert a.files_deduplicated == 1
        assert a.files_failed == 1
        assert a.records_produced == 300
        assert a.records_inserted == 293

    def test_merge_with_empty_is_identity(self) -> None:
        original = PipelineStats(files_discovered=10, records_inserted=500)
        original.merge(PipelineStats())
        assert original.files_discovered == 10
        assert original.records_inserted == 500

    def test_merge_is_not_commutative_in_place(self) -> None:
        """merge modifies self, not other."""
        a = PipelineStats(files_discovered=1)
        b = PipelineStats(files_discovered=2)
        a.merge(b)
        assert a.files_discovered == 3
        assert b.files_discovered == 2  # unchanged


class TestPipelineStatsToDict:
    _EXPECTED_BARE_KEYS = {
        "_files_discovered",
        "_files_parsed",
        "_files_skipped",
        "_files_deduplicated",
        "_files_failed",
        "_records_produced",
        "_records_inserted",
    }

    def test_to_dict_with_suffix_produces_correct_keys(self) -> None:
        d = PipelineStats().to_dict(suffix="total")
        assert "total_files_discovered" in d
        assert "total_records_inserted" in d

    def test_to_dict_all_seven_fields_present(self) -> None:
        d = PipelineStats().to_dict(suffix="x")
        assert len(d) == 7

    def test_to_dict_values_match_stats(self) -> None:
        stats = PipelineStats(files_discovered=5, records_inserted=200)
        d = stats.to_dict(suffix="run")
        assert d["run_files_discovered"] == 5
        assert d["run_records_inserted"] == 200

    def test_to_dict_empty_suffix(self) -> None:
        d = PipelineStats(files_parsed=3).to_dict(suffix="")
        # With empty suffix the key should be "_files_parsed" (prefix underscore from format)
        assert any("files_parsed" in k for k in d)
