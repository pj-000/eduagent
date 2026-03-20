"""End-to-end tests using FakeProvider."""
from __future__ import annotations

import asyncio
import json
import pytest
from pathlib import Path

from eduagent.logging.event_sink import EventSink
from eduagent.models.events import EventType
from eduagent.providers.fake import FakeProvider
from eduagent.registry.artifact_registry import ArtifactRegistry
from eduagent.services.replay_service import ReplayService
from eduagent.services.run_service import RunService


@pytest.fixture
def tmp_registry(tmp_path):
    return ArtifactRegistry(base_dir=tmp_path / "artifacts")


@pytest.mark.asyncio
async def test_simple_run_with_final_answer(tmp_path, tmp_registry):
    """Single agent produces final_answer immediately."""
    provider = FakeProvider(responses=[
        json.dumps({
            "action_type": "final_answer",
            "payload": {"content": "Task completed successfully", "artifact_ids": []}
        }),
    ])

    service = RunService(
        registry=tmp_registry,
        providers={"default": provider},
        runs_dir=str(tmp_path / "runs"),
        max_rounds=5,
    )

    run_id = await service.create_run(task="simple test", cli_display=False)
    task = await service.start_run(run_id)
    await task

    info = service.get_run(run_id)
    assert info["status"] == "completed"
    assert info["final_answer"] == "Task completed successfully"


@pytest.mark.asyncio
async def test_multi_step_run(tmp_path, tmp_registry):
    """Planner sends message then produces final_answer."""
    provider = FakeProvider(responses=[
        json.dumps({
            "action_type": "send_message",
            "payload": {"content": "Analyzing the task..."}
        }),
        json.dumps({
            "action_type": "call_tool",
            "payload": {"tool_name": "generate_math_problems", "arguments": {"grade": 3, "count": 5}}
        }),
        json.dumps({
            "action_type": "final_answer",
            "payload": {"content": "Generated 5 math problems for grade 3", "artifact_ids": []}
        }),
    ])

    service = RunService(
        registry=tmp_registry,
        providers={"default": provider},
        runs_dir=str(tmp_path / "runs"),
        max_rounds=10,
    )

    run_id = await service.create_run(task="generate math problems", cli_display=False)
    task = await service.start_run(run_id)
    await task

    info = service.get_run(run_id)
    assert info["status"] == "completed"

    # Verify events were persisted
    events = EventSink.load_events(Path(tmp_path / "runs" / run_id))
    assert len(events) > 0
    event_types = [e.event_type for e in events]
    assert EventType.RUN_STARTED in event_types
    assert EventType.RUN_COMPLETED in event_types


@pytest.mark.asyncio
async def test_handoff_between_agents(tmp_path, tmp_registry):
    """Planner hands off to builder, builder creates draft, then final answer."""
    planner_provider = FakeProvider(responses=[
        json.dumps({
            "action_type": "handoff",
            "payload": {"target_agent": "builder", "reason": "Need to create a tool"}
        }),
        # After builder hands back
        json.dumps({
            "action_type": "final_answer",
            "payload": {"content": "Tool creation initiated", "artifact_ids": []}
        }),
    ])

    builder_provider = FakeProvider(responses=[
        json.dumps({
            "action_type": "create_executable_tool_draft",
            "payload": {
                "name": "test_tool",
                "description": "A test tool",
                "input_schema": {},
                "output_schema": {},
                "entrypoint": "run",
                "code": "def run():\n    return {'result': 42}",
                "safety_mode": "restricted"
            }
        }),
        json.dumps({
            "action_type": "handoff",
            "payload": {"target_agent": "reviewer", "reason": "Draft ready for review"}
        }),
    ])

    reviewer_provider = FakeProvider(responses=[
        json.dumps({
            "action_type": "submit_review",
            "payload": {
                "artifact_id": "__PENDING__",
                "approve": True,
                "scores": {"correctness": 0.9, "safety": 1.0},
                "rationale": "Looks good",
                "required_revisions": []
            }
        }),
    ])

    user_sim_provider = FakeProvider(responses=[
        json.dumps({
            "action_type": "submit_review",
            "payload": {
                "artifact_id": "__PENDING__",
                "approve": True,
                "scores": {"usability": 0.9},
                "rationale": "Useful",
                "required_revisions": []
            }
        }),
    ])

    service = RunService(
        registry=tmp_registry,
        providers={
            "default": planner_provider,
            "planner": planner_provider,
            "builder": builder_provider,
            "reviewer": reviewer_provider,
            "user_simulator": user_sim_provider,
        },
        runs_dir=str(tmp_path / "runs"),
        max_rounds=10,
    )

    run_id = await service.create_run(task="create a tool", cli_display=False)
    task = await service.start_run(run_id)
    await task

    info = service.get_run(run_id)
    assert info["status"] == "completed"

    # Verify events contain handoff
    events = EventSink.load_events(Path(tmp_path / "runs" / run_id))
    event_types = [e.event_type for e in events]
    assert EventType.AGENT_HANDOFF in event_types


@pytest.mark.asyncio
async def test_replay_scenario_a(tmp_path, tmp_registry):
    """Replay scenario-a: create executable tool."""
    service = ReplayService(
        registry=tmp_registry,
        runs_dir=str(tmp_path / "runs"),
    )

    run_id = await service.replay("scenario-a", cli_display=False)
    events = EventSink.load_events(Path(tmp_path / "runs" / run_id))
    assert len(events) > 0

    event_types = [e.event_type for e in events]
    assert EventType.RUN_STARTED in event_types
    assert EventType.RUN_COMPLETED in event_types


@pytest.mark.asyncio
async def test_event_persistence_and_load(tmp_path, tmp_registry):
    """Verify events can be persisted and loaded back."""
    provider = FakeProvider(responses=[
        json.dumps({
            "action_type": "final_answer",
            "payload": {"content": "done", "artifact_ids": []}
        }),
    ])

    service = RunService(
        registry=tmp_registry,
        providers={"default": provider},
        runs_dir=str(tmp_path / "runs"),
    )

    run_id = await service.create_run(task="persistence test", cli_display=False)
    task = await service.start_run(run_id)
    await task

    # Load events from disk
    events = EventSink.load_events(Path(tmp_path / "runs" / run_id))
    assert len(events) >= 2  # At least RUN_STARTED and RUN_COMPLETED

    # Verify sequence numbers are monotonically increasing
    for i in range(1, len(events)):
        assert events[i].sequence_number > events[i - 1].sequence_number

    # Verify all events have the correct run_id
    for e in events:
        assert e.run_id == run_id
