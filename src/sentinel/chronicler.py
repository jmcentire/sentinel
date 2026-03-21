"""Chronicler webhook client — emits incident lifecycle events."""

from __future__ import annotations

import logging
from datetime import datetime

import aiohttp

from sentinel.config import ChroniclerConfig
from sentinel.schemas import Incident

logger = logging.getLogger(__name__)


class ChroniclerEmitter:
    """Posts incident lifecycle events to a Chronicler endpoint. Fire-and-forget."""

    def __init__(self, config: ChroniclerConfig) -> None:
        self._endpoint = config.chronicler_endpoint
        self._enabled = config.chronicler_enabled

    def is_configured(self) -> bool:
        return self._enabled and self._endpoint is not None

    async def emit(self, incident: Incident) -> bool:
        """Convert an incident's lifecycle into an event sequence and POST each.

        Returns True if all events were posted successfully. Never raises.
        """
        if not self.is_configured():
            return False

        events = self._build_events(incident)
        all_ok = True
        for event in events:
            ok = await self._post(f"{self._endpoint}/events", event)
            if not ok:
                all_ok = False
        return all_ok

    def _build_events(self, incident: Incident) -> list[dict]:
        """Build the event sequence from an incident's lifecycle state."""
        base = {
            "incident_id": incident.id,
            "component_id": incident.component_id or "",
            "pact_key": incident.pact_key or "",
            "severity": incident.severity,
            "signal_count": len(incident.signals),
            "spend_usd": incident.spend_usd,
        }

        events: list[dict] = []

        # Always emit detected
        events.append({
            **base,
            "event": "incident.detected",
            "timestamp": incident.created_at,
        })

        # Triage phase (if the incident progressed past detection)
        if incident.status not in ("detected",):
            events.append({
                **base,
                "event": "incident.triaging",
                "timestamp": incident.created_at,
            })

        # Remediation phase
        if incident.status in ("remediating", "verifying", "resolved", "escalated"):
            events.append({
                **base,
                "event": "incident.remediating",
                "timestamp": incident.updated_at,
            })

        # Terminal state
        if incident.status == "resolved":
            events.append({
                **base,
                "event": "incident.resolved",
                "timestamp": incident.updated_at,
            })
        elif incident.status == "escalated":
            events.append({
                **base,
                "event": "incident.escalated",
                "timestamp": incident.updated_at,
            })

        return events

    async def _post(self, url: str, payload: dict) -> bool:
        """POST JSON. Returns True on 2xx. Never raises."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status < 300:
                        return True
                    logger.debug("Chronicler returned %d", resp.status)
                    return False
        except Exception as e:
            logger.debug("Chronicler request failed (non-fatal): %s", e)
            return False
