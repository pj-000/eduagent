"""Unified event schema for CLI, API SSE, and structured logging."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .agent_profile import AgentRole


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    AGENT_TURN_STARTED = "agent_turn_started"
    MESSAGE_CREATED = "message_created"
    ACTION_CREATED = "action_created"
    ACTION_RESULT = "action_result"
    SKILL_INJECTED = "skill_injected"
    ARTIFACT_CREATED = "artifact_created"
    ARTIFACT_UPDATED = "artifact_updated"
    EVALUATION_COMPLETED = "evaluation_completed"
    AGENT_TURN_ENDED = "agent_turn_ended"
    AGENT_HANDOFF = "agent_handoff"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class RuntimeEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])
    sequence_number: int = 0
    event_type: EventType
    run_id: str
    round_number: int = 0
    agent_id: str | None = None
    agent_role: AgentRole | None = None
    step_in_turn: int | None = None
    related_action_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    payload: dict[str, Any] = Field(default_factory=dict)
