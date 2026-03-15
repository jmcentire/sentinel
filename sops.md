# Sentinel — Standards of Practice

## Language & Runtime
- Python 3.12+
- Async throughout (aiohttp for HTTP, asyncio for orchestration)
- Type hints on all public functions

## Data Models
- Pydantic v2 (BaseModel, ConfigDict)
- Frozen models for signals, incidents, fix results
- Mutable models for runtime state (manifest, config)

## CLI
- Click framework
- 9 commands: init, watch, register, manifest, fix, report, status, serve

## Testing
- pytest with pytest-asyncio (auto mode)
- One test file per source module
- All tests run without external services
- Mock Arbiter/Stigmergy/Ledger/Pact in tests

## Integration Rules
- Arbiter/Stigmergy: fire-and-forget (2s timeout, never raise)
- Ledger: non-blocking startup (use defaults if unavailable)
- Pact: CLI push preferred, API fallback, local file last resort

## Error Handling
- Never crash on integration failure
- Log integration errors at debug level
- Fingerprint errors for deduplication (normalize + SHA256[:16])

## Conventions
- snake_case functions, PascalCase classes
- Prefer stdlib over third-party
- Keep files under 300 lines (fixer.py and sentinel.py are exceptions)
- All file I/O via pathlib
- UTC timestamps everywhere
