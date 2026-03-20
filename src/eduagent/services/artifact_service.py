"""ArtifactService: artifact listing, details, revisions."""
from __future__ import annotations

from typing import Any

from ..models.artifacts import CapabilityArtifact, ExecutableToolSpec, PromptSkillSpec
from ..registry.artifact_registry import ArtifactRegistry


class ArtifactService:
    def __init__(self, registry: ArtifactRegistry):
        self._registry = registry

    async def list_artifacts(self, status: str | None = None) -> list[dict[str, Any]]:
        all_artifacts = await self._registry.list_all()
        if status:
            all_artifacts = [a for a in all_artifacts if a.status.value == status]
        return [self._summarize(a) for a in all_artifacts]

    async def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        artifact = await self._registry.get_artifact(artifact_id)
        if artifact is None:
            return None
        return self._detail(artifact)

    def _summarize(self, artifact: CapabilityArtifact) -> dict[str, Any]:
        return {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind.value,
            "name": artifact.name,
            "description": artifact.description,
            "status": artifact.status.value,
            "revision": artifact.revision,
            "created_by": artifact.created_by,
            "created_at": artifact.created_at.isoformat(),
        }

    def _detail(self, artifact: CapabilityArtifact) -> dict[str, Any]:
        data = artifact.model_dump()
        data["kind"] = artifact.kind.value
        data["status"] = artifact.status.value
        # Load code for executable tools
        if isinstance(artifact, ExecutableToolSpec) and artifact.code_path:
            from pathlib import Path
            p = Path(artifact.code_path)
            if p.exists():
                data["code"] = p.read_text()
        return data
