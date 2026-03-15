"""Triage agent — maps error signals to components via LLM when PACT key is missing."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from sentinel.llm import LLMClient
from sentinel.manifest import ManifestManager
from sentinel.schemas import Signal

logger = logging.getLogger(__name__)

TRIAGE_SYSTEM = """You are starting fresh on this triage with no prior context.

Analyze the production error signal and determine which component most likely
produced it. Respond with the component_id or "unknown" if uncertain."""


class TriageResult(BaseModel):
    """Result of LLM-based triage."""
    component_id: str = Field(description="Component ID or 'unknown'")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the mapping")
    reasoning: str = Field(description="Brief explanation")


class DiagnosticResult(BaseModel):
    """LLM-generated diagnostic for escalation."""
    summary: str = Field(description="1-2 sentence summary")
    error_analysis: str = Field(description="Root cause hypothesis")
    component_context: str = Field(description="How the component relates to the error")
    recommended_direction: str = Field(description="What a human should do next")
    severity: str = Field(description="low, medium, high, critical, or compliance")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in diagnosis")


async def triage_signal(
    llm: LLMClient,
    signal: Signal,
    manifest: ManifestManager,
) -> str | None:
    """Use LLM to map an error signal to a component ID.

    Returns component_id or None if can't be determined.
    """
    entries = manifest.all_entries()
    if not entries:
        return None

    # Build compact summary of all components
    summaries = []
    for comp_id, entry in entries.items():
        contract_text = ""
        if entry.contract_path:
            try:
                data = json.loads(open(entry.contract_path).read())
                funcs = [f.get("name", "") for f in data.get("functions", [])]
                types = [t.get("name", "") for t in data.get("types", [])]
                contract_text = f"functions=[{', '.join(funcs)}], types=[{', '.join(types)}]"
            except Exception:
                contract_text = "(contract unreadable)"
        summaries.append(f"- {comp_id}: {contract_text}")

    components_text = "\n".join(summaries)

    prompt = f"""Error signal from production:
Source: {signal.source}
Raw text: {signal.raw_text}
File: {signal.file_path}
Process: {signal.process_name}

Known components:
{components_text}

Which component most likely produced this error?"""

    try:
        result, _, _ = await llm.assess(
            TriageResult, prompt, TRIAGE_SYSTEM, max_tokens=1024,
        )
        if result.component_id == "unknown" or result.confidence < 0.3:
            return None
        if result.component_id in entries:
            return result.component_id
        return None
    except Exception as e:
        logger.debug("Triage failed: %s", e)
        return None


async def generate_diagnostic_report(
    llm: LLMClient,
    incident_id: str,
    signal: Signal,
    manifest: ManifestManager,
    component_id: str = "",
    attempted_fixes: list[str] | None = None,
) -> DiagnosticResult | None:
    """Generate a diagnostic report for escalation."""
    context = ""
    if component_id:
        entry = manifest.lookup(component_id)
        if entry and entry.contract_path:
            try:
                context = open(entry.contract_path).read()[:2000]
            except Exception:
                context = "(contract unreadable)"

    fixes_text = "\n".join(f"  {i}. {f}" for i, f in enumerate(attempted_fixes or [], 1)) or "None"

    prompt = f"""Analyze this production incident.

Incident ID: {incident_id}
Component: {component_id or 'unknown'}

Error:
  [{signal.source}] {signal.raw_text[:500]}

Contract context:
{context or 'No contract available'}

Attempted fixes:
{fixes_text}

Produce a diagnostic report."""

    try:
        result, _, _ = await llm.assess(
            DiagnosticResult, prompt,
            "Analyze the incident and produce a diagnostic report.",
            max_tokens=2048,
        )
        return result
    except Exception as e:
        logger.debug("Diagnostic report generation failed: %s", e)
        return None
