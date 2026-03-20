"""BaseAgent: pure decision component."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from ..models.actions import ActionEnvelope, ActionType
from ..models.agent_profile import AgentProfile
from ..models.artifacts import CapabilityArtifact, PromptSkillSpec
from ..models.conversation import ConversationState
from ..models.results import ActionResult
from ..providers.base import ModelProvider, ProviderResponse

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    """Read-only context provided to agent by AgentRunner."""
    state: ConversationState
    available_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    recent_results: list[ActionResult] = Field(default_factory=list)
    injected_skill: dict[str, Any] | None = None
    active_tools: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


class BaseAgent(ABC):
    def __init__(self, profile: AgentProfile, provider: ModelProvider):
        self.profile = profile
        self.provider = provider

    @abstractmethod
    async def decide_next_action(self, context: AgentContext) -> ActionEnvelope:
        ...

    @abstractmethod
    def build_prompt(self, context: AgentContext) -> list[dict[str, str]]:
        ...

    async def _call_llm(self, context: AgentContext) -> str:
        messages = self.build_prompt(context)
        resp = await self.provider.chat(
            messages=messages,
            model=self.profile.model_name,
            response_format={"type": "json_object"},
        )
        return resp.content

    def _parse_action(self, raw: str, context: AgentContext) -> ActionEnvelope:
        """Parse LLM JSON output into ActionEnvelope."""
        data = json.loads(raw)
        action_type = data.get("action_type", "")
        payload = data.get("payload", {})
        return ActionEnvelope(
            action_type=ActionType(action_type),
            agent_id=self.profile.agent_id,
            payload=self._build_payload(action_type, payload),
        )

    def _build_payload(self, action_type: str, data: dict) -> Any:
        from ..models.actions import (
            SendMessagePayload,
            CallToolPayload,
            CreateExecutableToolDraftPayload,
            CreatePromptSkillDraftPayload,
            SubmitReviewPayload,
            ActivateArtifactPayload,
            RejectArtifactPayload,
            HandoffPayload,
            FinalAnswerPayload,
        )
        mapping = {
            "send_message": SendMessagePayload,
            "call_tool": CallToolPayload,
            "create_executable_tool_draft": CreateExecutableToolDraftPayload,
            "create_prompt_skill_draft": CreatePromptSkillDraftPayload,
            "submit_review": SubmitReviewPayload,
            "activate_artifact": ActivateArtifactPayload,
            "reject_artifact": RejectArtifactPayload,
            "handoff": HandoffPayload,
            "final_answer": FinalAnswerPayload,
        }
        cls = mapping.get(action_type)
        if cls is None:
            raise ValueError(f"Unknown action_type: {action_type}")
        return cls.model_validate(data)

    def _format_state_summary(self, context: AgentContext) -> str:
        s = context.state
        parts = [f"Task: {s.task}", f"Round: {s.round_number}"]
        if s.last_action_result:
            r = s.last_action_result
            parts.append(f"Last result: {r.action_type} {'ok' if r.success else 'FAIL'}")
            if r.error:
                parts.append(f"Error: {r.error}")
            if r.evaluation_feedback:
                parts.append(f"Feedback: {r.evaluation_feedback}")
        if context.injected_skill:
            parts.append(f"Injected skill: {context.injected_skill.get('name', '')}")
        if s.pending_artifact_ids:
            parts.append(f"Pending artifacts: {s.pending_artifact_ids}")
        if s.active_artifact_ids:
            parts.append(f"Active artifacts: {s.active_artifact_ids}")
        return "\n".join(parts)

    def _format_messages(self, context: AgentContext) -> str:
        msgs = context.state.shared_messages[-10:]
        if not msgs:
            return "No messages yet."
        lines = []
        for m in msgs:
            prefix = m.agent_id or m.role
            lines.append(f"[{prefix}] {m.content}")
        return "\n".join(lines)

    def _format_available_tools(self, context: AgentContext) -> str:
        tools = context.active_tools
        if not tools:
            return "No tools available."
        lines = []
        for t in tools:
            sig = t.get("signature", "")
            desc = t.get("description", "")
            if sig:
                lines.append(f"- {t['name']}{' — ' + desc if desc else ''}\n  signature: {sig}")
            else:
                lines.append(f"- {t['name']}: {desc}")
        return "\n".join(lines)
