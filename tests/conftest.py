"""Pytest configuration and shared fixtures."""
import pytest
from pathlib import Path


@pytest.fixture
def tmp_registry(tmp_path):
    from eduagent.registry.artifact_registry import ArtifactRegistry
    return ArtifactRegistry(base_dir=tmp_path / "artifacts")
