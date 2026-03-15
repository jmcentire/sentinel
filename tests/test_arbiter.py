"""Tests for Arbiter trust event client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from sentinel.arbiter import ArbiterClient
from sentinel.config import ArbiterConfig


class TestArbiterClient:
    def test_not_configured(self):
        client = ArbiterClient(ArbiterConfig())
        assert client.is_configured() is False

    def test_configured(self):
        client = ArbiterClient(ArbiterConfig(api_endpoint="http://localhost:7700"))
        assert client.is_configured() is True

    @pytest.mark.asyncio
    async def test_report_returns_false_when_unconfigured(self):
        client = ArbiterClient(ArbiterConfig())
        result = await client.report_trust_event("comp", "fix", 1.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_report_fix_success_payload(self):
        client = ArbiterClient(ArbiterConfig(
            api_endpoint="http://localhost:7700",
            trust_event_on_fix=True,
        ))
        client._post = AsyncMock(return_value=True)

        result = await client.report_fix_success("auth", run_id="fix123")
        assert result is True
        client._post.assert_called_once()
        url, payload = client._post.call_args[0]
        assert "/trust/event" in url
        assert payload["node_id"] == "auth"
        assert payload["event"] == "sentinel_fix"
        assert payload["weight"] == 1.5

    @pytest.mark.asyncio
    async def test_report_fix_failure_payload(self):
        client = ArbiterClient(ArbiterConfig(
            api_endpoint="http://localhost:7700",
            trust_event_on_fix=True,
        ))
        client._post = AsyncMock(return_value=True)

        result = await client.report_fix_failure("auth", run_id="fix123")
        assert result is True
        _, payload = client._post.call_args[0]
        assert payload["event"] == "sentinel_fix_failure"
        assert payload["weight"] == -0.5

    @pytest.mark.asyncio
    async def test_report_production_error_payload(self):
        client = ArbiterClient(ArbiterConfig(api_endpoint="http://localhost:7700"))
        client._post = AsyncMock(return_value=True)

        result = await client.report_production_error("auth")
        assert result is True
        _, payload = client._post.call_args[0]
        assert payload["event"] == "production_error"
        assert payload["weight"] == -0.3

    @pytest.mark.asyncio
    async def test_fix_success_skipped_when_trust_disabled(self):
        client = ArbiterClient(ArbiterConfig(
            api_endpoint="http://localhost:7700",
            trust_event_on_fix=False,
        ))
        result = await client.report_fix_success("auth")
        assert result is False

    @pytest.mark.asyncio
    async def test_post_failure_returns_false(self):
        client = ArbiterClient(ArbiterConfig(api_endpoint="http://localhost:7700"))
        client._post = AsyncMock(return_value=False)

        result = await client.report_trust_event("comp", "fix", 1.0)
        assert result is False
