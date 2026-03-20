"""Action executor: executes ActionEnvelope -> ActionResult."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from ..models.actions import (
    ActionEnvelope,
    ActionType,
    ActivateArtifactPayload,
    CallToolPayload,
    CreateExecutableToolDraftPayload,
    CreatePromptSkillDraftPayload,
    FinalAnswerPayload,
    HandoffPayload,
    RejectArtifactPayload,
    SendMessagePayload,
    SubmitReviewPayload,
)
from ..models.artifacts import (
    ArtifactStatus,
    ExecutableToolSpec,
    PromptSkillSpec,
)
from ..models.evaluation import EvaluationCard
from ..models.results import ActionResult
from ..evaluation.evaluator import Evaluator
from ..evaluation.rule_checker import RuleChecker
from ..registry.artifact_registry import ArtifactRegistry
from .sandbox import Sandbox, SandboxError


class ActionExecutor:
    def __init__(
        self,
        registry: ArtifactRegistry,
        sandbox: Sandbox,
        builtin_tools: dict[str, Any] | None = None,
        evaluator: Evaluator | None = None,
    ):
        self.registry = registry
        self.sandbox = sandbox
        self.builtin_tools = builtin_tools or {}
        self.evaluator = evaluator or Evaluator(RuleChecker(sandbox))
        # Track evaluation cards per artifact for activation checks
        self._evaluation_cards: dict[str, list[EvaluationCard]] = {}

    async def execute(self, action: ActionEnvelope) -> ActionResult:
        try:
            match action.action_type:
                case ActionType.SEND_MESSAGE:
                    return self._exec_send_message(action)
                case ActionType.CALL_TOOL:
                    return await self._exec_call_tool(action)
                case ActionType.CREATE_EXECUTABLE_TOOL_DRAFT:
                    return await self._exec_create_tool_draft(action)
                case ActionType.CREATE_PROMPT_SKILL_DRAFT:
                    return await self._exec_create_skill_draft(action)
                case ActionType.SUBMIT_REVIEW:
                    return self._exec_submit_review(action)
                case ActionType.ACTIVATE_ARTIFACT:
                    return await self._exec_activate(action)
                case ActionType.REJECT_ARTIFACT:
                    return await self._exec_reject(action)
                case ActionType.HANDOFF:
                    return self._exec_handoff(action)
                case ActionType.FINAL_ANSWER:
                    return self._exec_final_answer(action)
                case _:
                    return self._fail(action, f"Unknown action type: {action.action_type}")
        except Exception as e:
            return self._fail(action, str(e))

    def _ok(
        self,
        action: ActionEnvelope,
        output: Any = None,
        artifacts_changed: list[str] | None = None,
        should_continue: bool = True,
        suggested_next: str | None = None,
        evaluation_feedback: str | None = None,
    ) -> ActionResult:
        return ActionResult(
            action_id=action.action_id,
            agent_id=action.agent_id,
            action_type=action.action_type.value,
            success=True,
            output=output,
            artifacts_changed=artifacts_changed or [],
            should_continue_current_agent=should_continue,
            suggested_next_agent=suggested_next,
            evaluation_feedback=evaluation_feedback,
        )

    def _fail(self, action: ActionEnvelope, error: str) -> ActionResult:
        return ActionResult(
            action_id=action.action_id,
            agent_id=action.agent_id,
            action_type=action.action_type.value,
            success=False,
            error=error,
        )

    def _exec_send_message(self, action: ActionEnvelope) -> ActionResult:
        p: SendMessagePayload = action.payload
        return self._ok(action, output={"message": p.content})

    async def _exec_call_tool(self, action: ActionEnvelope) -> ActionResult:
        p: CallToolPayload = action.payload

        # Check builtin tools first
        if p.tool_name in self.builtin_tools:
            func = self.builtin_tools[p.tool_name]
            result = func(**p.arguments) if callable(func) else func
            return self._ok(action, output=result)

        # Check registry for active executable tools
        active_tools = await self.registry.list_active_tools()
        tool = next((t for t in active_tools if t.name == p.tool_name), None)
        if tool is None:
            return self._fail(action, f"Tool '{p.tool_name}' not found")

        # Execute in sandbox
        try:
            code = ""
            if tool.code_path:
                from pathlib import Path
                code_path = Path(tool.code_path)
                if code_path.exists():
                    code = code_path.read_text()
            if not code:
                return self._fail(action, f"No code found for tool '{p.tool_name}'")

            result = self.sandbox.execute(code, tool.entrypoint, p.arguments)
            return self._ok(action, output=result)
        except SandboxError as e:
            return self._fail(action, f"Sandbox error: {e}")

    async def _exec_create_tool_draft(self, action: ActionEnvelope) -> ActionResult:
        p: CreateExecutableToolDraftPayload = action.payload
        artifact_id = uuid.uuid4().hex[:10]
        artifact = ExecutableToolSpec(
            artifact_id=artifact_id,
            name=p.name,
            description=p.description,
            input_schema=p.input_schema,
            output_schema=p.output_schema,
            entrypoint=p.entrypoint,
            safety_mode=p.safety_mode,
            created_by=action.agent_id,
        )
        # Store code content for registry to save
        artifact._code_content = p.code
        await self.registry.register_draft(artifact)
        return self._ok(
            action,
            output={"artifact_id": artifact_id, "name": p.name},
            artifacts_changed=[artifact_id],
            suggested_next="reviewer",
        )

    async def _exec_create_skill_draft(self, action: ActionEnvelope) -> ActionResult:
        p: CreatePromptSkillDraftPayload = action.payload
        artifact_id = uuid.uuid4().hex[:10]
        artifact = PromptSkillSpec(
            artifact_id=artifact_id,
            name=p.name,
            description=p.description,
            trigger_guidance=p.trigger_guidance,
            prompt_fragment=p.prompt_fragment,
            allowed_tools=p.allowed_tools,
            created_by=action.agent_id,
        )
        await self.registry.register_draft(artifact)
        return self._ok(
            action,
            output={"artifact_id": artifact_id, "name": p.name},
            artifacts_changed=[artifact_id],
            suggested_next="reviewer",
        )

    def _exec_submit_review(self, action: ActionEnvelope) -> ActionResult:
        p: SubmitReviewPayload = action.payload
        card = EvaluationCard(
            artifact_id=p.artifact_id,
            evaluator_id=action.agent_id,
            scores=p.scores,
            approve=p.approve,
            rationale=p.rationale,
            required_revisions=p.required_revisions,
        )
        # Track evaluation cards for activation checks
        if p.artifact_id not in self._evaluation_cards:
            self._evaluation_cards[p.artifact_id] = []
        self._evaluation_cards[p.artifact_id].append(card)

        feedback = p.rationale
        if p.required_revisions:
            feedback += " Revisions needed: " + "; ".join(p.required_revisions)

        return self._ok(
            action,
            output=card.model_dump(),
            artifacts_changed=[p.artifact_id],
            should_continue=False,
            evaluation_feedback=feedback,
        )

    async def _exec_activate(self, action: ActionEnvelope) -> ActionResult:
        p: ActivateArtifactPayload = action.payload
        artifact = await self.registry.get_artifact(p.artifact_id)
        if artifact is None:
            return self._fail(action, f"Artifact {p.artifact_id} not found")

        # Run rule check
        rule_check = self.evaluator.run_rule_check(artifact)

        # Get collected evaluation cards
        reviews = self._evaluation_cards.get(p.artifact_id, [])

        # Check activation criteria
        can, reason = self.evaluator.can_activate(artifact, rule_check, reviews)
        if not can:
            return self._fail(action, f"Cannot activate: {reason}")

        await self.registry.activate(p.artifact_id)
        return self._ok(
            action,
            output={"artifact_id": p.artifact_id, "status": "active"},
            artifacts_changed=[p.artifact_id],
        )

    async def _exec_reject(self, action: ActionEnvelope) -> ActionResult:
        p: RejectArtifactPayload = action.payload
        artifact = await self.registry.reject(p.artifact_id)
        return self._ok(
            action,
            output={"artifact_id": p.artifact_id, "status": "rejected", "reason": p.reason},
            artifacts_changed=[p.artifact_id],
            should_continue=False,
        )

    def _exec_handoff(self, action: ActionEnvelope) -> ActionResult:
        p: HandoffPayload = action.payload
        return self._ok(
            action,
            output={"target_agent": p.target_agent, "reason": p.reason},
            should_continue=False,
            suggested_next=p.target_agent,
        )

    def _exec_final_answer(self, action: ActionEnvelope) -> ActionResult:
        p: FinalAnswerPayload = action.payload
        return self._ok(
            action,
            output={"content": p.content, "artifact_ids": p.artifact_ids},
            should_continue=False,
        )
