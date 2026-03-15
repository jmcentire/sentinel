"""Lightweight async event bus for internal Sentinel events."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class SentinelEvent:
    """An internal event emitted during Sentinel operation."""
    kind: str
    component_id: str = ""
    detail: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class EventBus:
    """Simple async event dispatcher. Handler exceptions are logged, not propagated."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, kind: str, handler: Callable) -> None:
        """Register a handler for an event kind."""
        self._handlers.setdefault(kind, []).append(handler)

    async def emit(self, event: SentinelEvent) -> None:
        """Dispatch event to all registered handlers for its kind."""
        for handler in self._handlers.get(event.kind, []):
            try:
                result = handler(event)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.debug("Event handler error for %s: %s", event.kind, e)

        # Also dispatch to wildcard handlers
        for handler in self._handlers.get("*", []):
            try:
                result = handler(event)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.debug("Wildcard handler error: %s", e)
