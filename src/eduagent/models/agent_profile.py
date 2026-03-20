"""Agent profile models."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    PLANNER = "planner"
    BUILDER = "builder"
    REVIEWER = "reviewer"
    USER_SIMULATOR = "user_simulator"


class AgentProfile(BaseModel):
    agent_id: str
    role: AgentRole
    display_name: str
    model_name: str = "qwen3.5-plus"
    max_actions_per_turn: int = 5
    system_prompt: str = ""
    allowed_action_types: list[str] = Field(default_factory=list)
