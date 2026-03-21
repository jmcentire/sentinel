"""Tests for Chronicler incident lifecycle emitter."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sentinel.chronicler import ChroniclerEmitter
from sentinel.config import ChroniclerConfig, SentinelConfig
from sentinel.schemas import Incident, Signal


def _make_incident(**overrides) -> Incident:
    """Build a minimal Incident for testing."""
    defaults = {
        "id": "inc-001",
        "status": "resolved",
        "component_id": "auth",
        "pact_key": "PACT:auth:validate",
        "severity": "high",
        "signals": [Signal(
            source="log_file",
            raw_text="Token expired",
            timestamp="2025-01-01T00:00:00",
        )],
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:05:00",
        "spend_usd": 1.25,
    }
    defaults.update(overrides)
    return Incident(**defaults)


class TestChroniclerConfig:
    def test_disabled_by_default(self):
        config = SentinelConfig()
        assert config.chronicler.chronicler_enabled is False

    def test_default_endpoint(self):
        config = ChroniclerConfig()
        assert config.chronicler_endpoint == "http://localhost:8485"

    def test_config_from_dict(self):
        config = ChroniclerConfig(chronicler_enabled=True, chronicler_endpoint="http://host:9000")
        assert config.chronicler_enabled is True
        assert config.chronicler_endpoint == "http://host:9000"


class TestChroniclerEmitter:
    def test_not_configured_when_disabled(self):
        emitter = ChroniclerEmitter(ChroniclerConfig())
        assert emitter.is_configured() is False

    def test_configured_when_enabled(self):
        emitter = ChroniclerEmitter(ChroniclerConfig(chronicler_enabled=True))
        assert emitter.is_configured() is True

    @pytest.mark.asyncio
    async def test_emit_returns_false_when_disabled(self):
        emitter = ChroniclerEmitter(ChroniclerConfig())
        incident = _make_incident()
        result = await emitter.emit(incident)
        assert result is False

    @pytest.mark.asyncio
    async def test_resolved_incident_event_sequence(self):
        emitter = ChroniclerEmitter(ChroniclerConfig(chronicler_enabled=True))
        emitter._post = AsyncMock(return_value=True)

        incident = _make_incident(status="resolved")
        result = await emitter.emit(incident)

        assert result is True
        events = [call[0][1] for call in emitter._post.call_args_list]
        event_names = [e["event"] for e in events]
        assert event_names == [
            "incident.detected",
            "incident.triaging",
            "incident.remediating",
            "incident.resolved",
        ]

    @pytest.mark.asyncio
    async def test_escalated_incident_event_sequence(self):
        emitter = ChroniclerEmitter(ChroniclerConfig(chronicler_enabled=True))
        emitter._post = AsyncMock(return_value=True)

        incident = _make_incident(status="escalated")
        result = await emitter.emit(incident)

        assert result is True
        events = [call[0][1] for call in emitter._post.call_args_list]
        event_names = [e["event"] for e in events]
        assert event_names == [
            "incident.detected",
            "incident.triaging",
            "incident.remediating",
            "incident.escalated",
        ]

    @pytest.mark.asyncio
    async def test_detected_only_event_sequence(self):
        emitter = ChroniclerEmitter(ChroniclerConfig(chronicler_enabled=True))
        emitter._post = AsyncMock(return_value=True)

        incident = _make_incident(status="detected")
        result = await emitter.emit(incident)

        assert result is True
        events = [call[0][1] for call in emitter._post.call_args_list]
        event_names = [e["event"] for e in events]
        assert event_names == ["incident.detected"]

    @pytest.mark.asyncio
    async def test_event_payload_fields(self):
        emitter = ChroniclerEmitter(ChroniclerConfig(chronicler_enabled=True))
        emitter._post = AsyncMock(return_value=True)

        incident = _make_incident()
        await emitter.emit(incident)

        _, payload = emitter._post.call_args_list[0][0]
        assert payload["incident_id"] == "inc-001"
        assert payload["component_id"] == "auth"
        assert payload["pact_key"] == "PACT:auth:validate"
        assert payload["severity"] == "high"
        assert payload["signal_count"] == 1
        assert payload["spend_usd"] == 1.25

    @pytest.mark.asyncio
    async def test_posts_to_events_endpoint(self):
        emitter = ChroniclerEmitter(ChroniclerConfig(
            chronicler_enabled=True,
            chronicler_endpoint="http://myhost:9000",
        ))
        emitter._post = AsyncMock(return_value=True)

        await emitter.emit(_make_incident(status="detected"))
        url = emitter._post.call_args_list[0][0][0]
        assert url == "http://myhost:9000/events"

    @pytest.mark.asyncio
    async def test_fire_and_forget_on_post_failure(self):
        """Chronicler unavailability does not raise."""
        emitter = ChroniclerEmitter(ChroniclerConfig(chronicler_enabled=True))
        emitter._post = AsyncMock(return_value=False)

        incident = _make_incident()
        result = await emitter.emit(incident)
        # Returns False but does NOT raise
        assert result is False

    @pytest.mark.asyncio
    async def test_fire_and_forget_unreachable_endpoint(self):
        """Real HTTP to unreachable host returns False, does not raise."""
        emitter = ChroniclerEmitter(ChroniclerConfig(
            chronicler_enabled=True,
            chronicler_endpoint="http://127.0.0.1:1",
        ))

        incident = _make_incident(status="detected")
        result = await emitter.emit(incident)
        assert result is False
