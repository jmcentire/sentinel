"""Tests for contract tightening and Pact push."""

from __future__ import annotations

from pathlib import Path

import pytest

from sentinel.config import PactIntegrationConfig
from sentinel.contracts import ContractManager
from sentinel.schemas import ContractProposal


class TestContractManager:
    def test_not_configured(self, tmp_path: Path):
        mgr = ContractManager(PactIntegrationConfig(), tmp_path)
        assert mgr.pact_configured is False

    def test_configured_with_project_dir(self, tmp_path: Path):
        mgr = ContractManager(
            PactIntegrationConfig(project_dir="/tmp/pact"),
            tmp_path,
        )
        assert mgr.pact_configured is True

    @pytest.mark.asyncio
    async def test_write_proposal_when_unconfigured(self, tmp_path: Path):
        """FA-S-016: writes to .sentinel/proposed_contracts/ when Pact not configured."""
        mgr = ContractManager(PactIntegrationConfig(), tmp_path)
        proposal = ContractProposal(
            component_id="auth",
            proposed_yaml="name: auth\nversion: 2",
            reason="tightened after fix",
        )
        result = await mgr.push_contract(proposal)
        assert result is True

        written = tmp_path / "proposed_contracts" / "auth.yaml"
        assert written.exists()
        assert "version: 2" in written.read_text()

    @pytest.mark.asyncio
    async def test_empty_proposal_skipped(self, tmp_path: Path):
        mgr = ContractManager(PactIntegrationConfig(), tmp_path)
        proposal = ContractProposal(component_id="auth", proposed_yaml="none")
        result = await mgr.push_contract(proposal)
        assert result is False

    def test_list_proposals(self, tmp_path: Path):
        mgr = ContractManager(PactIntegrationConfig(), tmp_path)
        proposals_dir = tmp_path / "proposed_contracts"
        proposals_dir.mkdir(parents=True)
        (proposals_dir / "auth.yaml").write_text("name: auth")
        (proposals_dir / "pricing.yaml").write_text("name: pricing")

        proposals = mgr.list_proposals()
        assert len(proposals) == 2
        ids = [p.component_id for p in proposals]
        assert "auth" in ids
        assert "pricing" in ids

    def test_list_proposals_empty(self, tmp_path: Path):
        mgr = ContractManager(PactIntegrationConfig(), tmp_path)
        assert mgr.list_proposals() == []
