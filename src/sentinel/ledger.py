"""Ledger integration — loads field-level severity mappings at startup."""

from __future__ import annotations

import logging

import aiohttp

from sentinel.config import LedgerConfig

logger = logging.getLogger(__name__)


class SeverityMapping:
    """A field-level severity override from Ledger."""

    def __init__(
        self,
        field_pattern: str,
        annotation: str,
        sentinel_severity: str,
    ) -> None:
        self.field_pattern = field_pattern
        self.annotation = annotation
        self.sentinel_severity = sentinel_severity


class LedgerClient:
    """Fetches severity mappings from the Ledger API."""

    def __init__(self, config: LedgerConfig) -> None:
        self._endpoint = config.ledger_api

    def is_configured(self) -> bool:
        return self._endpoint is not None

    async def load_severity_mappings(self) -> list[SeverityMapping]:
        """GET /export/sentinel from Ledger. Returns empty list on failure.

        Per FA-S-030: Ledger unavailability logs a warning but does not
        prevent Sentinel from watching logs.
        """
        if not self.is_configured():
            return []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._endpoint}/export/sentinel",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status >= 300:
                        logger.warning(
                            "Ledger returned %d — proceeding without severity overrides",
                            resp.status,
                        )
                        return []
                    data = await resp.json()
        except Exception as e:
            logger.warning(
                "Ledger unavailable at %s — proceeding without severity overrides: %s",
                self._endpoint, e,
            )
            return []

        mappings = []
        for entry in data.get("severity_mappings", []):
            mappings.append(SeverityMapping(
                field_pattern=entry.get("field_pattern", ""),
                annotation=entry.get("annotation", ""),
                sentinel_severity=entry.get("sentinel_severity", "medium"),
            ))

        logger.info("Loaded %d severity mappings from Ledger", len(mappings))
        return mappings
