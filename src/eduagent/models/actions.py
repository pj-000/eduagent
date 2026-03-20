"""Action envelope and payload models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .artifacts import ArtifactKind, SafetyMode


class ActionType(str, Enum):
    SEND_MESSAGE = "send_message"
    CALL_TOOL = "call_tool"
    CREATE_EXECUTABLE_TOOL_DRAFT = "create_executable_tool_draft"
    CREATE_PROMPT_SKILL_DRAFT = "create_prompt_skill_draft"
    SUBMIT_REVIEW = "submit_review"
    ACTIVATE_ARTIFACT = "activate_artifact"
    REJECT_ARTIFACT = "reject_artifact"
    HANDOFF = "handoff"
    FINAL_ANSWER = "final_answer"


class SendMessagePayload(BaseModel):
    content: str
    target_agent: str | None = None


class CallToolPayload(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class CreateExecutableToolDraftPayload(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    entrypoint: str = "run"
    code: str = ""
    safety_mode: SafetyMode = SafetyMode.RESTRICTED


class CreatePromptSkillDraftPayload(BaseModel):
    name: str
    description: str
    trigger_guidance: str = ""
    prompt_fragment: str = ""
    allowed_tools: list[str] = Field(default_factory=list)


class SubmitReviewPayload(BaseModel):
    artifact_id: str
    approve: bool
    scores: dict[str, float] = Field(default_factory=dict)
    rationale: str = ""
    required_revisions: list[str] = Field(default_factory=list)


class ActivateArtifactPayload(BaseModel):
    artifact_id: str


class RejectArtifactPayload(BaseModel):
    artifact_id: str
    reason: str = ""


class HandoffPayload(BaseModel):
    target_agent: str
    reason: str = ""


class FinalAnswerPayload(BaseModel):
    content: str
    artifact_ids: list[str] = Field(default_factory=list)


class ActionEnvelope(BaseModel):
    action_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])
    action_type: ActionType
    agent_id: str
    payload: (
        SendMessagePayload
        | CallToolPayload
        | CreateExecutableToolDraftPayload
        | CreatePromptSkillDraftPayload
        | SubmitReviewPayload
        | ActivateArtifactPayload
        | RejectArtifactPayload
        | HandoffPayload
        | FinalAnswerPayload
    )
    timestamp: datetime = Field(default_factory=datetime.now)
