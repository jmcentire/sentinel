"""Tests for data models."""

from __future__ import annotations

import pytest

from sentinel.schemas import (
    Attribution,
    ContractProposal,
    DiagnosticReport,
    FixResult,
    Incident,
    LogKey,
    ManifestEntry,
    MonitoringBudget,
    SeverityMapping,
    Signal,
    SignalFingerprint,
)


class TestSignal:
    def test_log_file_signal(self):
        s = Signal(source="log_file", raw_text="ERROR: fail", timestamp="t", file_path="/a.log")
        assert s.source == "log_file"
        assert s.log_key == ""

    def test_manual_signal(self):
        s = Signal(source="manual", raw_text="TypeError", timestamp="t")
        assert s.process_name == ""


class TestLogKey:
    def test_canonical(self):
        k = LogKey(component_id="auth", method_name="validate", raw="PACT:auth:validate")
        assert k.component_id == "auth"
        assert k.method_name == "validate"

    def test_defaults(self):
        k = LogKey(component_id="x")
        assert k.method_name == ""
        assert k.raw == ""


class TestSignalFingerprint:
    def test_construction(self):
        s = Signal(source="log_file", raw_text="Error", timestamp="t")
        fp = SignalFingerprint(hash="abc", first_seen="t", last_seen="t", representative=s)
        assert fp.count == 1


class TestAttribution:
    def test_registered(self):
        a = Attribution(pact_key="PACT:auth:validate", component_id="auth", status="registered")
        assert a.status == "registered"

    def test_unattributed(self):
        a = Attribution(pact_key="", status="unattributed")
        assert a.manifest_entry is None


class TestManifestEntry:
    def test_defaults(self):
        e = ManifestEntry(component_id="auth")
        assert e.language == "python"
        assert e.pact_project == ""

    def test_serialization(self):
        e = ManifestEntry(component_id="auth", test_path="/tests")
        data = e.model_dump()
        e2 = ManifestEntry.model_validate(data)
        assert e2.test_path == "/tests"


class TestIncident:
    def test_defaults(self):
        inc = Incident(id="x", created_at="t", updated_at="t")
        assert inc.status == "detected"
        assert inc.severity == "medium"
        assert inc.pact_key == ""

    def test_serialization(self):
        inc = Incident(id="x", component_id="auth", created_at="t", updated_at="t", spend_usd=1.5)
        data = inc.model_dump()
        inc2 = Incident.model_validate(data)
        assert inc2.spend_usd == 1.5


class TestFixResult:
    def test_defaults(self):
        f = FixResult(id="f1", incident_id="i1", component_id="auth")
        assert f.status == "pending"
        assert f.spend_usd == 0.0

    def test_serialization(self):
        f = FixResult(id="f1", incident_id="i1", component_id="auth", status="success")
        data = f.model_dump()
        f2 = FixResult.model_validate(data)
        assert f2.status == "success"


class TestContractProposal:
    def test_construction(self):
        p = ContractProposal(component_id="auth", proposed_yaml="name: auth", reason="fix")
        assert p.component_id == "auth"


class TestSeverityMapping:
    def test_construction(self):
        m = SeverityMapping(field_pattern="email", annotation="gdpr", sentinel_severity="high")
        assert m.sentinel_severity == "high"


class TestMonitoringBudget:
    def test_defaults(self):
        b = MonitoringBudget()
        assert b.per_incident_cap == 5.00
        assert b.monthly_cap == 300.00


class TestDiagnosticReport:
    def test_construction(self):
        r = DiagnosticReport(
            incident_id="x", summary="s", error_analysis="a",
            component_context="c", recommended_direction="d",
            severity="high", confidence=0.9,
        )
        assert r.severity == "high"

    def test_compliance_severity(self):
        r = DiagnosticReport(
            incident_id="x", summary="s", error_analysis="a",
            component_context="c", recommended_direction="d",
            severity="compliance", confidence=0.5,
        )
        assert r.severity == "compliance"

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            DiagnosticReport(
                incident_id="x", summary="s", error_analysis="a",
                component_context="c", recommended_direction="d",
                severity="low", confidence=1.5,
            )
