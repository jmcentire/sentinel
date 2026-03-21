# === Sentinel Configuration Loader (src_sentinel_config) v1 ===
#  Dependencies: pathlib, logging, typing, yaml, pydantic
# Loads and validates sentinel.yaml configuration files into typed Pydantic models. Provides configuration schema for log sources, error thresholds, LLM settings, integrations (Pact, Arbiter, Stigmergy), notifications, budgets, and auto-remediation settings.

# Module invariants:
#   - Default configuration is always valid and can be instantiated without parameters
#   - All Pydantic models have default values for all fields
#   - Config search order is deterministic: explicit path -> ./sentinel.yaml -> ~/.sentinel/sentinel.yaml
#   - First successfully loaded config file wins; subsequent candidates are not checked
#   - If all candidates fail or no files exist, default SentinelConfig is returned

class SourceConfig:
    """A log source to watch."""
    type: Literal['file', 'cloudwatch', 'webhook', 'stdout'] = file # optional
    path: str = None                         # optional
    format: str = text                       # optional
    log_group: str = None                    # optional
    filter_pattern: str = None               # optional
    region: str = None                       # optional
    poll_interval: int = 30                  # optional
    port: int = 0                            # optional
    error_patterns: list[str] = ['ERROR', 'CRITICAL', 'Traceback'] # optional

class ErrorThresholdConfig:
    """When to spawn a fixer."""
    count: int = 1                           # optional
    window_seconds: int = 300                # optional

class LLMConfig:
    """LLM provider settings."""
    provider: str = anthropic                # optional
    model: str = claude-sonnet-4-20250514    # optional
    max_tokens: int = 8192                   # optional
    budget_per_fix: float = 2.00             # optional

class PactIntegrationConfig:
    """How to reach Pact for contract push."""
    project_dir: str | None = None           # optional
    api_endpoint: str | None = None          # optional

class ArbiterConfig:
    """Arbiter trust ledger connection."""
    api_endpoint: str | None = None          # optional
    trust_event_on_fix: bool = True          # optional

class StigmergyConfig:
    """Stigmergy signal emission."""
    endpoint: str | None = None              # optional

class NotifyConfig:
    """Webhook notifications."""
    webhook_url: str | None = None           # optional
    on_error: bool = True                    # optional
    on_fix: bool = True                      # optional
    on_contract_push: bool = True            # optional

class LedgerConfig:
    """Ledger severity mapping integration."""
    ledger_api: str | None = None            # optional

class BudgetConfig:
    """Multi-window spending budget."""
    per_incident_cap: float = 5.00           # optional
    hourly_cap: float = 10.00                # optional
    daily_cap: float = 25.00                 # optional
    weekly_cap: float = 100.00               # optional
    monthly_cap: float = 300.00              # optional

class SentinelConfig:
    """Top-level configuration loaded from sentinel.yaml."""
    version: str = 1.0                       # optional
    sources: list[SourceConfig] = []         # optional
    pact_key_pattern: str = r"PACT:[a-zA-Z0-9_]+:[a-zA-Z0-9_]+" # optional
    error_threshold: ErrorThresholdConfig = ErrorThresholdConfig() # optional
    llm: LLMConfig = LLMConfig()             # optional
    pact: PactIntegrationConfig = PactIntegrationConfig() # optional
    arbiter: ArbiterConfig = ArbiterConfig() # optional
    stigmergy: StigmergyConfig = StigmergyConfig() # optional
    notify: NotifyConfig = NotifyConfig()    # optional
    ledger: LedgerConfig = LedgerConfig()    # optional
    budget: BudgetConfig = BudgetConfig()    # optional
    auto_remediate: bool = False             # optional
    state_dir: str = .sentinel               # optional

def load_config(
    path: Path | None = None,
) -> SentinelConfig:
    """
    Load sentinel.yaml from the given path, cwd, or defaults. Search order: explicit path, ./sentinel.yaml, ~/.sentinel/sentinel.yaml. Returns default config if no file found.

    Postconditions:
      - Returns a valid SentinelConfig instance
      - If no config file is found or all loads fail, returns default SentinelConfig()
      - If a valid config file is found, returns validated config from that file

    Errors:
      - file_read_error (Exception): File exists but cannot be read
          handling: Caught, logged as warning, continues to next candidate
      - yaml_parse_error (yaml.YAMLError): YAML file is malformed
          handling: Caught, logged as warning, continues to next candidate
      - validation_error (pydantic.ValidationError): YAML data fails Pydantic validation
          handling: Caught, logged as warning, continues to next candidate

    Side effects: Reads files from filesystem, Logs warnings when config file loading fails
    Idempotent: yes
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['SourceConfig', 'ErrorThresholdConfig', 'LLMConfig', 'PactIntegrationConfig', 'ArbiterConfig', 'StigmergyConfig', 'NotifyConfig', 'LedgerConfig', 'BudgetConfig', 'SentinelConfig', 'load_config']
