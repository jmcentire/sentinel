"""Arbiter trust ledger HTTP client — reports trust events after fixes."""

from __future__ import annotations

import logging
from datetime import datetime

import aiohttp

from sentinel.config import ArbiterConfig

logger = logging.getLogger(__name__)


class ArbiterClient:
    """Posts trust events to the Arbiter API. Fire-and-forget."""

    def __init__(self, config: ArbiterConfig) -> None:
        self._endpoint = config.api_endpoint
        self._trust_on_fix = config.trust_event_on_fix

    def is_configured(self) -> bool:
        return self._endpoint is not None

    async def report_trust_event(
        self,
        node_id: str,
        event: str,
        weight: float,
        run_id: str = "",
    ) -> bool:
        """POST /trust/event. Returns True on success, False on failure."""
        if not self.is_configured():
            return False

        payload = {
            "node_id": node_id,
            "event": event,
            "weight": weight,
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
        }

        return await self._post(f"{self._endpoint}/trust/event", payload)

    async def _post(self, url: str, payload: dict) -> bool:
        """POST JSON to a URL. Returns True on 2xx."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status < 300:
                        return True
                    logger.debug("Arbiter returned %d", resp.status)
                    return False
        except Exception as e:
            logger.debug("Arbiter request failed: %s", e)
            return False

    async def report_fix_success(self, component_id: str, run_id: str = "") -> bool:
        """Report a successful fix (trust boost)."""
        if not self._trust_on_fix:
            return False
        return await self.report_trust_event(
            node_id=component_id,
            event="sentinel_fix",
            weight=1.5,
            run_id=run_id,
        )

    async def report_fix_failure(self, component_id: str, run_id: str = "") -> bool:
        """Report a failed fix (trust penalty)."""
        if not self._trust_on_fix:
            return False
        return await self.report_trust_event(
            node_id=component_id,
            event="sentinel_fix_failure",
            weight=-0.5,
            run_id=run_id,
        )

    async def report_production_error(
        self,
        component_id: str,
        run_id: str = "",
    ) -> bool:
        """Report production error detection (trust reduction)."""
        return await self.report_trust_event(
            node_id=component_id,
            event="production_error",
            weight=-0.3,
            run_id=run_id,
        )
