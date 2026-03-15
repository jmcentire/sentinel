"""Sentinel — long-running production monitor and auto-remediation coordinator.

Watches configured signal sources, attributes errors via PACT keys, computes
severity with Ledger overrides, creates incidents, spawns fixer agents, pushes
tightened contracts to Pact, and reports trust events to Arbiter/Stigmergy.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path

from sentinel.arbiter import ArbiterClient
from sentinel.attribution import AttributionEngine
from sentinel.config import SentinelConfig
from sentinel.contracts import ContractManager
from sentinel.events import EventBus, SentinelEvent
from sentinel.fixer import FixerAgent
from sentinel.git_ops import GitOps
from sentinel.incidents import IncidentManager
from sentinel.ledger import LedgerClient
from sentinel.llm import LLMClient
from sentinel.manifest import ManifestManager
from sentinel.notify import Notifier
from sentinel.schemas import (
    Attribution,
    ContractProposal,
    FixResult,
    Incident,
    MonitoringBudget,
    Signal,
    SignalFingerprint,
)
from sentinel.severity import SeverityEngine
from sentinel.stigmergy import StigmergyClient
from sentinel.triage import triage_signal
from sentinel.watcher import SignalIngester, fingerprint_signal

logger = logging.getLogger(__name__)


class Sentinel:
    """Main orchestrator — wires all modules, runs the signal pipeline."""

    def __init__(self, config: SentinelConfig) -> None:
        self._config = config
        self._state_dir = Path(config.state_dir)
        self._running = False

        # Core modules
        self._manifest = ManifestManager(self._state_dir)
        self._attribution = AttributionEngine(self._manifest, config.pact_key_pattern)
        budget = MonitoringBudget(**config.budget.model_dump())
        self._incident_mgr = IncidentManager(self._state_dir, budget)
        self._ingester = SignalIngester(
            config.sources, config.error_threshold.window_seconds,
        )
        self._event_bus = EventBus()

        # Integration clients
        self._arbiter = ArbiterClient(config.arbiter)
        self._stigmergy = StigmergyClient(config.stigmergy)
        self._notifier = Notifier(config.notify)
        self._contracts = ContractManager(config.pact, self._state_dir)
        self._ledger = LedgerClient(config.ledger)

        # Severity engine (loaded at startup)
        self._severity: SeverityEngine | None = None

        # Fix history
        self._fixes: list[FixResult] = []

    @property
    def manifest(self) -> ManifestManager:
        return self._manifest

    @property
    def incident_mgr(self) -> IncidentManager:
        return self._incident_mgr

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def fixes(self) -> list[FixResult]:
        return self._fixes

    async def startup(self) -> None:
        """Load Ledger severity mappings (FA-S-027). Non-blocking on failure (FA-S-030)."""
        mappings = await self._ledger.load_severity_mappings()
        self._severity = SeverityEngine(mappings if mappings else None)

    async def run(self) -> None:
        """Main loop — watch sources and process signals until stopped."""
        self._running = True
        await self.startup()

        logger.info("Sentinel starting: %d sources configured", len(self._config.sources))
        await self._ingester.start()

        try:
            async for signal in self._ingester.watch():
                if not self._running:
                    break
                try:
                    await self.handle_signal(signal)
                except Exception as e:
                    logger.debug("Error handling signal: %s", e)
        except asyncio.CancelledError:
            pass
        finally:
            self._ingester.stop()
            logger.info("Sentinel stopped")

    async def handle_signal(self, signal: Signal) -> None:
        """Process a single signal through the full pipeline."""
        # Step 1: Attribute
        attribution = self._attribution.attribute_signal(signal)

        # Step 2: Compute severity
        severity = "medium"
        if self._severity:
            severity = self._severity.compute(signal, attribution)

        # Step 3: Check for existing incident (dedup)
        fp_hash = fingerprint_signal(signal)
        existing = self._find_incident_by_fingerprint(fp_hash)
        if existing:
            self._incident_mgr.add_signal(existing.id, signal)
            return

        # Step 4: Create incident
        project_dir = ""
        if attribution.manifest_entry:
            project_dir = attribution.manifest_entry.pact_project
        incident = self._incident_mgr.create_incident(signal, project_dir, attribution.component_id)
        incident.pact_key = attribution.pact_key
        incident.severity = severity
        incident.fingerprint = SignalFingerprint(
            hash=fp_hash,
            first_seen=datetime.now().isoformat(),
            last_seen=datetime.now().isoformat(),
            count=1,
            representative=signal,
        )
        self._incident_mgr.save_state()

        # Step 5: Alert (always)
        await self._alert(incident)

        # Step 6: Report production error to Arbiter (FA-S-019)
        if attribution.component_id:
            await self._arbiter.report_production_error(
                attribution.component_id, run_id=incident.id,
            )
            await self._stigmergy.emit_production_error(
                attribution.component_id,
                attribution.pact_key,
                signal.raw_text[:200],
            )

        # Step 7: Triage if no component identified
        if not attribution.component_id and attribution.status != "registered":
            try:
                llm = LLMClient(self._config.llm)
                component_id = await triage_signal(llm, signal, self._manifest)
                await llm.close()
                if component_id:
                    incident.component_id = component_id
                    attribution = Attribution(
                        pact_key=attribution.pact_key,
                        component_id=component_id,
                        status="registered",
                        manifest_entry=self._manifest.lookup(component_id),
                        error_context=signal.raw_text,
                    )
                    self._incident_mgr.save_state()
            except Exception as e:
                logger.debug("Triage failed: %s", e)

        # Step 8: Auto-remediate if enabled and component known
        if self._config.auto_remediate and attribution.component_id and attribution.manifest_entry:
            if self._incident_mgr.check_budget(incident.id):
                fix_result = await self._spawn_fixer(incident, attribution)
                if fix_result.status == "success":
                    self._incident_mgr.close_incident(
                        incident.id, "auto_fixed",
                        f"Auto-fixed by Sentinel at {datetime.now().isoformat()}",
                    )
                    await self._post_fix_success(incident, fix_result, attribution)
                else:
                    await self._post_fix_failure(incident, fix_result, attribution)
                    await self._escalate(incident)
            else:
                incident.resolution = "budget_exceeded"
                await self._escalate(incident)
        elif not self._config.auto_remediate:
            await self._escalate(incident)

    async def handle_manual_fix(self, pact_key: str, error_text: str) -> FixResult:
        """Manually trigger a fix for a PACT key + error (FA-S-023)."""
        signal = Signal(
            source="manual",
            raw_text=error_text,
            timestamp=datetime.now().isoformat(),
            log_key=pact_key,
        )
        attribution = self._attribution.attribute(pact_key + " " + error_text)

        if not attribution.manifest_entry:
            return FixResult(
                id=uuid.uuid4().hex[:12],
                incident_id="",
                component_id=attribution.component_id,
                status="failure",
                error=f"Component {attribution.component_id} not in manifest",
                completed_at=datetime.now().isoformat(),
            )

        incident = self._incident_mgr.create_incident(
            signal,
            attribution.manifest_entry.pact_project,
            attribution.component_id,
        )
        incident.pact_key = attribution.pact_key

        return await self._spawn_fixer(incident, attribution)

    async def _spawn_fixer(
        self, incident: Incident, attribution: Attribution,
    ) -> FixResult:
        """Spawn a fixer agent for an incident (FA-S-007)."""
        self._incident_mgr.update_status(incident.id, "remediating")
        await self._event_bus.emit(SentinelEvent(
            kind="fix_started",
            component_id=attribution.component_id,
            detail=f"Fixing {incident.id}",
        ))

        llm = LLMClient(self._config.llm)
        git = GitOps(Path(attribution.manifest_entry.pact_project)) if attribution.manifest_entry else None
        fixer = FixerAgent(llm=llm, git=git)

        try:
            result = await fixer.fix(incident, attribution.manifest_entry)
            self._fixes.append(result)
            self._incident_mgr.record_spend(incident.id, result.spend_usd)
            return result
        except Exception as e:
            logger.debug("Fixer failed for %s: %s", incident.id, e)
            return FixResult(
                id=uuid.uuid4().hex[:12],
                incident_id=incident.id,
                component_id=attribution.component_id,
                status="failure",
                error=str(e),
                completed_at=datetime.now().isoformat(),
            )
        finally:
            await llm.close()

    async def _post_fix_success(
        self, incident: Incident, fix_result: FixResult, attribution: Attribution,
    ) -> None:
        """Handle successful fix: push contract, Arbiter, Stigmergy, notify."""
        # Push contract tightening (FA-S-015/FA-S-016)
        contract_changed = False
        if fix_result.contract_change and fix_result.contract_change.strip() != "none":
            proposal = ContractProposal(
                component_id=attribution.component_id,
                proposed_yaml=fix_result.contract_change,
                reason=f"Tightened after fix for incident {incident.id}",
                fix_id=fix_result.id,
            )
            await self._contracts.push_contract(proposal)
            contract_changed = True
            await self._stigmergy.emit_contract_tightened(
                attribution.component_id, attribution.pact_key,
            )

        # Arbiter trust boost (FA-S-017)
        await self._arbiter.report_fix_success(
            attribution.component_id, run_id=fix_result.id,
        )

        # Stigmergy signal (FA-S-020)
        await self._stigmergy.emit_fix_applied(
            attribution.component_id,
            attribution.pact_key,
            incident.signals[0].raw_text[:200] if incident.signals else "",
            contract_changed=contract_changed,
        )

        # Notify
        await self._notifier.notify("fix", {
            "incident_id": incident.id,
            "component_id": attribution.component_id,
            "fix_id": fix_result.id,
        })

        await self._event_bus.emit(SentinelEvent(
            kind="fix_complete",
            component_id=attribution.component_id,
            detail=f"Fixed {incident.id} (${fix_result.spend_usd:.2f})",
        ))

    async def _post_fix_failure(
        self, incident: Incident, fix_result: FixResult, attribution: Attribution,
    ) -> None:
        """Handle failed fix: Arbiter penalty, Stigmergy, notify."""
        # Arbiter trust penalty (FA-S-018)
        await self._arbiter.report_fix_failure(
            attribution.component_id, run_id=fix_result.id,
        )

        # Stigmergy signal (FA-S-020)
        await self._stigmergy.emit_fix_failed(
            attribution.component_id,
            attribution.pact_key,
            incident.signals[0].raw_text[:200] if incident.signals else "",
        )

        await self._event_bus.emit(SentinelEvent(
            kind="fix_failed",
            component_id=attribution.component_id,
            detail=f"Fix failed for {incident.id}: {fix_result.error}",
        ))

    async def _alert(self, incident: Incident) -> None:
        """Send alert notification for a new incident."""
        await self._notifier.notify("error", {
            "incident_id": incident.id,
            "component_id": incident.component_id,
            "severity": incident.severity,
            "error": incident.signals[0].raw_text[:200] if incident.signals else "",
        })
        await self._event_bus.emit(SentinelEvent(
            kind="incident_detected",
            component_id=incident.component_id,
            detail=f"Incident {incident.id}: {incident.signals[0].raw_text[:100] if incident.signals else 'unknown'}",
        ))

    async def _escalate(self, incident: Incident) -> None:
        """Escalate an incident."""
        self._incident_mgr.update_status(incident.id, "escalated")
        report = (
            f"# Escalation: Incident {incident.id}\n"
            f"Component: {incident.component_id or 'unknown'}\n"
            f"Severity: {incident.severity}\n"
            f"Spend: ${incident.spend_usd:.2f}\n"
            f"Resolution: {incident.resolution or 'needs human review'}\n"
        )
        self._incident_mgr.close_incident(incident.id, "escalated", report)
        await self._event_bus.emit(SentinelEvent(
            kind="incident_escalated",
            component_id=incident.component_id,
            detail=f"Incident {incident.id} escalated",
        ))

    def _find_incident_by_fingerprint(self, fp_hash: str) -> Incident | None:
        for incident in self._incident_mgr.get_recent_incidents(100):
            if incident.fingerprint and incident.fingerprint.hash == fp_hash:
                return incident
        return None

    def stop(self) -> None:
        """Signal graceful shutdown."""
        self._running = False
        self._ingester.stop()
