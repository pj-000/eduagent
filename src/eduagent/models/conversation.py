"""Conversation state models."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .actions import ActionEnvelope
from .results import ActionResult


class Message(BaseModel):
    role: str
    content: str
    agent_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ConversationState(BaseModel):
    run_id: str
    task: str
    shared_messages: list[Message] = Field(default_factory=list)
    action_history: list[ActionEnvelope] = Field(default_factory=list)
    result_history: list[ActionResult] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    active_artifact_ids: list[str] = Field(default_factory=list)
    pending_artifact_ids: list[str] = Field(default_factory=list)
    last_action_result: ActionResult | None = None
    round_number: int = 0
    current_agent_id: str | None = None
    terminated: bool = False
    final_answer: str | None = None
