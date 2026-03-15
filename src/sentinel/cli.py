"""CLI — command-line interface for Sentinel."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
import yaml

from sentinel.config import SentinelConfig, load_config


@click.group()
@click.option("--config", "config_path", type=click.Path(exists=False), default=None, help="Path to sentinel.yaml")
@click.pass_context
def main(ctx: click.Context, config_path: str | None) -> None:
    """Sentinel — production attribution and contract tightening."""
    ctx.ensure_object(dict)
    path = Path(config_path) if config_path else None
    ctx.obj["config"] = load_config(path)
    ctx.obj["config_path"] = path


@main.command()
def init() -> None:
    """Initialize .sentinel/ directory and sentinel.yaml in current directory (FA-S-001)."""
    sentinel_dir = Path(".sentinel")
    sentinel_dir.mkdir(exist_ok=True)
    (sentinel_dir / "manifest.json").write_text('{"components": {}}')
    (sentinel_dir / "proposed_contracts").mkdir(exist_ok=True)

    config_path = Path("sentinel.yaml")
    if not config_path.exists():
        default = SentinelConfig()
        config_path.write_text(yaml.dump(
            json.loads(default.model_dump_json()),
            default_flow_style=False,
            sort_keys=False,
        ))
        click.echo(f"Created {config_path}")

    click.echo(f"Initialized {sentinel_dir}/")


@main.command()
@click.pass_context
def watch(ctx: click.Context) -> None:
    """Start watching configured log sources (long-running) (FA-S-003)."""
    config = ctx.obj["config"]
    if not config.sources:
        click.echo("No sources configured in sentinel.yaml. Add sources and retry.", err=True)
        sys.exit(1)

    from sentinel.sentinel import Sentinel

    sentinel = Sentinel(config)
    try:
        asyncio.run(sentinel.run())
    except KeyboardInterrupt:
        sentinel.stop()
        click.echo("\nSentinel stopped.")


@main.command()
@click.argument("directory", type=click.Path(exists=True))
@click.pass_context
def register(ctx: click.Context, directory: str) -> None:
    """Register all components from a Pact project directory (FA-S-002)."""
    config = ctx.obj["config"]
    state_dir = Path(config.state_dir)

    from sentinel.manifest import ManifestManager

    manifest = ManifestManager(state_dir)
    entries = ManifestManager.scan_directory(Path(directory))

    if not entries:
        click.echo(f"No components found in {directory}")
        return

    for entry in entries:
        manifest.register(entry)
        click.echo(f"  Registered: {entry.component_id}")

    click.echo(f"\nRegistered {len(entries)} components from {directory}")


@main.group()
def manifest() -> None:
    """Manage the component manifest."""


@manifest.command("show")
@click.pass_context
def manifest_show(ctx: click.Context) -> None:
    """Show all registered components."""
    config = ctx.obj["config"]
    state_dir = Path(config.state_dir)

    from sentinel.manifest import ManifestManager

    mgr = ManifestManager(state_dir)
    entries = mgr.all_entries()

    if not entries:
        click.echo("No components registered. Use 'sentinel register <dir>' to add components.")
        return

    for comp_id, entry in sorted(entries.items()):
        click.echo(f"  {comp_id}")
        click.echo(f"    contract: {entry.contract_path}")
        click.echo(f"    tests:    {entry.test_path}")
        click.echo(f"    source:   {entry.source_path}")
        click.echo(f"    language: {entry.language}")
        click.echo(f"    project:  {entry.pact_project}")
        click.echo()


@manifest.command("add")
@click.argument("component_id")
@click.option("--contract", default="", help="Path to contract file")
@click.option("--tests", default="", help="Path to test file/directory")
@click.option("--source", default="", help="Path to source file/directory")
@click.option("--language", default="python", help="Language (python/typescript)")
@click.option("--project", default="", help="Pact project directory")
@click.pass_context
def manifest_add(
    ctx: click.Context,
    component_id: str,
    contract: str,
    tests: str,
    source: str,
    language: str,
    project: str,
) -> None:
    """Manually add a component to the manifest."""
    config = ctx.obj["config"]
    state_dir = Path(config.state_dir)

    from sentinel.manifest import ManifestManager
    from sentinel.schemas import ManifestEntry

    mgr = ManifestManager(state_dir)
    entry = ManifestEntry(
        component_id=component_id,
        contract_path=contract,
        test_path=tests,
        source_path=source,
        language=language,
        pact_project=project,
    )
    mgr.register(entry)
    click.echo(f"Registered {component_id}")


@main.command()
@click.argument("pact_key")
@click.argument("error")
@click.pass_context
def fix(ctx: click.Context, pact_key: str, error: str) -> None:
    """Manually trigger a fix for a PACT key + error text (FA-S-023)."""
    config = ctx.obj["config"]

    from sentinel.sentinel import Sentinel

    sentinel = Sentinel(config)

    async def _run():
        await sentinel.startup()
        return await sentinel.handle_manual_fix(pact_key, error)

    result = asyncio.run(_run())
    click.echo(json.dumps(result.model_dump(), indent=2, default=str))


@main.command()
@click.pass_context
def report(ctx: click.Context) -> None:
    """Show recent incidents and fix history."""
    config = ctx.obj["config"]
    state_dir = Path(config.state_dir)

    from sentinel.incidents import IncidentManager
    from sentinel.schemas import MonitoringBudget

    budget = MonitoringBudget(**config.budget.model_dump())
    mgr = IncidentManager(state_dir, budget)

    incidents = mgr.get_recent_incidents(20)
    if not incidents:
        click.echo("No incidents recorded.")
        return

    for inc in incidents:
        status_marker = {
            "resolved": "[OK]",
            "escalated": "[!!]",
        }.get(inc.status, "[..]")
        click.echo(
            f"  {status_marker} {inc.id}  {inc.component_id or 'unknown':20s}  "
            f"${inc.spend_usd:.2f}  {inc.status}  {inc.created_at[:19]}"
        )


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show Sentinel configuration and integration connectivity."""
    config = ctx.obj["config"]

    click.echo("Sentinel Status")
    click.echo(f"  Config:      {ctx.obj.get('config_path') or 'defaults'}")
    click.echo(f"  State dir:   {config.state_dir}")
    click.echo(f"  Sources:     {len(config.sources)}")
    click.echo(f"  Auto-fix:    {config.auto_remediate}")
    click.echo(f"  LLM:         {config.llm.model} (${config.llm.budget_per_fix:.2f}/fix)")
    click.echo()

    click.echo("Integrations:")
    click.echo(f"  Pact:        {config.pact.project_dir or config.pact.api_endpoint or 'not configured'}")
    click.echo(f"  Arbiter:     {config.arbiter.api_endpoint or 'not configured'}")
    click.echo(f"  Stigmergy:   {config.stigmergy.endpoint or 'not configured'}")
    click.echo(f"  Ledger:      {config.ledger.ledger_api or 'not configured'}")
    click.echo(f"  Notify:      {config.notify.webhook_url or 'not configured'}")

    state_dir = Path(config.state_dir)
    from sentinel.manifest import ManifestManager

    mgr = ManifestManager(state_dir)
    click.echo(f"\n  Components:  {len(mgr.all_entries())}")


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8484, type=int, help="Bind port")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int) -> None:
    """Start the HTTP API server."""
    config = ctx.obj["config"]

    from sentinel.api import SentinelAPI
    from sentinel.sentinel import Sentinel

    sentinel = Sentinel(config)
    api = SentinelAPI(sentinel)

    async def _run():
        await sentinel.startup()
        await api.start(host, port)
        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await api.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        click.echo("\nAPI server stopped.")


if __name__ == "__main__":
    main()
