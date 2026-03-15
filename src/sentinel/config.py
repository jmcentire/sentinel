"""Configuration — loads sentinel.yaml into typed models."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SourceConfig(BaseModel):
    """A log source to watch."""
    type: Literal["file", "cloudwatch", "webhook", "stdout"] = "file"
    path: str = ""
    format: str = "text"
    log_group: str = ""
    filter_pattern: str = ""
    region: str = ""
    poll_interval: int = 30
    port: int = 0
    error_patterns: list[str] = Field(
        default_factory=lambda: ["ERROR", "CRITICAL", "Traceback"],
    )


class ErrorThresholdConfig(BaseModel):
    """When to spawn a fixer."""
    count: int = 1
    window_seconds: int = 300


class LLMConfig(BaseModel):
    """LLM provider settings."""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8192
    budget_per_fix: float = 2.00


class PactIntegrationConfig(BaseModel):
    """How to reach Pact for contract push."""
    project_dir: str | None = None
    api_endpoint: str | None = None


class ArbiterConfig(BaseModel):
    """Arbiter trust ledger connection."""
    api_endpoint: str | None = None
    trust_event_on_fix: bool = True


class StigmergyConfig(BaseModel):
    """Stigmergy signal emission."""
    endpoint: str | None = None


class NotifyConfig(BaseModel):
    """Webhook notifications."""
    webhook_url: str | None = None
    on_error: bool = True
    on_fix: bool = True
    on_contract_push: bool = True


class LedgerConfig(BaseModel):
    """Ledger severity mapping integration."""
    ledger_api: str | None = None


class BudgetConfig(BaseModel):
    """Multi-window spending budget."""
    per_incident_cap: float = 5.00
    hourly_cap: float = 10.00
    daily_cap: float = 25.00
    weekly_cap: float = 100.00
    monthly_cap: float = 300.00


class SentinelConfig(BaseModel):
    """Top-level configuration loaded from sentinel.yaml."""
    version: str = "1.0"
    sources: list[SourceConfig] = []
    pact_key_pattern: str = r"PACT:[a-zA-Z0-9_]+:[a-zA-Z0-9_]+"
    error_threshold: ErrorThresholdConfig = Field(default_factory=ErrorThresholdConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    pact: PactIntegrationConfig = Field(default_factory=PactIntegrationConfig)
    arbiter: ArbiterConfig = Field(default_factory=ArbiterConfig)
    stigmergy: StigmergyConfig = Field(default_factory=StigmergyConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    ledger: LedgerConfig = Field(default_factory=LedgerConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    auto_remediate: bool = False
    state_dir: str = ".sentinel"


def load_config(path: Path | None = None) -> SentinelConfig:
    """Load sentinel.yaml from the given path, cwd, or defaults.

    Search order: explicit path, ./sentinel.yaml, ~/.sentinel/sentinel.yaml.
    Returns default config if no file found.
    """
    candidates = []
    if path:
        candidates.append(path)
    candidates.extend([
        Path.cwd() / "sentinel.yaml",
        Path.home() / ".sentinel" / "sentinel.yaml",
    ])

    for candidate in candidates:
        if candidate.exists():
            try:
                data = yaml.safe_load(candidate.read_text()) or {}
                return SentinelConfig.model_validate(data)
            except Exception as e:
                logger.warning("Failed to load %s: %s", candidate, e)

    return SentinelConfig()
