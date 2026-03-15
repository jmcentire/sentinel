"""Tests for Stigmergy signal emission client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sentinel.config import StigmergyConfig
from sentinel.stigmergy import StigmergyClient


class TestStigmergyClient:
    def test_not_configured(self):
        client = StigmergyClient(StigmergyConfig())
        assert client.is_configured() is False

    def test_configured(self):
        client = StigmergyClient(StigmergyConfig(endpoint="http://localhost:8800"))
        assert client.is_configured() is True

    @pytest.mark.asyncio
    async def test_emit_returns_false_when_unconfigured(self):
        client = StigmergyClient(StigmergyConfig())
        result = await client.emit_signal("test", "actor", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_emit_fix_applied(self):
        client = StigmergyClient(StigmergyConfig(endpoint="http://localhost:8800"))
        client._post = AsyncMock(return_value=True)

        result = await client.emit_fix_applied("auth", "PACT:auth:validate", "Token error")
        assert result is True
        client._post.assert_called_once()
        url, payload = client._post.call_args[0]
        assert "/signals" in url
        assert payload["source"] == "sentinel"
        assert payload["type"] == "fix_applied"
        assert payload["actor"] == "auth"

    @pytest.mark.asyncio
    async def test_emit_fix_failed(self):
        client = StigmergyClient(StigmergyConfig(endpoint="http://localhost:8800"))
        client._post = AsyncMock(return_value=True)

        result = await client.emit_fix_failed("auth", "PACT:auth:validate", "error")
        assert result is True
        _, payload = client._post.call_args[0]
        assert payload["type"] == "fix_failed"

    @pytest.mark.asyncio
    async def test_emit_production_error(self):
        client = StigmergyClient(StigmergyConfig(endpoint="http://localhost:8800"))
        client._post = AsyncMock(return_value=True)

        result = await client.emit_production_error("auth", "PACT:auth:validate", "error")
        assert result is True
        _, payload = client._post.call_args[0]
        assert payload["type"] == "production_error"

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        """FA-S-021: Stigmergy unavailability does not affect Sentinel."""
        client = StigmergyClient(StigmergyConfig(endpoint="http://localhost:8800"))
        client._post = AsyncMock(return_value=False)

        result = await client.emit_signal("test", "actor", {})
        assert result is False
