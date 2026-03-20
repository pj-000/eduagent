"""API request/response schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    task: str


class CreateRunResponse(BaseModel):
    run_id: str


class RunStatusResponse(BaseModel):
    run_id: str
    task: str
    status: str
    created_at: str
    completed_at: str | None = None
    final_answer: str | None = None
    round_number: int = 0
    current_agent: str | None = None
    error: str | None = None


class ArtifactSummary(BaseModel):
    artifact_id: str
    kind: str
    name: str
    description: str
    status: str
    revision: int
    created_by: str
    created_at: str


class ArtifactDetail(BaseModel):
    artifact_id: str
    kind: str
    name: str
    description: str
    status: str
    revision: int
    created_by: str
    code: str | None = None
    prompt_fragment: str | None = None
    trigger_guidance: str | None = None

    model_config = {"extra": "allow"}


class ReplayRequest(BaseModel):
    pass


class ReplayResponse(BaseModel):
    run_id: str
    scenario: str
