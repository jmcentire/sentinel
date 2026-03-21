# === Arbiter Trust Ledger HTTP Client (src_sentinel_arbiter) v1 ===
#  Dependencies: logging, datetime, aiohttp, sentinel.config
# HTTP client for reporting trust events to the Arbiter API after fixes. Provides fire-and-forget posting of trust events including fix successes, fix failures, and production errors with configurable weights.

# Module invariants:
#   - HTTP timeout is always 5 seconds for all requests
#   - report_fix_success uses event='sentinel_fix' with weight=1.5
#   - report_fix_failure uses event='sentinel_fix_failure' with weight=-0.5
#   - report_production_error uses event='production_error' with weight=-0.3
#   - All trust events include automatically-generated ISO timestamp
#   - All methods return bool indicating success/failure rather than raising exceptions
#   - Fix-related reports (_fix_success, _fix_failure) are gated by _trust_on_fix config flag
#   - Production error reports are NOT gated by _trust_on_fix flag

class ArbiterClient:
    """Posts trust events to the Arbiter API. Fire-and-forget. Maintains endpoint configuration and trust reporting settings."""
    _endpoint: str | None                    # required, API endpoint URL from config
    _trust_on_fix: bool                      # required, Whether to report trust events on fix operations from config

def __init__(
    config: ArbiterConfig,
) -> None:
    """
    Initialize ArbiterClient with configuration. Extracts api_endpoint and trust_event_on_fix from config object.

    Preconditions:
      - config must be an instance of ArbiterConfig with api_endpoint and trust_event_on_fix attributes

    Postconditions:
      - _endpoint is set to config.api_endpoint
      - _trust_on_fix is set to config.trust_event_on_fix

    Side effects: mutates_state
    Idempotent: no
    """
    ...

def is_configured() -> bool:
    """
    Check if the client is configured with a valid endpoint. Returns True if _endpoint is not None.

    Postconditions:
      - Returns True if _endpoint is not None
      - Returns False if _endpoint is None

    Side effects: none
    Idempotent: no
    """
    ...

def report_trust_event(
    node_id: str,
    event: str,
    weight: float,
    run_id: str = "",
) -> bool:
    """
    POST trust event to /trust/event endpoint. Returns True on success (2xx response), False on failure or if not configured. Adds timestamp automatically.

    Postconditions:
      - Returns False if not configured
      - Returns True on successful POST (status < 300)
      - Returns False on POST failure or exception
      - Payload includes timestamp in ISO format

    Errors:
      - not_configured (bool): _endpoint is None
          returns: False

    Side effects: network_call, logging
    Idempotent: no
    """
    ...

def _post(
    url: str,
    payload: dict,
) -> bool:
    """
    POST JSON payload to a URL. Returns True on 2xx status codes, False otherwise. Uses 5-second timeout. Catches all exceptions and returns False.

    Postconditions:
      - Returns True if response status < 300
      - Returns False if response status >= 300
      - Returns False if any exception occurs
      - Logs debug message on non-2xx response or exception

    Errors:
      - http_error (bool): HTTP status >= 300
          returns: False
      - network_exception (bool): Any exception during HTTP request (timeout, connection error, etc.)
          returns: False

    Side effects: network_call, logging
    Idempotent: no
    """
    ...

def report_fix_success(
    component_id: str,
    run_id: str = "",
) -> bool:
    """
    Report a successful fix with trust boost. Returns False if trust_on_fix is disabled, otherwise calls report_trust_event with event='sentinel_fix' and weight=1.5.

    Postconditions:
      - Returns False if _trust_on_fix is False
      - Otherwise returns result of report_trust_event with event='sentinel_fix', weight=1.5

    Errors:
      - trust_on_fix_disabled (bool): _trust_on_fix is False
          returns: False

    Side effects: network_call, logging
    Idempotent: no
    """
    ...

def report_fix_failure(
    component_id: str,
    run_id: str = "",
) -> bool:
    """
    Report a failed fix with trust penalty. Returns False if trust_on_fix is disabled, otherwise calls report_trust_event with event='sentinel_fix_failure' and weight=-0.5.

    Postconditions:
      - Returns False if _trust_on_fix is False
      - Otherwise returns result of report_trust_event with event='sentinel_fix_failure', weight=-0.5

    Errors:
      - trust_on_fix_disabled (bool): _trust_on_fix is False
          returns: False

    Side effects: network_call, logging
    Idempotent: no
    """
    ...

def report_production_error(
    component_id: str,
    run_id: str = "",
) -> bool:
    """
    Report production error detection with trust reduction. Calls report_trust_event with event='production_error' and weight=-0.3. Not gated by _trust_on_fix.

    Postconditions:
      - Returns result of report_trust_event with event='production_error', weight=-0.3

    Side effects: network_call, logging
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['ArbiterClient', 'is_configured', 'report_trust_event', '_post', 'report_fix_success', 'report_fix_failure', 'report_production_error']
