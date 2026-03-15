# Sentinel

Production attribution and contract tightening for [Pact](https://github.com/jmcentire/pact)-generated code.

Sentinel watches production logs, attributes errors to specific components via embedded PACT keys, spawns LLM-driven fixer agents, and pushes tightened contracts back to Pact — closing the feedback loop between production and specification.

## How It Works

```
Production Logs ──> Sentinel ──> Attribution ──> Fixer Agent ──> Tightened Contract
                       │              │              │                  │
                       │         PACT key       LLM generates      Pushed back
                       │         extraction     reproducer test    to Pact
                       │              │         + source fix
                       │              ▼              │
                       │         Manifest            ▼
                       │         lookup         Tests in temp dir
                       │                             │
                       ▼                             ▼
                  Arbiter trust              Git snapshot/commit
                  Stigmergy signal           Contract proposal
                  Webhook notify
```

**PACT keys** are string literals embedded in generated source code by Pact. Format: `PACT:<component_id>:<method_name>`. When an error containing a PACT key appears in production logs, Sentinel extracts it, looks up the component in its manifest, reads the contract/tests/source, and spawns a fixer.

## Install

```bash
pip install sentinel-monitor
# With LLM support:
pip install sentinel-monitor[llm]
```

## Quick Start

```bash
# Initialize in your project
sentinel init

# Register components from a Pact project
sentinel register ~/Code/my-pact-project

# Check what's registered
sentinel manifest show

# Start watching (requires sources in sentinel.yaml)
sentinel watch

# Manually trigger a fix
sentinel fix "PACT:auth_module:validate_token" "Token signature invalid: expected ES256, got RS256"

# Start the HTTP API
sentinel serve
```

## Configuration

Sentinel is configured via `sentinel.yaml`:

```yaml
version: "1.0"

sources:
  - type: file
    path: "/var/log/app/*.log"
    format: jsonl
  - type: stdout

pact_key_pattern: "PACT:[a-zA-Z0-9_]+:[a-zA-Z0-9_]+"

error_threshold:
  count: 1
  window_seconds: 300

auto_remediate: false

llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  max_tokens: 8192
  budget_per_fix: 2.00

pact:
  project_dir: ~/Code/my-project

arbiter:
  api_endpoint: http://localhost:7700

stigmergy:
  endpoint: http://localhost:8800

ledger:
  ledger_api: http://localhost:7701

notify:
  webhook_url: https://hooks.slack.com/...
  on_error: true
  on_fix: true
  on_contract_push: true

budget:
  per_incident_cap: 5.00
  hourly_cap: 10.00
  daily_cap: 25.00
```

## Architecture

Sentinel is fully standalone with no Pact Python imports. It calls Pact via subprocess for contract push operations.

```
src/sentinel/
  config.py          # sentinel.yaml loader
  schemas.py         # All data models
  cli.py             # Click CLI
  sentinel.py        # Main orchestrator
  attribution.py     # PACT key extraction + manifest lookup
  manifest.py        # .sentinel/manifest.json CRUD
  watcher.py         # Log/process/webhook signal sources
  fixer.py           # LLM fixer agent
  triage.py          # LLM triage for unattributed errors
  llm.py             # Anthropic API client
  git_ops.py         # Git snapshot/commit/revert
  test_runner.py     # Subprocess test runner
  severity.py        # Severity computation + Ledger overrides
  ledger.py          # Ledger API client
  contracts.py       # Contract tightening + Pact push
  arbiter.py         # Arbiter trust event client
  stigmergy.py       # Stigmergy signal emission
  notify.py          # Webhook notifications
  incidents.py       # Incident lifecycle + budget
  events.py          # Internal event bus
  api.py             # HTTP API
```

## CLI

| Command | Description |
|---------|-------------|
| `sentinel init` | Initialize `.sentinel/` and `sentinel.yaml` |
| `sentinel watch` | Start watching configured log sources |
| `sentinel register <dir>` | Register components from a Pact project |
| `sentinel manifest show` | Show registered components |
| `sentinel manifest add <id>` | Manually register a component |
| `sentinel fix <key> <error>` | Manually trigger a fix |
| `sentinel report` | Show recent incidents |
| `sentinel status` | Show config and integration connectivity |
| `sentinel serve` | Start the HTTP API |

## HTTP API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Health and integration connectivity |
| `/manifest` | GET | All registered components |
| `/fixes` | GET | Recent fix history |
| `/fixes/<id>` | GET | Single fix detail |
| `/fix` | POST | Manually trigger a fix |
| `/register` | POST | Register a component |
| `/metrics` | GET | Operational metrics |

## Integrations

- **Pact** — Pushes tightened contracts via `pact sentinel push-contract`
- **Arbiter** — Reports trust events (production_error, sentinel_fix, sentinel_fix_failure)
- **Stigmergy** — Emits signals for all fix outcomes (fire-and-forget)
- **Ledger** — Loads field-level severity mappings at startup (gdpr_erasable, audit_field)

## PACT Key Standard

```
Format:  PACT:<component_id>:<method_name>
Example: PACT:auth_module:validate_token
         PACT:payment_processor:charge_card

Rules:
  - component_id: alphanumeric + underscore
  - method_name: alphanumeric + underscore
  - prefix: "PACT:" (uppercase)
```

Pact embeds these in generated code at implementation time. Sentinel extracts them at error time.

## License

MIT
