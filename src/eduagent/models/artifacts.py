"""Capability artifact models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ArtifactKind(str, Enum):
    EXECUTABLE_TOOL = "executable_tool"
    PROMPT_SKILL = "prompt_skill"


class ArtifactStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    REJECTED = "rejected"


class SafetyMode(str, Enum):
    SAFE_READ = "safe_read"
    RESTRICTED = "restricted"


class CapabilityArtifact(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    name: str
    description: str
    status: ArtifactStatus = ArtifactStatus.DRAFT
    version: str = "1.0"
    revision: int = 0
    created_by: str
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated_at: datetime = Field(default_factory=datetime.now)


class ExecutableToolSpec(CapabilityArtifact):
    kind: ArtifactKind = ArtifactKind.EXECUTABLE_TOOL
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    entrypoint: str = "run"
    code_path: str = ""
    safety_mode: SafetyMode = SafetyMode.RESTRICTED


class PromptSkillSpec(CapabilityArtifact):
    kind: ArtifactKind = ArtifactKind.PROMPT_SKILL
    trigger_guidance: str = ""
    prompt_fragment: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
