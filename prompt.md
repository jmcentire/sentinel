# Sentinel — System Context

## What It Is
Production attribution and contract tightening. Watches logs for PACT-keyed errors, attributes them to components, and spawns LLM fixer agents that push tightened contracts back to Pact.

## How It Works
Signal pipeline: Ingest -> Attribute (PACT keys) -> Severity -> Dedup (fingerprint) -> Incident -> Triage -> Remediate -> Tighten -> Integrate

## Key Constraints
- Budget enforcement across multiple time windows (C001)
- No concurrent duplicate fixers (C002)
- Reproduce before fix (C003)
- Fire-and-forget for Arbiter/Stigmergy (C004)
- Non-blocking Ledger startup (C005)
- Local fallback for Pact contract push (C006)

## Architecture
21 source modules. Core: sentinel.py (orchestrator), watcher.py (ingestion), fixer.py (LLM remediation), incidents.py (lifecycle + budget).

## Integrations
- Pact: component registration, contract tightening (CLI or API, local fallback)
- Arbiter: trust events (fire-and-forget)
- Stigmergy: signals (fire-and-forget)
- Ledger: severity mappings at startup (non-blocking)

## Done Checklist
- [ ] Budget enforcement tested across all time windows
- [ ] Fixer dedup prevents concurrent spawns
- [ ] Integration failures don't crash Sentinel
- [ ] Proposed contracts written locally when Pact unavailable
- [ ] Error fingerprinting deduplicates correctly
