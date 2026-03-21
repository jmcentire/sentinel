# Task: Add Chronicler Integration to Sentinel

## Context

This project was adopted from an existing codebase (21 source files, 162 functions, 36 test files). When Sentinel resolves or escalates an incident, it should emit the incident lifecycle as an event sequence to Chronicler. This lets Chronicler assemble incident stories that flow through Stigmergy for pattern detection.

## Specific changes

### 1. Chronicler Emitter

Add `src/sentinel/chronicler.py`:
- On incident resolution or escalation, convert the incident to a sequence of Chronicler events:
  - `incident.detected` — initial error signal
  - `incident.triaging` — attribution + severity computed
  - `incident.remediating` — fixer agent spawned
  - `incident.resolved` or `incident.escalated` — terminal event
- Each event carries: incident_id, component_id, pact_key, severity, timestamp, signal_count, spend_usd
- POST to Chronicler's webhook endpoint (configurable in sentinel.yaml)

### 2. Config

Add to `src/sentinel/config.py`:
```yaml
chronicler:
  enabled: false
  endpoint: http://localhost:8485
```

### 3. Wire into Orchestrator

In `src/sentinel/sentinel.py`:
- After `_resolve_incident()` or `_escalate_incident()`, call `chronicler_emitter.emit(incident)`
- Fire-and-forget: unreachable Chronicler doesn't block Sentinel operation

## Constraints

- Backward compatible: disabled by default
- Fire-and-forget: consistent with existing Arbiter/Stigmergy integration patterns
- No new external dependencies (use existing aiohttp or requests)
- All existing tests must pass
- Python 3.12+, Pydantic v2
