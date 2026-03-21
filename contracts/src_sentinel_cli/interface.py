# === Sentinel CLI (src_sentinel_cli) v1 ===
#  Dependencies: asyncio, json, sys, pathlib, click, yaml, sentinel.config, sentinel.sentinel, sentinel.manifest, sentinel.schemas, sentinel.llm, sentinel.triage, sentinel.incidents, sentinel.api, re, datetime
# Command-line interface for Sentinel production attribution and contract tightening system. Provides commands for initialization, component registration, log watching, error triage, manual fixes, status reporting, and API server management.

# Module invariants:
#   - Click context object (ctx.obj) is always a dict after main() executes
#   - ctx.obj['config'] always contains a SentinelConfig instance
#   - All file paths use pathlib.Path for cross-platform compatibility
#   - .sentinel/ directory structure: manifest.json and proposed_contracts/ subdirectory

def main(
    ctx: click.Context,
    config_path: str | None = None,
) -> None:
    """
    Root CLI command group that loads configuration and sets up context for all subcommands.

    Postconditions:
      - ctx.obj is a dict
      - ctx.obj['config'] contains loaded SentinelConfig
      - ctx.obj['config_path'] contains Path or None

    Side effects: Loads configuration from file or defaults, Mutates click Context object
    Idempotent: no
    """
    ...

def init() -> None:
    """
    Initialize .sentinel/ directory structure and sentinel.yaml configuration file in current directory (FA-S-001).

    Postconditions:
      - .sentinel/ directory exists
      - .sentinel/manifest.json exists with empty components dict
      - .sentinel/proposed_contracts/ directory exists
      - sentinel.yaml exists if it didn't before

    Side effects: Creates .sentinel/ directory, Writes .sentinel/manifest.json, Creates .sentinel/proposed_contracts/ directory, Creates sentinel.yaml if not exists, Prints status messages to stdout
    Idempotent: yes
    """
    ...

def watch(
    ctx: click.Context,
) -> None:
    """
    Start watching configured log sources in long-running mode (FA-S-003). Exits with code 1 if no sources configured.

    Preconditions:
      - ctx.obj['config'] is loaded
      - config.sources must be non-empty (enforced with sys.exit(1))

    Postconditions:
      - Sentinel watcher runs until interrupted or error

    Errors:
      - no_sources_configured (sys.exit): config.sources is empty
          exit_code: 1
      - keyboard_interrupt (KeyboardInterrupt): User presses Ctrl+C
          handling: Graceful shutdown with sentinel.stop()

    Side effects: Imports sentinel.sentinel.Sentinel, Runs async event loop, Monitors log sources continuously, Prints messages to stdout/stderr
    Idempotent: no
    """
    ...

def register(
    ctx: click.Context,
    directory: str,
) -> None:
    """
    Register all components from a Pact project directory (FA-S-002). Scans directory for components and adds them to manifest.

    Preconditions:
      - directory path exists (enforced by click.Path(exists=True))

    Postconditions:
      - All discovered components are registered in manifest
      - Success message printed with count

    Side effects: Imports sentinel.manifest.ManifestManager, Scans directory for component files, Writes to manifest file, Prints registration status to stdout
    Idempotent: no
    """
    ...

def manifest() -> None:
    """
    CLI command group for managing the component manifest. No operation itself, just a grouping command.

    Side effects: none
    Idempotent: yes
    """
    ...

def manifest_show(
    ctx: click.Context,
) -> None:
    """
    Show all registered components from the manifest with their metadata.

    Postconditions:
      - All manifest entries printed to stdout or 'no components' message shown

    Side effects: Imports sentinel.manifest.ManifestManager, Reads manifest file, Prints component details to stdout
    Idempotent: yes
    """
    ...

def manifest_add(
    ctx: click.Context,
    component_id: str,
    contract: str = None,
    tests: str = None,
    source: str = None,
    language: str = python,
    project: str = None,
) -> None:
    """
    Manually add a single component to the manifest with specified metadata.

    Postconditions:
      - Component registered in manifest
      - Success message printed

    Side effects: Imports sentinel.manifest.ManifestManager and sentinel.schemas.ManifestEntry, Writes to manifest file, Prints confirmation to stdout
    Idempotent: no
    """
    ...

def triage(
    ctx: click.Context,
    error_text: str,
    manifest_path: str | None = None,
) -> None:
    """
    Manually triage an error to find the responsible component (FA-S-025). Uses PACT key pattern matching first, falls back to LLM if needed.

    Preconditions:
      - At least one component must be registered (exits with code 1 otherwise)

    Postconditions:
      - Prints component_id, confidence, and reasoning to stdout

    Errors:
      - no_components_registered (sys.exit): manifest.all_entries() is empty
          exit_code: 1
      - llm_unavailable (handled): ImportError or RuntimeError when using LLM
          handling: Reports unknown component with confidence 0.0

    Side effects: Imports re, datetime, ManifestManager, Signal, possibly LLMClient and triage_signal, Reads manifest, May call LLM API, Prints triage results to stdout
    Idempotent: yes
    """
    ...

def fix(
    ctx: click.Context,
    pact_key: str,
    error: str,
) -> None:
    """
    Manually trigger a fix for a PACT key and error text (FA-S-023). Invokes Sentinel's handle_manual_fix workflow.

    Postconditions:
      - Fix result printed as JSON to stdout

    Side effects: Imports sentinel.sentinel.Sentinel, Runs async event loop, Calls Sentinel startup and handle_manual_fix, May call LLM, modify files, run tests, Prints JSON result to stdout
    Idempotent: no
    """
    ...

def report(
    ctx: click.Context,
) -> None:
    """
    Show recent incidents and fix history from the incident manager.

    Postconditions:
      - Recent incidents printed to stdout or 'no incidents' message

    Side effects: Imports sentinel.incidents.IncidentManager and sentinel.schemas.MonitoringBudget, Reads incident storage, Prints incident summaries to stdout
    Idempotent: yes
    """
    ...

def status(
    ctx: click.Context,
) -> None:
    """
    Show Sentinel configuration, integration connectivity, and component count.

    Postconditions:
      - Configuration and status summary printed to stdout

    Side effects: Imports sentinel.manifest.ManifestManager, Reads manifest to count components, Prints configuration summary to stdout
    Idempotent: yes
    """
    ...

def serve(
    ctx: click.Context,
    host: str = 0.0.0.0,
    port: int = 8484,
) -> None:
    """
    Start the HTTP API server on specified host and port. Runs until interrupted.

    Postconditions:
      - API server runs until interrupted

    Errors:
      - keyboard_interrupt (KeyboardInterrupt): User presses Ctrl+C
          handling: Graceful shutdown

    Side effects: Imports sentinel.api.SentinelAPI and sentinel.sentinel.Sentinel, Starts HTTP server, Runs async event loop, Listens on network socket
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['main', 'init', 'watch', 'KeyboardInterrupt', 'register', 'manifest', 'manifest_show', 'manifest_add', 'triage', 'handled', 'fix', 'report', 'status', 'serve']
