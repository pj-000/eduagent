"""Tests for ArtifactRegistry."""
from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path

from eduagent.models.artifacts import (
    ArtifactKind,
    ArtifactStatus,
    ExecutableToolSpec,
    PromptSkillSpec,
)
from eduagent.registry.artifact_registry import ArtifactRegistry


@pytest.fixture
def tmp_registry(tmp_path):
    return ArtifactRegistry(base_dir=tmp_path / "artifacts")


@pytest.mark.asyncio
async def test_register_and_get(tmp_registry):
    tool = ExecutableToolSpec(
        artifact_id="t1",
        name="math_gen",
        description="Generates math",
        created_by="builder",
        entrypoint="run",
    )
    await tmp_registry.register_draft(tool)
    got = await tmp_registry.get_artifact("t1")
    assert got is not None
    assert got.name == "math_gen"
    assert got.status == ArtifactStatus.DRAFT


@pytest.mark.asyncio
async def test_activate(tmp_registry):
    tool = ExecutableToolSpec(
        artifact_id="t2",
        name="quiz",
        description="Quiz gen",
        created_by="builder",
    )
    await tmp_registry.register_draft(tool)
    activated = await tmp_registry.activate("t2")
    assert activated.status == ArtifactStatus.ACTIVE

    got = await tmp_registry.get_artifact("t2")
    assert got.status == ArtifactStatus.ACTIVE


@pytest.mark.asyncio
async def test_reject(tmp_registry):
    tool = ExecutableToolSpec(
        artifact_id="t3",
        name="bad_tool",
        description="Bad",
        created_by="builder",
    )
    await tmp_registry.register_draft(tool)
    rejected = await tmp_registry.reject("t3")
    assert rejected.status == ArtifactStatus.REJECTED


@pytest.mark.asyncio
async def test_record_revision(tmp_registry):
    tool = ExecutableToolSpec(
        artifact_id="t4",
        name="rev_tool",
        description="Revisable",
        created_by="builder",
    )
    await tmp_registry.register_draft(tool)
    assert tool.revision == 0

    tool.description = "Revised"
    revised = await tmp_registry.record_revision(tool)
    assert revised.revision == 1
    assert revised.status == ArtifactStatus.DRAFT

    count = await tmp_registry.get_revision_count("t4")
    assert count == 1


@pytest.mark.asyncio
async def test_list_active_tools(tmp_registry):
    t1 = ExecutableToolSpec(
        artifact_id="t5", name="active_tool", description="Active", created_by="b"
    )
    t2 = ExecutableToolSpec(
        artifact_id="t6", name="draft_tool", description="Draft", created_by="b"
    )
    await tmp_registry.register_draft(t1)
    await tmp_registry.register_draft(t2)
    await tmp_registry.activate("t5")

    active = await tmp_registry.list_active_tools()
    assert len(active) == 1
    assert active[0].artifact_id == "t5"


@pytest.mark.asyncio
async def test_list_active_skills(tmp_registry):
    s1 = PromptSkillSpec(
        artifact_id="s1",
        name="skill1",
        description="Skill",
        created_by="b",
        trigger_guidance="test",
        prompt_fragment="do something",
    )
    await tmp_registry.register_draft(s1)
    await tmp_registry.activate("s1")

    skills = await tmp_registry.list_active_skills()
    assert len(skills) == 1
    assert skills[0].name == "skill1"


@pytest.mark.asyncio
async def test_list_all(tmp_registry):
    t1 = ExecutableToolSpec(
        artifact_id="a1", name="t1", description="d", created_by="b"
    )
    s1 = PromptSkillSpec(
        artifact_id="a2", name="s1", description="d", created_by="b",
        trigger_guidance="t", prompt_fragment="p",
    )
    await tmp_registry.register_draft(t1)
    await tmp_registry.register_draft(s1)

    all_arts = await tmp_registry.list_all()
    assert len(all_arts) == 2


@pytest.mark.asyncio
async def test_get_nonexistent(tmp_registry):
    got = await tmp_registry.get_artifact("nonexistent")
    assert got is None


@pytest.mark.asyncio
async def test_atomic_write_integrity(tmp_registry):
    """Verify registry.json is valid JSON after writes."""
    tool = ExecutableToolSpec(
        artifact_id="t7", name="atomic", description="test", created_by="b"
    )
    await tmp_registry.register_draft(tool)

    # Read raw file and verify it's valid JSON
    raw = tmp_registry._registry_path.read_text()
    data = json.loads(raw)
    assert "artifacts" in data
    assert "t7" in data["artifacts"]


@pytest.mark.asyncio
async def test_tmp_cleanup(tmp_path):
    """Verify .tmp files are cleaned up on init."""
    art_dir = tmp_path / "artifacts"
    art_dir.mkdir()
    tmp_file = art_dir / "registry.tmp"
    tmp_file.write_text("garbage")

    registry = ArtifactRegistry(base_dir=art_dir)
    assert not tmp_file.exists()


@pytest.mark.asyncio
async def test_purge_drafts(tmp_registry):
    """purge_drafts removes all drafts, leaves active/rejected intact."""
    from eduagent.models.artifacts import ExecutableToolSpec, PromptSkillSpec

    # Create 3 drafts
    for i in range(3):
        t = ExecutableToolSpec(
            artifact_id=f"draft{i}", name=f"tool{i}", description="d", created_by="b"
        )
        await tmp_registry.register_draft(t)

    # Activate one, reject one
    await tmp_registry.activate("draft0")
    await tmp_registry.reject("draft1")

    removed = await tmp_registry.purge_drafts()
    assert removed == 1  # only draft2 is still draft

    all_arts = await tmp_registry.list_all()
    statuses = {a.artifact_id: a.status.value for a in all_arts}
    assert statuses["draft0"] == "active"
    assert statuses["draft1"] == "rejected"
    assert "draft2" not in statuses


@pytest.mark.asyncio
async def test_purge_drafts_cleans_files(tmp_path):
    """purge_drafts removes code files from disk."""
    from eduagent.models.artifacts import ExecutableToolSpec

    registry = ArtifactRegistry(base_dir=tmp_path / "artifacts")
    t = ExecutableToolSpec(
        artifact_id="todel", name="tool", description="d", created_by="b"
    )
    t._code_content = "def run(): return {}"
    await registry.register_draft(t)

    code_dir = tmp_path / "artifacts" / "tools" / "todel"
    assert code_dir.exists()

    await registry.purge_drafts()
    assert not code_dir.exists()
