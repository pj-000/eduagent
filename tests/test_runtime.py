"""Tests for runtime components: AgentRunner, Executor, Scheduler, Sandbox."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from eduagent.agents.base import AgentContext, BaseAgent
from eduagent.logging.event_sink import EventSink
from eduagent.models.actions import (
    ActionEnvelope,
    ActionType,
    CallToolPayload,
    FinalAnswerPayload,
    HandoffPayload,
    SendMessagePayload,
)
from eduagent.models.agent_profile import AgentProfile, AgentRole
from eduagent.models.conversation import ConversationState
from eduagent.models.results import ActionResult
from eduagent.providers.fake import FakeProvider
from eduagent.registry.artifact_registry import ArtifactRegistry
from eduagent.runtime.agent_runner import AgentRunner
from eduagent.runtime.executor import ActionExecutor
from eduagent.runtime.sandbox import Sandbox, SandboxError
from eduagent.runtime.scheduler import Scheduler


# --- Sandbox Tests ---

class TestSandbox:
    def test_valid_code(self):
        sb = Sandbox()
        code = "def run(x=1):\n    return x * 2"
        issues = sb.validate_code(code)
        assert issues == []

    def test_forbidden_import(self):
        sb = Sandbox()
        code = "import os\ndef run():\n    return os.getcwd()"
        issues = sb.validate_code(code)
        assert any("os" in i for i in issues)

    def test_forbidden_builtin(self):
        sb = Sandbox()
        code = "def run():\n    return eval('1+1')"
        issues = sb.validate_code(code)
        assert any("eval" in i for i in issues)

    def test_check_entrypoint(self):
        sb = Sandbox()
        code = "def run():\n    return 42"
        assert sb.check_entrypoint(code, "run")
        assert not sb.check_entrypoint(code, "missing")

    def test_execute_simple(self):
        sb = Sandbox()
        code = "def run(x=5):\n    return x * 2"
        result = sb.execute(code, "run", {"x": 3})
        assert result == 6

    def test_execute_no_args(self):
        sb = Sandbox()
        code = "def run():\n    return 42"
        result = sb.execute(code, "run", {})
        assert result == 42

    def test_execute_with_allowed_import(self):
        sb = Sandbox()
        code = "import math\ndef run():\n    return math.pi"
        result = sb.execute(code, "run", {})
        assert abs(result - 3.14159) < 0.001

    def test_execute_forbidden_import_raises(self):
        sb = Sandbox()
        code = "import subprocess\ndef run():\n    return 1"
        with pytest.raises(SandboxError):
            sb.execute(code, "run", {})

    def test_smoke_test_success(self):
        sb = Sandbox()
        code = "def run():\n    return {'ok': True}"
        result = sb.smoke_test(code, "run")
        assert result["success"]

    def test_smoke_test_failure(self):
        sb = Sandbox()
        code = "def run():\n    raise ValueError('boom')"
        result = sb.smoke_test(code, "run")
        assert not result["success"]
        assert "boom" in result["error"]


# --- Executor Tests ---

@pytest.fixture
def tmp_executor(tmp_path):
    registry = ArtifactRegistry(base_dir=tmp_path / "artifacts")
    sandbox = Sandbox()
    builtin = {
        "test_tool": lambda x=1: {"result": x * 10},
    }
    return ActionExecutor(registry=registry, sandbox=sandbox, builtin_tools=builtin)


@pytest.mark.asyncio
async def test_executor_send_message(tmp_executor):
    action = ActionEnvelope(
        action_type=ActionType.SEND_MESSAGE,
        agent_id="planner",
        payload=SendMessagePayload(content="hello"),
    )
    result = await tmp_executor.execute(action)
    assert result.success
    assert result.output["message"] == "hello"


@pytest.mark.asyncio
async def test_executor_call_builtin_tool(tmp_executor):
    action = ActionEnvelope(
        action_type=ActionType.CALL_TOOL,
        agent_id="planner",
        payload=CallToolPayload(tool_name="test_tool", arguments={"x": 5}),
    )
    result = await tmp_executor.execute(action)
    assert result.success
    assert result.output["result"] == 50


@pytest.mark.asyncio
async def test_executor_call_missing_tool(tmp_executor):
    action = ActionEnvelope(
        action_type=ActionType.CALL_TOOL,
        agent_id="planner",
        payload=CallToolPayload(tool_name="nonexistent"),
    )
    result = await tmp_executor.execute(action)
    assert not result.success
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_executor_handoff(tmp_executor):
    action = ActionEnvelope(
        action_type=ActionType.HANDOFF,
        agent_id="planner",
        payload=HandoffPayload(target_agent="builder", reason="need tool"),
    )
    result = await tmp_executor.execute(action)
    assert result.success
    assert result.suggested_next_agent == "builder"
    assert not result.should_continue_current_agent


@pytest.mark.asyncio
async def test_executor_final_answer(tmp_executor):
    action = ActionEnvelope(
        action_type=ActionType.FINAL_ANSWER,
        agent_id="planner",
        payload=FinalAnswerPayload(content="done"),
    )
    result = await tmp_executor.execute(action)
    assert result.success
    assert result.output["content"] == "done"


# --- Scheduler Tests ---

class FakeAgent(BaseAgent):
    async def decide_next_action(self, context: AgentContext) -> ActionEnvelope:
        return ActionEnvelope(
            action_type=ActionType.SEND_MESSAGE,
            agent_id=self.profile.agent_id,
            payload=SendMessagePayload(content="test"),
        )

    def build_prompt(self, context: AgentContext) -> list[dict[str, str]]:
        return [{"role": "user", "content": "test"}]


def _make_agents():
    agents = {}
    for role_name, role in [
        ("planner", AgentRole.PLANNER),
        ("builder", AgentRole.BUILDER),
        ("reviewer", AgentRole.REVIEWER),
        ("user_simulator", AgentRole.USER_SIMULATOR),
    ]:
        profile = AgentProfile(
            agent_id=role_name, role=role, display_name=role_name
        )
        agents[role_name] = FakeAgent(profile=profile, provider=FakeProvider())
    return agents


class TestScheduler:
    def test_initial_selects_planner(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents)
        state = ConversationState(run_id="r1", task="test")
        agent = scheduler.select_next_agent(state)
        assert agent.profile.agent_id == "planner"

    def test_handoff_follows_target(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents)
        state = ConversationState(run_id="r1", task="test")
        state.current_agent_id = "planner"
        state.last_action_result = ActionResult(
            action_id="a1",
            agent_id="planner",
            action_type="handoff",
            success=True,
            output={"target_agent": "builder", "reason": "need tool"},
            suggested_next_agent="builder",
        )
        agent = scheduler.select_next_agent(state)
        assert agent.profile.agent_id == "builder"

    def test_draft_created_goes_to_reviewer(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents)
        state = ConversationState(run_id="r1", task="test")
        state.current_agent_id = "builder"
        state.last_action_result = ActionResult(
            action_id="a1",
            agent_id="builder",
            action_type="create_executable_tool_draft",
            success=True,
            output={"artifact_id": "t1"},
        )
        agent = scheduler.select_next_agent(state)
        assert agent.profile.agent_id == "reviewer"

    def test_reviewer_goes_to_user_simulator(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents)
        state = ConversationState(run_id="r1", task="test")
        state.current_agent_id = "reviewer"
        state.last_action_result = ActionResult(
            action_id="a1",
            agent_id="reviewer",
            action_type="submit_review",
            success=True,
            output={"approve": True},
        )
        agent = scheduler.select_next_agent(state)
        assert agent.profile.agent_id == "user_simulator"

    def test_termination_on_final_answer(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents)
        state = ConversationState(run_id="r1", task="test", final_answer="done")
        assert scheduler.should_terminate(state)

    def test_termination_on_max_rounds(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents, max_rounds=5)
        state = ConversationState(run_id="r1", task="test", round_number=5)
        assert scheduler.should_terminate(state)

    def test_reviewer_reject_goes_to_builder(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents)
        state = ConversationState(run_id="r1", task="test")
        state.current_agent_id = "reviewer"
        state.last_action_result = ActionResult(
            action_id="a1",
            agent_id="reviewer",
            action_type="submit_review",
            success=True,
            output={"approve": False, "required_revisions": ["fix X"]},
        )
        agent = scheduler.select_next_agent(state)
        assert agent.profile.agent_id == "builder"

    def test_user_simulator_approve_goes_to_planner(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents)
        state = ConversationState(run_id="r1", task="test")
        state.current_agent_id = "user_simulator"
        state.last_action_result = ActionResult(
            action_id="a1",
            agent_id="user_simulator",
            action_type="submit_review",
            success=True,
            output={"approve": True},
        )
        agent = scheduler.select_next_agent(state)
        assert agent.profile.agent_id == "planner"

    def test_user_simulator_reject_goes_to_builder(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents)
        state = ConversationState(run_id="r1", task="test")
        state.current_agent_id = "user_simulator"
        state.last_action_result = ActionResult(
            action_id="a1",
            agent_id="user_simulator",
            action_type="submit_review",
            success=True,
            output={"approve": False},
        )
        agent = scheduler.select_next_agent(state)
        assert agent.profile.agent_id == "builder"

    def test_no_termination_early(self):
        agents = _make_agents()
        scheduler = Scheduler(agents=agents)
        state = ConversationState(run_id="r1", task="test", round_number=1)
        assert not scheduler.should_terminate(state)


# --- AgentRunner Tests ---

class ScriptedAgent(BaseAgent):
    """Agent that returns pre-scripted actions."""

    def __init__(self, profile, provider, actions: list[ActionEnvelope]):
        super().__init__(profile, provider)
        self._actions = list(actions)
        self._idx = 0

    async def decide_next_action(self, context: AgentContext) -> ActionEnvelope:
        if self._idx < len(self._actions):
            action = self._actions[self._idx]
            self._idx += 1
            return action
        return ActionEnvelope(
            action_type=ActionType.FINAL_ANSWER,
            agent_id=self.profile.agent_id,
            payload=FinalAnswerPayload(content="fallback"),
        )

    def build_prompt(self, context: AgentContext) -> list[dict[str, str]]:
        return [{"role": "user", "content": "test"}]


@pytest.mark.asyncio
async def test_agent_runner_single_step(tmp_path):
    registry = ArtifactRegistry(base_dir=tmp_path / "artifacts")
    event_sink = EventSink(run_id="r1", runs_dir=tmp_path / "runs", cli_display=False)
    sandbox = Sandbox()
    executor = ActionExecutor(registry=registry, sandbox=sandbox, builtin_tools={
        "test_tool": lambda: {"ok": True},
    })
    runner = AgentRunner(executor=executor, event_sink=event_sink, registry=registry)

    profile = AgentProfile(
        agent_id="planner", role=AgentRole.PLANNER, display_name="Planner"
    )
    agent = ScriptedAgent(
        profile=profile,
        provider=FakeProvider(),
        actions=[
            ActionEnvelope(
                action_type=ActionType.FINAL_ANSWER,
                agent_id="planner",
                payload=FinalAnswerPayload(content="done"),
            ),
        ],
    )

    state = ConversationState(run_id="r1", task="test")
    results = await runner.run_agent_turn(agent, state)

    assert len(results) == 1
    assert results[0].success
    assert results[0].action_type == "final_answer"

    await event_sink.close()


@pytest.mark.asyncio
async def test_agent_runner_multi_step(tmp_path):
    registry = ArtifactRegistry(base_dir=tmp_path / "artifacts")
    event_sink = EventSink(run_id="r2", runs_dir=tmp_path / "runs", cli_display=False)
    sandbox = Sandbox()
    executor = ActionExecutor(registry=registry, sandbox=sandbox, builtin_tools={
        "test_tool": lambda: {"ok": True},
    })
    runner = AgentRunner(executor=executor, event_sink=event_sink, registry=registry)

    profile = AgentProfile(
        agent_id="planner", role=AgentRole.PLANNER, display_name="Planner",
        max_actions_per_turn=5,
    )
    agent = ScriptedAgent(
        profile=profile,
        provider=FakeProvider(),
        actions=[
            ActionEnvelope(
                action_type=ActionType.SEND_MESSAGE,
                agent_id="planner",
                payload=SendMessagePayload(content="analyzing"),
            ),
            ActionEnvelope(
                action_type=ActionType.CALL_TOOL,
                agent_id="planner",
                payload=CallToolPayload(tool_name="test_tool"),
            ),
            ActionEnvelope(
                action_type=ActionType.FINAL_ANSWER,
                agent_id="planner",
                payload=FinalAnswerPayload(content="done"),
            ),
        ],
    )

    state = ConversationState(run_id="r2", task="test")
    results = await runner.run_agent_turn(agent, state)

    assert len(results) == 3
    assert results[0].action_type == "send_message"
    assert results[1].action_type == "call_tool"
    assert results[2].action_type == "final_answer"

    await event_sink.close()


@pytest.mark.asyncio
async def test_agent_runner_handoff_ends_turn(tmp_path):
    registry = ArtifactRegistry(base_dir=tmp_path / "artifacts")
    event_sink = EventSink(run_id="r3", runs_dir=tmp_path / "runs", cli_display=False)
    sandbox = Sandbox()
    executor = ActionExecutor(registry=registry, sandbox=sandbox)
    runner = AgentRunner(executor=executor, event_sink=event_sink, registry=registry)

    profile = AgentProfile(
        agent_id="planner", role=AgentRole.PLANNER, display_name="Planner",
        max_actions_per_turn=5,
    )
    agent = ScriptedAgent(
        profile=profile,
        provider=FakeProvider(),
        actions=[
            ActionEnvelope(
                action_type=ActionType.HANDOFF,
                agent_id="planner",
                payload=HandoffPayload(target_agent="builder", reason="need tool"),
            ),
            # This should NOT be reached
            ActionEnvelope(
                action_type=ActionType.SEND_MESSAGE,
                agent_id="planner",
                payload=SendMessagePayload(content="should not reach"),
            ),
        ],
    )

    state = ConversationState(run_id="r3", task="test")
    results = await runner.run_agent_turn(agent, state)

    assert len(results) == 1
    assert results[0].action_type == "handoff"

    await event_sink.close()
