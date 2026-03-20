"""Action result models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ResultStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"


class ActionResult(BaseModel):
    action_id: str
    agent_id: str
    action_type: str
    success: bool
    output: Any = None
    error: str | None = None
    artifacts_changed: list[str] = Field(default_factory=list)
    evaluation_feedback: str | None = None
    scheduler_hint: str | None = None
    should_continue_current_agent: bool = True
    suggested_next_agent: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
