"""Attribution engine — extracts PACT keys from log lines, looks up in manifest."""

from __future__ import annotations

import logging
import re

from sentinel.manifest import ManifestManager
from sentinel.schemas import Attribution, LogKey, Signal

logger = logging.getLogger(__name__)


class AttributionEngine:
    """Extracts PACT keys and attributes errors to registered components."""

    # Internal pattern always uses capture groups
    _DEFAULT_PATTERN = re.compile(r"PACT:([a-zA-Z0-9_]+):([a-zA-Z0-9_]+)")

    def __init__(
        self,
        manifest: ManifestManager,
        key_pattern: str = r"PACT:[a-zA-Z0-9_]+:[a-zA-Z0-9_]+",
    ) -> None:
        self._manifest = manifest
        # Ensure pattern has capture groups; if user-provided pattern lacks them,
        # use it only for detection and fall back to default for extraction.
        compiled = re.compile(key_pattern)
        if compiled.groups >= 2:
            self._pattern = compiled
        else:
            self._pattern = self._DEFAULT_PATTERN

    def extract_key(self, line: str) -> LogKey | None:
        """Extract a PACT key from a log line. Returns None if no match."""
        m = self._pattern.search(line)
        if not m:
            return None
        return LogKey(
            component_id=m.group(1),
            method_name=m.group(2) if m.lastindex and m.lastindex >= 2 else "",
            raw=m.group(0),
        )

    def attribute(self, line: str) -> Attribution:
        """Attribute a log line to a component.

        Returns Attribution with status:
        - "registered": PACT key found and component is in manifest
        - "unregistered": PACT key found but component not in manifest
        - "unattributed": no PACT key found in the line
        """
        key = self.extract_key(line)

        if key is None:
            logger.debug("UNATTRIBUTED: no PACT key in line: %.100s", line)
            return Attribution(
                pact_key="",
                status="unattributed",
                error_context=line,
            )

        # Try canonical lookup: first segment is component_id
        entry = self._manifest.lookup(key.component_id)
        if entry:
            return Attribution(
                pact_key=key.raw,
                component_id=key.component_id,
                method_name=key.method_name,
                status="registered",
                manifest_entry=entry,
                error_context=line,
            )

        # Try secondary format: first segment is project_hash, second is component_id
        entry = self._manifest.lookup(key.method_name)
        if entry:
            return Attribution(
                pact_key=key.raw,
                component_id=key.method_name,
                method_name="",
                status="registered",
                manifest_entry=entry,
                error_context=line,
            )

        # Key found but component not registered
        logger.debug("UNREGISTERED: PACT key %s not in manifest", key.raw)
        return Attribution(
            pact_key=key.raw,
            component_id=key.component_id,
            method_name=key.method_name,
            status="unregistered",
            error_context=line,
        )

    def attribute_signal(self, signal: Signal) -> Attribution:
        """Attribute a Signal object. Checks log_key field first, then raw_text."""
        if signal.log_key:
            attr = self.attribute(signal.log_key)
            if attr.status != "unattributed":
                attr.error_context = signal.raw_text
                return attr
        return self.attribute(signal.raw_text)
