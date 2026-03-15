"""Contract tightening — pushes proposed contracts to Pact or writes locally."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from sentinel.config import PactIntegrationConfig
from sentinel.schemas import ContractProposal

logger = logging.getLogger(__name__)


class ContractManager:
    """Handles contract tightening proposals and Pact push."""

    def __init__(self, config: PactIntegrationConfig, sentinel_dir: Path) -> None:
        self._project_dir = config.project_dir
        self._api_endpoint = config.api_endpoint
        self._sentinel_dir = sentinel_dir
        self._proposals_dir = sentinel_dir / "proposed_contracts"

    @property
    def pact_configured(self) -> bool:
        return self._project_dir is not None or self._api_endpoint is not None

    async def push_contract(self, proposal: ContractProposal) -> bool:
        """Push a tightened contract to Pact.

        If Pact project_dir is configured: calls `pact sentinel push-contract` via subprocess.
        If only api_endpoint: POSTs to the Pact API.
        If neither: writes to .sentinel/proposed_contracts/ with a warning (FA-S-016).
        """
        if not proposal.proposed_yaml.strip() or proposal.proposed_yaml.strip() == "none":
            return False

        if self._project_dir:
            return await self._push_via_cli(proposal)

        if self._api_endpoint:
            return await self._push_via_api(proposal)

        return self._write_proposal(proposal)

    async def _push_via_cli(self, proposal: ContractProposal) -> bool:
        """Push via `pact sentinel push-contract`."""
        # Write proposal to temp file
        temp_path = self._sentinel_dir / "tmp_contract.yaml"
        self._sentinel_dir.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(proposal.proposed_yaml)

        try:
            proc = await asyncio.create_subprocess_exec(
                "pact", "sentinel", "push-contract",
                proposal.component_id, str(temp_path),
                cwd=self._project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info(
                    "Contract pushed to Pact for %s", proposal.component_id,
                )
                return True
            logger.warning(
                "pact sentinel push-contract failed: %s",
                stderr.decode("utf-8", errors="replace"),
            )
            return False
        except FileNotFoundError:
            logger.warning("pact CLI not found — writing proposal locally")
            return self._write_proposal(proposal)
        finally:
            temp_path.unlink(missing_ok=True)

    async def _push_via_api(self, proposal: ContractProposal) -> bool:
        """Push via Pact API endpoint."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._api_endpoint}/contracts/{proposal.component_id}",
                    json={
                        "component_id": proposal.component_id,
                        "contract_yaml": proposal.proposed_yaml,
                        "reason": proposal.reason,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status < 300:
                        return True
                    logger.warning("Pact API returned %d", resp.status)
                    return False
        except Exception as e:
            logger.warning("Pact API push failed: %s", e)
            return self._write_proposal(proposal)

    def _write_proposal(self, proposal: ContractProposal) -> bool:
        """Write proposed contract to .sentinel/proposed_contracts/ (FA-S-016)."""
        self._proposals_dir.mkdir(parents=True, exist_ok=True)
        path = self._proposals_dir / f"{proposal.component_id}.yaml"
        path.write_text(proposal.proposed_yaml)
        logger.warning(
            "Pact not configured — proposed contract written to %s", path,
        )
        return True

    def list_proposals(self) -> list[ContractProposal]:
        """List all locally stored contract proposals."""
        proposals = []
        if not self._proposals_dir.exists():
            return proposals
        for path in sorted(self._proposals_dir.glob("*.yaml")):
            proposals.append(ContractProposal(
                component_id=path.stem,
                proposed_yaml=path.read_text(),
            ))
        return proposals
