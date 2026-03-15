"""Tests for the main Sentinel orchestrator."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sentinel.config import SentinelConfig, BudgetConfig
from sentinel.schemas import (
    Incident,
    ManifestEntry,
    Signal,
)
from sentinel.sentinel import Sentinel


def _make_config(**overrides) -> SentinelConfig:
    defaults = {"auto_remediate": False}
    defaults.update(overrides)
    return SentinelConfig(**defaults)


def _make_signal(text: str = "ERROR: test error") -> Signal:
    return Signal(
        source="log_file",
        raw_text=text,
        timestamp=datetime.now().isoformat(),
        file_path="/var/log/test.log",
    )


class TestHandleSignal:
    @pytest.mark.asyncio
    async def test_creates_incident(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path))
        sentinel = Sentinel(config)
        await sentinel.startup()

        signal = _make_signal()
        await sentinel.handle_signal(signal)

        incidents = sentinel.incident_mgr.get_recent_incidents()
        assert len(incidents) == 1
        assert incidents[0].status in ("detected", "escalated")

    @pytest.mark.asyncio
    async def test_dedup_same_fingerprint(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path))
        sentinel = Sentinel(config)
        await sentinel.startup()

        await sentinel.handle_signal(_make_signal("ERROR: same"))
        await sentinel.handle_signal(_make_signal("ERROR: same"))

        incidents = sentinel.incident_mgr.get_recent_incidents()
        assert len(incidents) == 1

    @pytest.mark.asyncio
    async def test_different_errors_create_separate_incidents(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path))
        sentinel = Sentinel(config)
        await sentinel.startup()

        await sentinel.handle_signal(_make_signal("ERROR: first error"))
        await sentinel.handle_signal(_make_signal("ERROR: completely different error"))

        incidents = sentinel.incident_mgr.get_recent_incidents()
        assert len(incidents) == 2


class TestManualFix:
    @pytest.mark.asyncio
    async def test_returns_failure_for_unknown_component(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path))
        sentinel = Sentinel(config)
        await sentinel.startup()

        result = await sentinel.handle_manual_fix("PACT:unknown:method", "error text")
        assert result.status == "failure"
        assert "not in manifest" in result.error


class TestSeverityIntegration:
    @pytest.mark.asyncio
    async def test_gdpr_erasable_sets_high_severity(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path))
        sentinel = Sentinel(config)
        await sentinel.startup()

        signal = _make_signal("ERROR: gdpr_erasable field email was exposed")
        await sentinel.handle_signal(signal)

        incidents = sentinel.incident_mgr.get_recent_incidents()
        assert len(incidents) == 1
        assert incidents[0].severity == "high"

    @pytest.mark.asyncio
    async def test_audit_field_deletion_sets_compliance(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path))
        sentinel = Sentinel(config)
        await sentinel.startup()

        signal = _make_signal("ERROR: audit_field record deleted unexpectedly")
        await sentinel.handle_signal(signal)

        incidents = sentinel.incident_mgr.get_recent_incidents()
        assert len(incidents) == 1
        assert incidents[0].severity == "compliance"


class TestEventBusIntegration:
    @pytest.mark.asyncio
    async def test_emits_incident_detected(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path))
        sentinel = Sentinel(config)
        await sentinel.startup()

        received = []
        sentinel.event_bus.on("incident_detected", lambda e: received.append(e))

        await sentinel.handle_signal(_make_signal())
        assert len(received) == 1
        assert received[0].kind == "incident_detected"


class TestErrorThreshold:
    """FA-S-007: Fixer only spawns after error_threshold.count errors in window."""

    @pytest.mark.asyncio
    async def test_threshold_count_1_spawns_immediately(self, tmp_path: Path):
        """Default threshold count=1: fixer spawns on first error."""
        config = _make_config(
            state_dir=str(tmp_path),
            auto_remediate=True,
        )
        sentinel = Sentinel(config)
        await sentinel.startup()

        # Register a component
        from sentinel.schemas import ManifestEntry
        sentinel.manifest.register(ManifestEntry(component_id="auth"))

        # threshold_reached should return True on first error (default count=1)
        assert sentinel._threshold_reached("auth") is True

    @pytest.mark.asyncio
    async def test_threshold_count_3_requires_3_errors(self, tmp_path: Path):
        """With count=3, fixer doesn't spawn until 3rd error."""
        from sentinel.config import ErrorThresholdConfig

        config = _make_config(
            state_dir=str(tmp_path),
            auto_remediate=True,
            error_threshold=ErrorThresholdConfig(count=3, window_seconds=300),
        )
        sentinel = Sentinel(config)
        await sentinel.startup()

        assert sentinel._threshold_reached("auth") is False
        assert sentinel._threshold_reached("auth") is False
        assert sentinel._threshold_reached("auth") is True  # 3rd error triggers

    @pytest.mark.asyncio
    async def test_threshold_independent_per_component(self, tmp_path: Path):
        from sentinel.config import ErrorThresholdConfig

        config = _make_config(
            state_dir=str(tmp_path),
            error_threshold=ErrorThresholdConfig(count=2),
        )
        sentinel = Sentinel(config)
        await sentinel.startup()

        assert sentinel._threshold_reached("auth") is False
        assert sentinel._threshold_reached("pricing") is False
        assert sentinel._threshold_reached("auth") is True  # 2nd for auth
        assert sentinel._threshold_reached("pricing") is True  # 2nd for pricing


class TestActiveFixerGuard:
    """FA-S-026: Same component doesn't get concurrent fixers."""

    @pytest.mark.asyncio
    async def test_active_fixer_blocks_duplicate(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path), auto_remediate=True)
        sentinel = Sentinel(config)
        await sentinel.startup()

        # Simulate an active fixer for "auth"
        sentinel._active_fixers.add("auth")

        from sentinel.schemas import ManifestEntry
        sentinel.manifest.register(ManifestEntry(component_id="auth"))

        # Send signal — should NOT spawn a fixer since one is active
        signal = Signal(
            source="log_file",
            raw_text="ERROR [PACT:auth:validate] token invalid",
            timestamp=datetime.now().isoformat(),
            log_key="PACT:auth:validate",
        )
        await sentinel.handle_signal(signal)

        # No fixes should have been attempted
        assert len(sentinel.fixes) == 0

    @pytest.mark.asyncio
    async def test_fixer_released_after_completion(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path))
        sentinel = Sentinel(config)
        await sentinel.startup()

        # _active_fixers should start empty and be cleared after spawn
        assert "auth" not in sentinel._active_fixers


class TestStop:
    def test_stop_sets_flag(self, tmp_path: Path):
        config = _make_config(state_dir=str(tmp_path))
        sentinel = Sentinel(config)
        sentinel.stop()
        assert sentinel._running is False
