"""Data models for Sentinel — signal ingestion, attribution, incident lifecycle,
fix tracking, severity, and diagnostic reporting.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Signal ingestion
# ---------------------------------------------------------------------------

class Signal(BaseModel):
    """A raw incoming error signal."""
    source: Literal["log_file", "process", "webhook", "manual"]
    raw_text: str
    timestamp: str
    file_path: str = ""
    process_name: str = ""
    log_key: str = ""


class SignalFingerprint(BaseModel):
    """Deduplicated signal identity."""
    hash: str
    first_seen: str
    last_seen: str
    count: int = 1
    representative: Signal


# ---------------------------------------------------------------------------
# PACT key and attribution
# ---------------------------------------------------------------------------

class LogKey(BaseModel):
    """Parsed PACT key from a log line.

    Canonical format: PACT:<component_id>:<method_name>
    The raw field stores the original matched string.
    """
    component_id: str
    method_name: str = ""
    raw: str = ""


class ManifestEntry(BaseModel):
    """A registered component in .sentinel/manifest.json."""
    component_id: str
    contract_path: str = ""
    test_path: str = ""
    source_path: str = ""
    language: str = "python"
    last_registered: str = ""
    pact_project: str = ""


class Attribution(BaseModel):
    """Result of attributing a log line to a component."""
    pact_key: str
    component_id: str = ""
    method_name: str = ""
    status: Literal["registered", "unregistered", "unattributed"] = "unattributed"
    manifest_entry: ManifestEntry | None = None
    error_context: str = ""


# ---------------------------------------------------------------------------
# Incident lifecycle
# ---------------------------------------------------------------------------

class Incident(BaseModel):
    """A tracked error incident with lifecycle."""
    id: str
    status: Literal[
        "detected", "triaging", "diagnosing", "remediating",
        "verifying", "resolved", "escalated",
    ] = "detected"
    project_dir: str = ""
    component_id: str = ""
    pact_key: str = ""
    severity: str = "medium"
    signals: list[Signal] = []
    fingerprint: SignalFingerprint | None = None
    created_at: str
    updated_at: str
    spend_usd: float = 0.0
    resolution: str = ""
    diagnostic_report: str = ""
    remediation_attempts: int = 0


class MonitoringBudget(BaseModel):
    """Multi-window budget for monitoring operations."""
    per_incident_cap: float = 5.00
    hourly_cap: float = 10.00
    daily_cap: float = 25.00
    weekly_cap: float = 100.00
    monthly_cap: float = 300.00


# ---------------------------------------------------------------------------
# Fix tracking
# ---------------------------------------------------------------------------

class FixResult(BaseModel):
    """Result of a fixer agent run."""
    id: str
    incident_id: str
    component_id: str
    status: Literal["pending", "running", "success", "failure"] = "pending"
    reproducer_test: str = ""
    fixed_source: dict[str, str] = Field(default_factory=dict)
    contract_change: str = ""
    git_snapshot_ref: str = ""
    git_fix_ref: str = ""
    started_at: str = ""
    completed_at: str = ""
    spend_usd: float = 0.0
    error: str = ""


class ContractProposal(BaseModel):
    """Proposed contract tightening from a fixer."""
    component_id: str
    proposed_yaml: str = ""
    reason: str = ""
    fix_id: str = ""


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

class SeverityMapping(BaseModel):
    """Ledger-sourced severity override for a field pattern."""
    field_pattern: str
    annotation: str
    sentinel_severity: str


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class DiagnosticReport(BaseModel):
    """Structured escalation report."""
    incident_id: str
    summary: str
    error_analysis: str
    component_context: str
    attempted_fixes: list[str] = []
    recommended_direction: str
    severity: Literal["low", "medium", "high", "critical", "compliance"]
    confidence: float = Field(ge=0.0, le=1.0)
