"""Severity computation — base severity + Ledger field-level overrides."""

from __future__ import annotations

import logging
import re

from sentinel.ledger import SeverityMapping
from sentinel.schemas import Attribution, Signal

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = ["low", "medium", "high", "critical", "compliance"]

DEFAULT_SEVERITY = "medium"


def _max_severity(a: str, b: str) -> str:
    """Return the higher severity of two values."""
    a_idx = _SEVERITY_ORDER.index(a) if a in _SEVERITY_ORDER else 1
    b_idx = _SEVERITY_ORDER.index(b) if b in _SEVERITY_ORDER else 1
    return _SEVERITY_ORDER[max(a_idx, b_idx)]


class SeverityEngine:
    """Computes error severity with Ledger override support."""

    def __init__(self, ledger_mappings: list[SeverityMapping] | None = None) -> None:
        self._overrides: list[tuple[re.Pattern, str, str]] = []
        if ledger_mappings:
            for m in ledger_mappings:
                try:
                    pattern = re.compile(m.field_pattern, re.IGNORECASE)
                    self._overrides.append((pattern, m.annotation, m.sentinel_severity))
                except re.error:
                    logger.warning("Invalid field_pattern in Ledger mapping: %s", m.field_pattern)

    def compute(self, signal: Signal, attribution: Attribution) -> str:
        """Compute severity for an error signal.

        Base severity is DEFAULT_SEVERITY.
        Ledger overrides can escalate based on field patterns in the error context.
        Special rules:
        - gdpr_erasable fields: HIGH minimum (FA-S-028)
        - audit_field deletions: COMPLIANCE (FA-S-029)
        """
        severity = DEFAULT_SEVERITY
        context = signal.raw_text + " " + attribution.error_context

        # Check Ledger severity overrides
        for pattern, annotation, override in self._overrides:
            if pattern.search(context):
                severity = _max_severity(severity, override)

        # Built-in rules
        if _mentions_gdpr_erasable(context):
            severity = _max_severity(severity, "high")

        if _mentions_audit_field_deletion(context):
            severity = _max_severity(severity, "compliance")

        return severity


def _mentions_gdpr_erasable(context: str) -> bool:
    """Check if the error context involves a gdpr_erasable field."""
    return bool(re.search(r"gdpr[_\s]?erasable", context, re.IGNORECASE))


def _mentions_audit_field_deletion(context: str) -> bool:
    """Check if the error context involves deletion of an audit_field."""
    has_audit = bool(re.search(r"audit[_\s]?field", context, re.IGNORECASE))
    has_delete = bool(re.search(r"delet|remov|drop|purg", context, re.IGNORECASE))
    return has_audit and has_delete
