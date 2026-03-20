"""Artifacts API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_artifact_service
from ..schemas import ArtifactDetail, ArtifactSummary
from ...services.artifact_service import ArtifactService

router = APIRouter(prefix="/artifacts", tags=["能力制品"])


@router.get(
    "",
    response_model=list[ArtifactSummary],
    summary="查询能力制品列表",
    description="""
查询系统中所有能力制品（工具和技能）。

**制品类型：**
- `executable_tool`：可执行 Python 工具，在沙箱中运行
- `prompt_skill`：提示词技能，注入 Agent 上下文

**制品状态：**
- `draft`：草稿，尚未通过审核
- `active`：已激活，可被 Planner 调用
- `rejected`：已拒绝

**过滤示例：**
- `?status=active` 只看已激活的制品
- `?status=draft` 只看草稿
""",
)
async def list_artifacts(
    status: str | None = Query(default=None, description="按状态过滤：draft / active / rejected"),
    service: ArtifactService = Depends(get_artifact_service),
):
    items = await service.list_artifacts(status=status)
    return [ArtifactSummary(**item) for item in items]


@router.get(
    "/{artifact_id}",
    response_model=ArtifactDetail,
    summary="查询制品详情",
    description="""
查询指定制品的完整信息，包括代码内容（ExecutableTool）或提示词片段（PromptSkill）。
""",
)
async def get_artifact(
    artifact_id: str,
    service: ArtifactService = Depends(get_artifact_service),
):
    detail = await service.get_artifact(artifact_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"制品 {artifact_id} 不存在")
    return ArtifactDetail(**detail)
