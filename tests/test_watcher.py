"""Tests for signal ingestion, fingerprinting, deduplication, and retry."""

from __future__ import annotations

from sentinel.config import SourceConfig
from sentinel.schemas import Signal
from sentinel.watcher import LogTailer, SignalIngester, fingerprint_signal, _extract_key_str


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
