"""Tests for signal ingestion, fingerprinting, deduplication, and retry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sentinel.config import SourceConfig
from sentinel.schemas import Signal
from sentinel.watcher import (
    CloudWatchSource,
    LogTailer,
    SignalIngester,
    fingerprint_signal,
    _extract_key_str,
)


class TestFingerprintSignal:
    def test_same_error_different_timestamps(self):
        s1 = Signal(
            source="log_file",
            raw_text="2024-01-01T12:00:00 ERROR: division by zero at line 42",
            timestamp="2024-01-01T12:00:00",
        )
        s2 = Signal(
            source="log_file",
            raw_text="2024-06-15T08:30:00 ERROR: division by zero at line 42",
            timestamp="2024-06-15T08:30:00",
        )
        assert fingerprint_signal(s1) == fingerprint_signal(s2)

    def test_different_errors(self):
        s1 = Signal(source="log_file", raw_text="ERROR: division by zero", timestamp="t")
        s2 = Signal(source="log_file", raw_text="ERROR: index out of range", timestamp="t")
        assert fingerprint_signal(s1) != fingerprint_signal(s2)

    def test_strips_line_numbers(self):
        s1 = Signal(source="log_file", raw_text="ERROR: failure at file.py:42", timestamp="t")
        s2 = Signal(source="log_file", raw_text="ERROR: failure at file.py:99", timestamp="t")
        assert fingerprint_signal(s1) == fingerprint_signal(s2)

    def test_strips_memory_addresses(self):
        s1 = Signal(source="log_file", raw_text="ERROR: object at 0x7fff12345678 is None", timestamp="t")
        s2 = Signal(source="log_file", raw_text="ERROR: object at 0xdeadbeef0000 is None", timestamp="t")
        assert fingerprint_signal(s1) == fingerprint_signal(s2)

    def test_deterministic(self):
        s = Signal(source="log_file", raw_text="ERROR: something", timestamp="t")
        assert fingerprint_signal(s) == fingerprint_signal(s)

    def test_hash_is_16_chars(self):
        s = Signal(source="log_file", raw_text="ERROR: test", timestamp="t")
        assert len(fingerprint_signal(s)) == 16


class TestExtractKeyStr:
    def test_extracts_key(self):
        assert _extract_key_str("[PACT:auth:validate] ERROR") == "PACT:auth:validate"

    def test_no_key(self):
        assert _extract_key_str("ERROR: no key here") == ""


class TestSignalIngesterDedup:
    def test_same_signal_deduped(self):
        ingester = SignalIngester([], dedup_window_seconds=300)
        s1 = Signal(source="log_file", raw_text="ERROR: test error", timestamp="t1")
        s2 = Signal(source="log_file", raw_text="ERROR: test error", timestamp="t2")
        assert ingester._deduplicate(s1) is True
        assert ingester._deduplicate(s2) is False

    def test_different_signals_not_deduped(self):
        ingester = SignalIngester([], dedup_window_seconds=300)
        s1 = Signal(source="log_file", raw_text="ERROR: first", timestamp="t1")
        s2 = Signal(source="log_file", raw_text="ERROR: second completely different", timestamp="t2")
        assert ingester._deduplicate(s1) is True
        assert ingester._deduplicate(s2) is True


class TestLogTailerRetry:
    """FA-S-024: Log source unavailability handled with retry and backoff."""

    def test_tailer_has_max_backoff(self):
        tailer = LogTailer("/nonexistent/log")
        assert tailer.MAX_BACKOFF == 60

    def test_tailer_stop_sets_flag(self):
        tailer = LogTailer("/nonexistent/log")
        assert tailer._stopped is False
        tailer.stop()
        assert tailer._stopped is True

    def test_tailer_handles_missing_file_gracefully(self):
        """LogTailer should not crash on init with a nonexistent file."""
        tailer = LogTailer("/nonexistent/path/to/log.log")
        assert tailer.path == "/nonexistent/path/to/log.log"
        # stop should not raise even without starting
        tailer.stop()


class TestCloudWatchSource:
    """Tests for CloudWatch log source configuration and behavior."""

    def test_init_defaults(self):
        cw = CloudWatchSource(log_group="/aws/lambda/test")
        assert cw.log_group == "/aws/lambda/test"
        assert cw.filter_pattern == ""
        assert cw.region == ""
        assert cw.poll_interval == 30
        assert cw._last_timestamp == 0
        assert cw._stopped is False

    def test_init_custom_params(self):
        cw = CloudWatchSource(
            log_group="/aws/ecs/my-service",
            filter_pattern="ERROR",
            region="eu-west-1",
            poll_interval=60,
            error_patterns=["FATAL", "PANIC"],
        )
        assert cw.log_group == "/aws/ecs/my-service"
        assert cw.filter_pattern == "ERROR"
        assert cw.region == "eu-west-1"
        assert cw.poll_interval == 60
        assert len(cw._patterns) == 2

    def test_stop_sets_flag(self):
        cw = CloudWatchSource(log_group="/aws/lambda/test")
        assert cw._stopped is False
        cw.stop()
        assert cw._stopped is True

    def test_get_client_raises_without_boto3(self):
        cw = CloudWatchSource(log_group="/aws/lambda/test")
        with patch.dict("sys.modules", {"boto3": None}):
            try:
                cw._client = None
                cw._get_client()
                assert False, "Should have raised"
            except RuntimeError as e:
                assert "boto3" in str(e)
                assert "cloudwatch" in str(e)

    def test_get_client_with_region(self):
        cw = CloudWatchSource(log_group="/test", region="us-west-2")
        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            cw._client = None
            result = cw._get_client()
            mock_boto3.client.assert_called_once_with(
                service_name="logs",
                region_name="us-west-2",
            )
            assert result is mock_client

    def test_get_client_without_region(self):
        cw = CloudWatchSource(log_group="/test", region="")
        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            cw._client = None
            result = cw._get_client()
            mock_boto3.client.assert_called_once_with(service_name="logs")
            assert result is mock_client


class TestSignalIngesterCloudWatch:
    """Test SignalIngester with CloudWatch source configuration."""

    def test_ingester_tracks_cloudwatch_sources(self):
        sources = [
            SourceConfig(
                type="cloudwatch",
                log_group="/aws/lambda/my-func",
                filter_pattern="ERROR",
                region="us-east-1",
                poll_interval=15,
            ),
        ]
        ingester = SignalIngester(sources)
        assert ingester._cloudwatch_sources == []  # not started yet
        assert len(ingester._sources) == 1
        assert ingester._sources[0].type == "cloudwatch"
        assert ingester._sources[0].log_group == "/aws/lambda/my-func"

    def test_ingester_handles_mixed_sources(self):
        sources = [
            SourceConfig(type="file", path="/var/log/app.log"),
            SourceConfig(
                type="cloudwatch",
                log_group="/aws/lambda/test",
                filter_pattern="ERROR",
            ),
            SourceConfig(type="webhook", port=9090),
        ]
        ingester = SignalIngester(sources)
        assert len(ingester._sources) == 3

    def test_ingester_stop_cleans_cloudwatch(self):
        """Stop should clean up CloudWatch sources."""
        cw = CloudWatchSource(log_group="/test")
        ingester = SignalIngester([])
        ingester._cloudwatch_sources.append(cw)
        ingester.stop()
        assert cw._stopped is True
