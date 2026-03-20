"""Replay API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_replay_service
from ..schemas import ReplayResponse
from ...services.replay_service import ReplayService

router = APIRouter(prefix="/replay", tags=["场景回放"])


@router.post(
    "/{scenario}",
    response_model=ReplayResponse,
    summary="回放标准场景",
    description="""
使用预录脚本回放标准演示场景，**不消耗真实 LLM API**，适合演示和测试。

**可用场景：**

| 场景 ID | 名称 | 说明 |
|---|---|---|
| `scenario-a` | 工具复用 | Planner 直接调用内置工具完成任务 |
| `scenario-b` | 技能创建 | Builder 创建 PromptSkill → 审核通过 → 激活 → 使用 |
| `scenario-reject` | 草稿拒绝 | Builder 创建工具 → Reviewer 拒绝 → 修订 → 再次拒绝 |

返回 `run_id`，可通过 `/runs/{run_id}` 查看结果。
""",
)
async def replay_scenario(
    scenario: str,
    service: ReplayService = Depends(get_replay_service),
):
    try:
        run_id = await service.replay(scenario, cli_display=False)
        return ReplayResponse(run_id=run_id, scenario=scenario)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
