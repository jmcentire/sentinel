"""Stigmergy signal emission — fire-and-forget POST to signal endpoint."""

from __future__ import annotations

import logging
from datetime import datetime

import aiohttp

from sentinel.config import StigmergyConfig

logger = logging.getLogger(__name__)


class StigmergyClient:
    """Emits signals to the Stigmergy endpoint. Fire-and-forget."""

    def __init__(self, config: StigmergyConfig) -> None:
        self._endpoint = config.endpoint

    def is_configured(self) -> bool:
        return self._endpoint is not None

    async def emit_signal(
        self,
        signal_type: str,
        actor: str,
        content: dict | None = None,
        weight: float = 1.0,
    ) -> bool:
        """POST /signals. Returns True on success. Never raises."""
        if not self.is_configured():
            return False

        payload = {
            "source": "sentinel",
            "type": signal_type,
            "actor": actor,
            "content": content or {},
            "weight": weight,
            "timestamp": datetime.now().isoformat(),
        }

        return await self._post(f"{self._endpoint}/signals", payload)

    async def _post(self, url: str, payload: dict) -> bool:
        """POST JSON. Returns True on 2xx. Never raises."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=2),
                ) as resp:
                    return resp.status < 300
        except Exception as e:
            logger.debug("Stigmergy signal failed (non-fatal): %s", e)
            return False

    async def emit_fix_applied(
        self, component_id: str, pact_key: str, error_summary: str,
        contract_changed: bool = False,
    ) -> bool:
        return await self.emit_signal(
            signal_type="fix_applied",
            actor=component_id,
            content={
                "pact_key": pact_key,
                "error_summary": error_summary,
                "fix_applied": True,
                "contract_changed": contract_changed,
            },
        )

    async def emit_fix_failed(
        self, component_id: str, pact_key: str, error_summary: str,
    ) -> bool:
        return await self.emit_signal(
            signal_type="fix_failed",
            actor=component_id,
            content={
                "pact_key": pact_key,
                "error_summary": error_summary,
                "fix_applied": False,
            },
        )

    async def emit_production_error(
        self, component_id: str, pact_key: str, error_summary: str,
    ) -> bool:
        return await self.emit_signal(
            signal_type="production_error",
            actor=component_id,
            content={
                "pact_key": pact_key,
                "error_summary": error_summary,
            },
        )

    async def emit_contract_tightened(
        self, component_id: str, pact_key: str,
    ) -> bool:
        return await self.emit_signal(
            signal_type="contract_tightened",
            actor=component_id,
            content={
                "pact_key": pact_key,
                "contract_changed": True,
            },
        )
