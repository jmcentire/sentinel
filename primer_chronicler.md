# Sentinel: Chronicler Integration

## What This Is

A targeted modification to Sentinel (production attribution and contract tightening) to emit incident lifecycles as event sequences to Chronicler.

## Current State

Sentinel watches logs for PACT-keyed errors, attributes them to components, and spawns LLM fixer agents. Incidents have a lifecycle: detected → triaging → remediating → resolved/escalated. On resolution, Sentinel already emits events to Arbiter (trust events) and Stigmergy (signals) via fire-and-forget.

The integration pattern is established: sentinel/arbiter.py and sentinel/stigmergy.py are fire-and-forget emitters that POST to external endpoints. Failure is logged and swallowed.

## What Changes

1. Add ChroniclerEmitter (src/sentinel/chronicler.py) following existing arbiter.py/stigmergy.py pattern
2. Convert incident lifecycle to Chronicler event sequence (detected, triaging, remediating, resolved/escalated)
3. Add chronicler config section to sentinel.yaml (enabled: false, endpoint)
4. Wire into orchestrator after _resolve_incident() and _escalate_incident()

## Why

Incident stories flowing through Chronicler → Stigmergy enable pattern detection on incidents: recurring failure types, common remediation paths, components that tend to fail together. Currently Sentinel sends individual signals to Stigmergy, but the full incident lifecycle as a story carries richer sequential context.

## Constraints

- Backward compatible: disabled by default
- Fire-and-forget: unreachable Chronicler doesn't block Sentinel
- Follow existing integration pattern (arbiter.py, stigmergy.py)
- No new external dependencies
- All existing tests must pass
- Python 3.12+, Pydantic v2
