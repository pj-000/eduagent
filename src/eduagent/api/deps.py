"""Dependency injection for FastAPI."""
from __future__ import annotations

from functools import lru_cache

from ..providers.dashscope import DashScopeProvider
from ..registry.artifact_registry import ArtifactRegistry
from ..services.artifact_service import ArtifactService
from ..services.replay_service import ReplayService
from ..services.run_service import RunService


@lru_cache()
def get_registry() -> ArtifactRegistry:
    return ArtifactRegistry(base_dir="artifacts")


@lru_cache()
def get_run_service() -> RunService:
    provider = DashScopeProvider()
    return RunService(
        registry=get_registry(),
        providers={"default": provider},
        runs_dir="runs",
    )


@lru_cache()
def get_artifact_service() -> ArtifactService:
    return ArtifactService(registry=get_registry())


@lru_cache()
def get_replay_service() -> ReplayService:
    return ReplayService(registry=get_registry(), runs_dir="runs")
