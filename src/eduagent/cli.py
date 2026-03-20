"""CLI entry point."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .logging.event_sink import EventSink
from .models.events import EventType, RuntimeEvent
from .registry.artifact_registry import ArtifactRegistry
from .services.artifact_service import ArtifactService
from .services.replay_service import ReplayService, SCENARIOS
from .services.run_service import RunService

console = Console()


def _get_registry() -> ArtifactRegistry:
    return ArtifactRegistry(base_dir="artifacts")


def _get_default_providers() -> dict:
    from .providers.dashscope import DashScopeProvider
    provider = DashScopeProvider()
    return {"default": provider}


@click.group()
def cli():
    """EduAgent: Multi-agent educational capability creation system."""
    pass


@cli.command()
@click.argument("task")
@click.option("--max-rounds", default=20, help="Maximum rounds")
def run(task: str, max_rounds: int):
    """Create and execute a run, streaming events to console."""
    asyncio.run(_run_async(task, max_rounds))


async def _run_async(task: str, max_rounds: int):
    registry = _get_registry()
    providers = _get_default_providers()
    service = RunService(
        registry=registry,
        providers=providers,
        runs_dir="runs",
        max_rounds=max_rounds,
    )

    run_id = await service.create_run(task=task, cli_display=True)
    console.print(f"[bold]Run created:[/bold] {run_id}")
    console.print(f"[dim]Task:[/dim] {task}")
    console.print()

    bg_task = await service.start_run(run_id)
    await bg_task

    info = service.get_run(run_id)
    console.print()
    if info and info["status"] == "completed":
        console.print(f"[bold green]Run completed[/bold green] in {info['round_number']} rounds")
        if info.get("final_answer"):
            console.print(f"[bold]Answer:[/bold] {info['final_answer']}")
    elif info:
        console.print(f"[bold red]Run failed:[/bold red] {info.get('error', 'unknown')}")


@cli.command()
@click.argument("run_id")
def inspect(run_id: str):
    """Inspect a completed run by reading its event log."""
    run_dir = Path("runs") / run_id
    if not run_dir.exists():
        console.print(f"[red]Run directory not found:[/red] {run_dir}")
        return

    events = EventSink.load_events(run_dir)
    if not events:
        console.print("[yellow]No events found for this run.[/yellow]")
        return

    table = Table(title=f"Run {run_id} — {len(events)} events")
    table.add_column("#", style="dim", width=4)
    table.add_column("Type", width=22)
    table.add_column("Agent", width=16)
    table.add_column("Round", width=6)
    table.add_column("Step", width=5)
    table.add_column("Summary", max_width=60)

    for e in events:
        summary = _event_summary(e)
        table.add_row(
            str(e.sequence_number),
            e.event_type.value,
            e.agent_id or "-",
            str(e.round_number),
            str(e.step_in_turn) if e.step_in_turn is not None else "-",
            summary,
        )

    console.print(table)


def _event_summary(e: RuntimeEvent) -> str:
    p = e.payload
    match e.event_type:
        case EventType.RUN_STARTED:
            return p.get("task", "")[:60]
        case EventType.ACTION_CREATED:
            return p.get("action_type", "")
        case EventType.ACTION_RESULT:
            ok = "ok" if p.get("success") else "FAIL"
            err = p.get("error", "")
            return f"{ok} {err}"[:60] if err else ok
        case EventType.AGENT_HANDOFF:
            return f"{p.get('from_agent','')} -> {p.get('to_agent','')}"
        case EventType.RUN_COMPLETED:
            return p.get("final_answer", "")[:60]
        case EventType.RUN_FAILED:
            return p.get("error_detail", "")[:60]
        case EventType.ARTIFACT_CREATED | EventType.ARTIFACT_UPDATED:
            return p.get("artifact_id", "")
        case EventType.EVALUATION_COMPLETED:
            card = p.get("evaluation_card", {})
            return f"{'APPROVE' if card.get('approve') else 'REJECT'}"
        case _:
            return ""


@cli.command()
@click.argument("scenario")
def replay(scenario: str):
    """Replay a standard scenario."""
    asyncio.run(_replay_async(scenario))


async def _replay_async(scenario: str):
    if scenario == "list":
        table = Table(title="Available Scenarios")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Description")
        for s in SCENARIOS.values():
            table.add_row(s.get("id", ""), s["name"], s["description"])
        # Use keys
        for k, v in SCENARIOS.items():
            console.print(f"  [bold]{k}[/bold]: {v['name']} — {v['description']}")
        return

    registry = _get_registry()
    service = ReplayService(registry=registry, runs_dir="runs")

    console.print(f"[bold]Replaying scenario:[/bold] {scenario}")
    console.print()

    try:
        run_id = await service.replay(scenario, cli_display=True)
        console.print()
        console.print(f"[bold green]Replay complete.[/bold green] Run ID: {run_id}")
        console.print(f"Use [bold]eduagent inspect {run_id}[/bold] to view the full trace.")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@cli.command()
@click.option("--status", default=None, help="Filter by status (draft/active/rejected)")
def artifacts(status: str | None):
    """List all artifacts."""
    asyncio.run(_artifacts_async(status))


async def _artifacts_async(status: str | None):
    registry = _get_registry()
    service = ArtifactService(registry=registry)
    items = await service.list_artifacts(status=status)

    if not items:
        console.print("[yellow]No artifacts found.[/yellow]")
        return

    table = Table(title="Artifacts")
    table.add_column("ID", width=12)
    table.add_column("Kind", width=16)
    table.add_column("Name", width=24)
    table.add_column("Status", width=10)
    table.add_column("Rev", width=4)
    table.add_column("Created By", width=12)

    for item in items:
        table.add_row(
            item["artifact_id"],
            item["kind"],
            item["name"],
            item["status"],
            str(item["revision"]),
            item["created_by"],
        )

    console.print(table)


@cli.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def purge(yes: bool):
    """Remove all draft artifacts from registry and disk."""
    asyncio.run(_purge_async(yes))


async def _purge_async(yes: bool):
    registry = _get_registry()
    all_arts = await registry.list_all()
    drafts = [a for a in all_arts if a.status.value == "draft"]

    if not drafts:
        console.print("[yellow]No draft artifacts to purge.[/yellow]")
        return

    console.print(f"Found [bold]{len(drafts)}[/bold] draft artifact(s) to remove.")
    if not yes:
        confirm = click.confirm("Proceed?", default=False)
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            return

    removed = await registry.purge_drafts()
    console.print(f"[bold green]Removed {removed} draft artifact(s).[/bold green]")
