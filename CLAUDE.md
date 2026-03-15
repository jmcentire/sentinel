# Sentinel

Production attribution and contract tightening. Watches logs for PACT-keyed errors, attributes them to components, and spawns LLM fixer agents that push tightened contracts back to Pact.

## Quick Reference

```bash
sentinel init                              # initialize .sentinel/ and sentinel.yaml
sentinel watch                             # start watching log sources
sentinel register <directory>              # register components from Pact project
sentinel fix <pact_key> <error_text>       # manually trigger a fix
sentinel report                            # show recent incidents
sentinel status                            # show config and integration connectivity
sentinel serve                             # start HTTP API (port 8484)
python3 -m pytest tests/ -v               # run tests
```

## Architecture

Signal pipeline:
1. **Ingest** — watch logs (file tail, CloudWatch, webhook, stdout)
2. **Attribute** — extract PACT keys (regex: `PACT:[a-zA-Z0-9_]+:[a-zA-Z0-9_]+`)
3. **Severity** — compute from error context, override via Ledger mappings
4. **Dedup** — fingerprint errors (normalize, SHA256 truncated to 16 chars)
5. **Incident** — create/update incident (detected -> triaging -> remediating -> resolved/escalated)
6. **Triage** — if unattributed, LLM guesses component
7. **Remediate** — spawn fixer agent if threshold reached and budget allows
8. **Fix cycle** — LLM reproducer test -> LLM fix -> test validation -> git commit
9. **Tighten** — push tightened contract to Pact
10. **Integrate** — report to Arbiter (trust), Stigmergy (signals), notify webhooks

## Structure

```
src/sentinel/
  sentinel.py          # Main orchestrator (17KB)
  cli.py               # Click CLI, 9 commands
  config.py            # sentinel.yaml loader (Pydantic)
  schemas.py           # All Pydantic data models
  watcher.py           # Signal ingestion (log tail, webhook, CloudWatch)
  attribution.py       # PACT key extraction, manifest lookup
  severity.py          # Severity computation + Ledger overrides
  incidents.py         # Incident lifecycle + budget enforcement
  fixer.py             # LLM-driven fixer agent (14KB)
  contracts.py         # Contract tightening + Pact push
  triage.py            # LLM triage for unattributed errors
  test_runner.py       # Subprocess test runner
  git_ops.py           # Git snapshot/commit/revert
  events.py            # Internal event bus (async)
  manifest.py          # Component registry (.sentinel/manifest.json)
  notify.py            # Webhook notifications
  api.py               # HTTP API (aiohttp, port 8484)
  llm.py               # Anthropic API wrapper
  arbiter.py           # Arbiter trust event client (fire-and-forget)
  stigmergy.py         # Stigmergy signal client (fire-and-forget)
  ledger.py            # Ledger severity mapping client
```

## Integrations

| System | Direction | What | Degradation |
|--------|-----------|------|-------------|
| Pact | Push | Tightened contracts (CLI or API) | Write to .sentinel/proposed_contracts/ |
| Arbiter | Push | Trust events (production_error: -0.3, fix: +1.5, fix_failure: -0.5) | Skip silently |
| Stigmergy | Push | Signals (fix_applied, fix_failed, production_error, contract_tightened) | Skip silently |
| Ledger | Pull | Severity mappings at startup | Use defaults |

## Budget Model

Multi-window spending caps: per-incident, hourly, daily, weekly, monthly. Each LLM fix has a `budget_per_fix` limit. Total spend tracked across all windows.

## Conventions

- Python 3.12+, Pydantic v2, Click, aiohttp, hatchling, pytest
- Async throughout (sentinel.py, watcher.py, fixer.py, all API clients)
- Fire-and-forget for Arbiter/Stigmergy (never raise, log at debug)
- Manifest persistence: .sentinel/manifest.json
- Incident state: .sentinel/monitoring/
- Proposed contracts: .sentinel/proposed_contracts/
- Exponential backoff on log source unavailability (max 60s)
- No concurrent duplicate fixer spawns
- Tests: 15 files, pytest-asyncio (auto mode)

## Kindex

Sentinel captures discoveries, decisions, and incident patterns in [Kindex](~/Code/kindex). Search before adding. Link related concepts.
