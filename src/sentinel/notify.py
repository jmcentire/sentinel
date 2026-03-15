"""Webhook notification sender — POSTs fix/error/contract events."""

from __future__ import annotations

import logging
from datetime import datetime

import aiohttp

from sentinel.config import NotifyConfig

logger = logging.getLogger(__name__)


class Notifier:
    """Sends webhook notifications for configured event types."""

    def __init__(self, config: NotifyConfig) -> None:
        self._url = config.webhook_url
        self._on_error = config.on_error
        self._on_fix = config.on_fix
        self._on_contract_push = config.on_contract_push

    def is_configured(self) -> bool:
        return self._url is not None

    async def notify(self, event_type: str, payload: dict) -> bool:
        """Send notification if event_type is enabled. Returns True on success."""
        if not self.is_configured():
            return False

        if event_type == "error" and not self._on_error:
            return False
        if event_type == "fix" and not self._on_fix:
            return False
        if event_type == "contract_push" and not self._on_contract_push:
            return False

        envelope = {
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "source": "sentinel",
            **payload,
        }

        return await self._post(self._url, envelope)

    async def _post(self, url: str, payload: dict) -> bool:
        """POST JSON. Returns True on 2xx."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status >= 300:
                        logger.debug("Webhook returned %d", resp.status)
                        return False
                    return True
        except Exception as e:
            logger.debug("Webhook notification failed: %s", e)
            return False
