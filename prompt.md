# Sentinel Chronicler Integration

## Overview
Integrate Sentinel's incident lifecycle management with the Chronicler system for event sequence tracking. This integration enables external systems to observe and analyze incident patterns across the production environment.

## Problem Statement
Sentinel currently manages incident lifecycles internally but doesn't expose these state transitions to external observability systems. The Chronicler system needs visibility into incident progression to support broader system analysis and correlation.

## Requirements

### Functional Requirements
- **Event Emission**: Convert incident lifecycle transitions to Chronicler event sequences
- **Fire-and-Forget**: Chronicler unavailability must not impact Sentinel's core functionality
- **Lifecycle Coverage**: Emit events for all incident state transitions (detected → triaging → remediating → resolved/escalated)
- **Backward Compatibility**: Feature disabled by default, no impact on existing functionality

### Technical Requirements
- Follow existing integration pattern (arbiter.py, stigmergy.py)
- Implement ChroniclerEmitter in src/sentinel/chronicler.py
- Add chronicler configuration section to sentinel.yaml
- Wire into orchestrator after incident resolution/escalation
- Maintain all existing test coverage

### Configuration Schema
```yaml
chronicler:
  enabled: false
  endpoint: "http://chronicler-service:8080/events"
  timeout: 5.0
```

### Event Sequence Format
Each incident lifecycle transition should generate an event with:
- Incident ID
- Timestamp
- State transition (detected/triaging/remediating/resolved/escalated)
- Component attribution
- Error context (PACT key, error signature)

## Integration Points
- Wire into orchestrator after `_resolve_incident()` and `_escalate_incident()`
- Consider additional wiring for earlier lifecycle transitions based on observability needs
- Follow fire-and-forget pattern: log failures but don't propagate errors

## Success Criteria
- All existing tests pass
- Chronicler integration follows established patterns
- Configuration maintains backward compatibility
- Event emission is reliable but non-blocking