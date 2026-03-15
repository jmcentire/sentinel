"""Tests for severity computation and Ledger integration."""

from __future__ import annotations

from sentinel.ledger import SeverityMapping
from sentinel.schemas import Attribution, Signal
from sentinel.severity import SeverityEngine, _max_severity


def _make_signal(text: str) -> Signal:
    return Signal(source="log_file", raw_text=text, timestamp="2024-01-01")


def _make_attribution(error_context: str = "") -> Attribution:
    return Attribution(pact_key="PACT:auth:validate", component_id="auth", error_context=error_context)


class TestMaxSeverity:
    def test_same(self):
        assert _max_severity("high", "high") == "high"

    def test_escalates(self):
        assert _max_severity("low", "high") == "high"
        assert _max_severity("medium", "critical") == "critical"

    def test_compliance_highest(self):
        assert _max_severity("critical", "compliance") == "compliance"


class TestSeverityEngine:
    def test_default_severity(self):
        engine = SeverityEngine()
        s = engine.compute(_make_signal("ERROR: something"), _make_attribution())
        assert s == "medium"

    def test_gdpr_erasable_escalates_to_high(self):
        engine = SeverityEngine()
        s = engine.compute(
            _make_signal("ERROR: failed to process gdpr_erasable field email"),
            _make_attribution(),
        )
        assert s == "high"

    def test_audit_field_deletion_escalates_to_compliance(self):
        engine = SeverityEngine()
        s = engine.compute(
            _make_signal("ERROR: audit_field record was deleted unexpectedly"),
            _make_attribution(),
        )
        assert s == "compliance"

    def test_ledger_override(self):
        mappings = [
            SeverityMapping(
                field_pattern="credit_card",
                annotation="pci_sensitive",
                sentinel_severity="critical",
            ),
        ]
        engine = SeverityEngine(mappings)
        s = engine.compute(
            _make_signal("ERROR: credit_card validation failed"),
            _make_attribution(),
        )
        assert s == "critical"

    def test_ledger_override_combined_with_gdpr(self):
        mappings = [
            SeverityMapping(
                field_pattern="ssn",
                annotation="pii",
                sentinel_severity="high",
            ),
        ]
        engine = SeverityEngine(mappings)
        # gdpr_erasable is also high, so no further escalation
        s = engine.compute(
            _make_signal("ERROR: ssn gdpr_erasable field exposed"),
            _make_attribution(),
        )
        assert s == "high"

    def test_no_ledger_mappings(self):
        engine = SeverityEngine(None)
        s = engine.compute(_make_signal("ERROR: generic"), _make_attribution())
        assert s == "medium"

    def test_audit_field_without_delete_no_escalation(self):
        engine = SeverityEngine()
        s = engine.compute(
            _make_signal("ERROR: audit_field read timeout"),
            _make_attribution(),
        )
        # No deletion keyword, stays medium
        assert s == "medium"
