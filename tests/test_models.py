"""Tests for Pydantic models."""
from __future__ import annotations

import json

import pytest

from eduagent.models.actions import (
    ActionEnvelope,
    ActionType,
    CallToolPayload,
    CreateExecutableToolDraftPayload,
    CreatePromptSkillDraftPayload,
    FinalAnswerPayload,
    HandoffPayload,
    SendMessagePayload,
    SubmitReviewPayload,
)
from eduagent.models.artifacts import (
    ArtifactKind,
    ArtifactStatus,
    CapabilityArtifact,
    ExecutableToolSpec,
    PromptSkillSpec,
    SafetyMode,
)
from eduagent.models.conversation import ConversationState, Message
from eduagent.models.evaluation import EvaluationCard
from eduagent.models.events import EventType, RuntimeEvent
from eduagent.models.results import ActionResult


class TestArtifacts:
    def test_executable_tool_spec(self):
        tool = ExecutableToolSpec(
            artifact_id="t1",
            name="math_gen",
            description="Generates math problems",
            created_by="builder",
            input_schema={"type": "object"},
            entrypoint="run",
        )
        assert tool.kind == ArtifactKind.EXECUTABLE_TOOL
        assert tool.status == ArtifactStatus.DRAFT
        assert tool.revision == 0
        assert tool.safety_mode == SafetyMode.RESTRICTED

    def test_prompt_skill_spec(self):
        skill = PromptSkillSpec(
            artifact_id="s1",
            name="simplifier",
            description="Simplifies text",
            created_by="builder",
            trigger_guidance="simplify text",
            prompt_fragment="Please simplify...",
            allowed_tools=["simplify_text"],
        )
        assert skill.kind == ArtifactKind.PROMPT_SKILL
        assert skill.allowed_tools == ["simplify_text"]

    def test_artifact_serialization(self):
        tool = ExecutableToolSpec(
            artifact_id="t1",
            name="test",
            description="test tool",
            created_by="builder",
        )
        data = json.loads(tool.model_dump_json())
        assert data["kind"] == "executable_tool"
        assert data["status"] == "draft"
        restored = ExecutableToolSpec.model_validate(data)
        assert restored.artifact_id == "t1"


class TestActions:
    def test_action_envelope_send_message(self):
        env = ActionEnvelope(
            action_type=ActionType.SEND_MESSAGE,
            agent_id="planner",
            payload=SendMessagePayload(content="hello"),
        )
        assert env.action_type == ActionType.SEND_MESSAGE
        assert env.payload.content == "hello"

    def test_action_envelope_call_tool(self):
        env = ActionEnvelope(
            action_type=ActionType.CALL_TOOL,
            agent_id="planner",
            payload=CallToolPayload(tool_name="math_gen", arguments={"grade": 3}),
        )
        assert env.payload.tool_name == "math_gen"

    def test_action_envelope_handoff(self):
        env = ActionEnvelope(
            action_type=ActionType.HANDOFF,
            agent_id="planner",
            payload=HandoffPayload(target_agent="builder", reason="need tool"),
        )
        assert env.payload.target_agent == "builder"

    def test_action_envelope_final_answer(self):
        env = ActionEnvelope(
            action_type=ActionType.FINAL_ANSWER,
            agent_id="planner",
            payload=FinalAnswerPayload(content="done", artifact_ids=["a1"]),
        )
        assert env.payload.artifact_ids == ["a1"]

    def test_action_envelope_create_tool_draft(self):
        env = ActionEnvelope(
            action_type=ActionType.CREATE_EXECUTABLE_TOOL_DRAFT,
            agent_id="builder",
            payload=CreateExecutableToolDraftPayload(
                name="quiz",
                description="quiz gen",
                code="def run(): pass",
            ),
        )
        assert env.payload.entrypoint == "run"

    def test_action_envelope_create_skill_draft(self):
        env = ActionEnvelope(
            action_type=ActionType.CREATE_PROMPT_SKILL_DRAFT,
            agent_id="builder",
            payload=CreatePromptSkillDraftPayload(
                name="simplifier",
                description="simplify",
                trigger_guidance="simplify text",
                prompt_fragment="Please simplify",
            ),
        )
        assert env.payload.trigger_guidance == "simplify text"

    def test_action_envelope_submit_review(self):
        env = ActionEnvelope(
            action_type=ActionType.SUBMIT_REVIEW,
            agent_id="reviewer",
            payload=SubmitReviewPayload(
                artifact_id="a1",
                approve=True,
                scores={"correctness": 0.9},
                rationale="looks good",
            ),
        )
        assert env.payload.approve is True

    def test_action_serialization_roundtrip(self):
        env = ActionEnvelope(
            action_type=ActionType.CALL_TOOL,
            agent_id="planner",
            payload=CallToolPayload(tool_name="test", arguments={"x": 1}),
        )
        data = json.loads(env.model_dump_json())
        assert data["action_type"] == "call_tool"


class TestResults:
    def test_action_result(self):
        r = ActionResult(
            action_id="a1",
            agent_id="planner",
            action_type="call_tool",
            success=True,
            output={"result": 42},
        )
        assert r.success
        assert r.should_continue_current_agent

    def test_action_result_failure(self):
        r = ActionResult(
            action_id="a2",
            agent_id="planner",
            action_type="call_tool",
            success=False,
            error="Tool not found",
        )
        assert not r.success
        assert r.error == "Tool not found"

    def test_action_result_serialization(self):
        r = ActionResult(
            action_id="a1",
            agent_id="planner",
            action_type="final_answer",
            success=True,
            output={"content": "done"},
        )
        data = json.loads(r.model_dump_json())
        assert data["action_type"] == "final_answer"


class TestConversation:
    def test_conversation_state(self):
        state = ConversationState(run_id="r1", task="test task")
        assert state.round_number == 0
        assert not state.terminated
        assert state.shared_messages == []

    def test_message(self):
        m = Message(role="user", content="hello", agent_id="planner")
        assert m.role == "user"


class TestEvaluation:
    def test_evaluation_card(self):
        card = EvaluationCard(
            artifact_id="a1",
            evaluator_id="reviewer",
            scores={"correctness": 0.9, "safety": 1.0},
            approve=True,
            rationale="Good",
        )
        assert card.approve
        assert card.scores["safety"] == 1.0


class TestEvents:
    def test_runtime_event(self):
        e = RuntimeEvent(
            event_type=EventType.RUN_STARTED,
            run_id="r1",
            payload={"task": "test"},
        )
        assert e.event_type == EventType.RUN_STARTED
        assert e.sequence_number == 0

    def test_event_serialization(self):
        e = RuntimeEvent(
            event_type=EventType.ACTION_CREATED,
            run_id="r1",
            agent_id="planner",
            step_in_turn=0,
            payload={"action_type": "call_tool"},
        )
        line = e.model_dump_json()
        restored = RuntimeEvent.model_validate_json(line)
        assert restored.event_type == EventType.ACTION_CREATED
        assert restored.agent_id == "planner"

    def test_all_event_types(self):
        for et in EventType:
            e = RuntimeEvent(event_type=et, run_id="r1")
            assert e.event_type == et
