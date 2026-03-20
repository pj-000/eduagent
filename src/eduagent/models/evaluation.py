"""Evaluation card model."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluationCard(BaseModel):
    artifact_id: str
    evaluator_id: str
    scores: dict[str, float] = Field(default_factory=dict)
    approve: bool = False
    rationale: str = ""
    required_revisions: list[str] = Field(default_factory=list)
