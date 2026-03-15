"""Tests for webhook notification sender."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sentinel.config import NotifyConfig
from sentinel.notify import Notifier


class TestNotifier:
    def test_not_configured(self):
        n = Notifier(NotifyConfig())
        assert n.is_configured() is False

    def test_configured(self):
        n = Notifier(NotifyConfig(webhook_url="http://localhost:9999/hook"))
        assert n.is_configured() is True

    @pytest.mark.asyncio
    async def test_unconfigured_returns_false(self):
        n = Notifier(NotifyConfig())
        assert await n.notify("error", {"msg": "test"}) is False

    @pytest.mark.asyncio
    async def test_filters_disabled_events(self):
        n = Notifier(NotifyConfig(webhook_url="http://hook", on_error=False))
        assert await n.notify("error", {}) is False

    @pytest.mark.asyncio
    async def test_sends_enabled_events(self):
        n = Notifier(NotifyConfig(webhook_url="http://hook", on_fix=True))
        n._post = AsyncMock(return_value=True)

        result = await n.notify("fix", {"component": "auth"})
        assert result is True
        n._post.assert_called_once()

    @pytest.mark.asyncio
    async def test_payload_structure(self):
        n = Notifier(NotifyConfig(webhook_url="http://hook", on_error=True))
        n._post = AsyncMock(return_value=True)

        await n.notify("error", {"incident_id": "inc123"})
        url, payload = n._post.call_args[0]
        assert payload["event_type"] == "error"
        assert payload["source"] == "sentinel"
        assert payload["incident_id"] == "inc123"
