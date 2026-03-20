"""Tests for FastAPI endpoints."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from eduagent.api.app import app
from eduagent.api.deps import get_artifact_service, get_registry, get_replay_service, get_run_service
from eduagent.providers.fake import FakeProvider
from eduagent.registry.artifact_registry import ArtifactRegistry
from eduagent.services.artifact_service import ArtifactService
from eduagent.services.replay_service import ReplayService
from eduagent.services.run_service import RunService


@pytest.fixture
def tmp_registry(tmp_path):
    return ArtifactRegistry(base_dir=tmp_path / "artifacts")


@pytest.fixture
def tmp_run_service(tmp_registry, tmp_path):
    provider = FakeProvider(responses=[
        '{"action_type":"final_answer","payload":{"content":"test done"}}',
    ])
    return RunService(
        registry=tmp_registry,
        providers={"default": provider},
        runs_dir=str(tmp_path / "runs"),
        max_rounds=5,
    )


@pytest.fixture
def tmp_artifact_service(tmp_registry):
    return ArtifactService(registry=tmp_registry)


@pytest.fixture
def tmp_replay_service(tmp_registry, tmp_path):
    return ReplayService(registry=tmp_registry, runs_dir=str(tmp_path / "runs"))


@pytest.fixture
def test_app(tmp_run_service, tmp_artifact_service, tmp_replay_service, tmp_registry):
    app.dependency_overrides[get_run_service] = lambda: tmp_run_service
    app.dependency_overrides[get_artifact_service] = lambda: tmp_artifact_service
    app.dependency_overrides[get_replay_service] = lambda: tmp_replay_service
    app.dependency_overrides[get_registry] = lambda: tmp_registry
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_run(client):
    resp = await client.post("/runs", json={"task": "test task"})
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data


@pytest.mark.asyncio
async def test_get_run_not_found(client):
    resp = await client.get("/runs/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_after_create(client):
    resp = await client.post("/runs", json={"task": "test task"})
    run_id = resp.json()["run_id"]

    # Give the background task a moment
    import asyncio
    await asyncio.sleep(0.5)

    resp = await client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["task"] == "test task"


@pytest.mark.asyncio
async def test_list_artifacts_empty(client):
    resp = await client.get("/artifacts")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_artifact_not_found(client):
    resp = await client.get("/artifacts/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_replay_unknown_scenario(client):
    resp = await client.post("/replay/unknown")
    assert resp.status_code == 404
