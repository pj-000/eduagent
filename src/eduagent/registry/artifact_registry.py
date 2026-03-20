"""Artifact registry with atomic writes."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from ..models.artifacts import (
    ArtifactKind,
    ArtifactStatus,
    CapabilityArtifact,
    ExecutableToolSpec,
    PromptSkillSpec,
)


class ArtifactRegistry:
    def __init__(self, base_dir: str | Path = "artifacts"):
        self._base_dir = Path(base_dir)
        self._registry_path = self._base_dir / "registry.json"
        self._lock = asyncio.Lock()
        self._ensure_dirs()
        self._cleanup_tmp()

    def _ensure_dirs(self):
        self._base_dir.mkdir(parents=True, exist_ok=True)
        (self._base_dir / "tools").mkdir(exist_ok=True)
        (self._base_dir / "skills").mkdir(exist_ok=True)
        if not self._registry_path.exists():
            self._atomic_write({"artifacts": {}})

    def _cleanup_tmp(self):
        tmp = self._registry_path.with_suffix(".tmp")
        if tmp.exists():
            tmp.unlink()

    def _read_registry(self) -> dict[str, Any]:
        return json.loads(self._registry_path.read_text())

    def _atomic_write(self, data: dict):
        tmp_path = self._registry_path.with_suffix(".tmp")
        content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        tmp_path.write_text(content)
        json.loads(tmp_path.read_text())  # validate
        os.replace(tmp_path, self._registry_path)

    def _deserialize(self, data: dict) -> CapabilityArtifact:
        kind = data.get("kind")
        if kind == ArtifactKind.EXECUTABLE_TOOL:
            return ExecutableToolSpec.model_validate(data)
        elif kind == ArtifactKind.PROMPT_SKILL:
            return PromptSkillSpec.model_validate(data)
        return CapabilityArtifact.model_validate(data)

    async def register_draft(self, artifact: CapabilityArtifact) -> CapabilityArtifact:
        artifact.status = ArtifactStatus.DRAFT
        # Save code/skill content FIRST so code_path is set before writing registry
        await self._save_revision(artifact)
        async with self._lock:
            data = self._read_registry()
            data["artifacts"][artifact.artifact_id] = json.loads(
                artifact.model_dump_json()
            )
            self._atomic_write(data)
        return artifact

    async def _save_revision(self, artifact: CapabilityArtifact):
        if isinstance(artifact, ExecutableToolSpec):
            rev_dir = self._base_dir / "tools" / artifact.artifact_id
            rev_dir.mkdir(parents=True, exist_ok=True)
            rev_path = rev_dir / f"rev_{artifact.revision}.py"
            # Read code from the artifact's code_path or store empty
            if hasattr(artifact, "_code_content"):
                rev_path.write_text(artifact._code_content)
            elif artifact.code_path and Path(artifact.code_path).exists():
                rev_path.write_text(Path(artifact.code_path).read_text())
            else:
                rev_path.write_text("# placeholder\n")
            artifact.code_path = str(rev_path)
        elif isinstance(artifact, PromptSkillSpec):
            rev_dir = self._base_dir / "skills" / artifact.artifact_id
            rev_dir.mkdir(parents=True, exist_ok=True)
            rev_path = rev_dir / f"rev_{artifact.revision}.json"
            rev_path.write_text(artifact.model_dump_json(indent=2))

    async def get_artifact(self, artifact_id: str) -> CapabilityArtifact | None:
        data = self._read_registry()
        entry = data["artifacts"].get(artifact_id)
        if entry is None:
            return None
        return self._deserialize(entry)

    async def activate(self, artifact_id: str) -> CapabilityArtifact:
        async with self._lock:
            data = self._read_registry()
            entry = data["artifacts"].get(artifact_id)
            if entry is None:
                raise ValueError(f"Artifact {artifact_id} not found")
            entry["status"] = ArtifactStatus.ACTIVE.value
            self._atomic_write(data)
        return self._deserialize(entry)

    async def reject(self, artifact_id: str) -> CapabilityArtifact:
        async with self._lock:
            data = self._read_registry()
            entry = data["artifacts"].get(artifact_id)
            if entry is None:
                raise ValueError(f"Artifact {artifact_id} not found")
            entry["status"] = ArtifactStatus.REJECTED.value
            self._atomic_write(data)
        return self._deserialize(entry)

    async def record_revision(
        self, artifact: CapabilityArtifact
    ) -> CapabilityArtifact:
        artifact.revision += 1
        artifact.status = ArtifactStatus.DRAFT
        async with self._lock:
            data = self._read_registry()
            data["artifacts"][artifact.artifact_id] = json.loads(
                artifact.model_dump_json()
            )
            self._atomic_write(data)
        await self._save_revision(artifact)
        return artifact

    async def get_revision_count(self, artifact_id: str) -> int:
        artifact = await self.get_artifact(artifact_id)
        if artifact is None:
            return 0
        return artifact.revision

    async def list_active_tools(self) -> list[ExecutableToolSpec]:
        data = self._read_registry()
        results = []
        for entry in data["artifacts"].values():
            if (
                entry.get("kind") == ArtifactKind.EXECUTABLE_TOOL
                and entry.get("status") == ArtifactStatus.ACTIVE
            ):
                results.append(ExecutableToolSpec.model_validate(entry))
        return results

    async def list_active_skills(self) -> list[PromptSkillSpec]:
        data = self._read_registry()
        results = []
        for entry in data["artifacts"].values():
            if (
                entry.get("kind") == ArtifactKind.PROMPT_SKILL
                and entry.get("status") == ArtifactStatus.ACTIVE
            ):
                results.append(PromptSkillSpec.model_validate(entry))
        return results

    async def list_all(self) -> list[CapabilityArtifact]:
        data = self._read_registry()
        return [self._deserialize(e) for e in data["artifacts"].values()]

    async def purge_drafts(self) -> int:
        """Remove all draft artifacts from registry and disk. Returns count removed."""
        async with self._lock:
            data = self._read_registry()
            to_remove = [
                aid for aid, entry in data["artifacts"].items()
                if entry.get("status") == ArtifactStatus.DRAFT.value
            ]
            for aid in to_remove:
                del data["artifacts"][aid]
            self._atomic_write(data)

        # Clean up files
        import shutil
        for aid in to_remove:
            for subdir in ("tools", "skills"):
                p = self._base_dir / subdir / aid
                if p.exists():
                    shutil.rmtree(p)

        return len(to_remove)
