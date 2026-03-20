"""Runs API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from ..deps import get_run_service
from ..schemas import CreateRunRequest, CreateRunResponse, RunStatusResponse
from ...services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["任务管理"])


@router.post(
    "",
    response_model=CreateRunResponse,
    summary="提交新任务",
    description="""
提交一个教育任务，系统自动启动多 Agent 协作流程。

**示例任务：**
- `帮我生成 10 道适合三年级学生的加减法练习题`
- `帮我创建一个生成英语填空题的工具`
- `帮我把这段课文改写成适合小学生理解的版本`

任务提交后立即返回 `run_id`，可通过 `/runs/{run_id}` 查询状态，
或通过 `/runs/{run_id}/events` 订阅实时事件流。
""",
)
async def create_run(
    req: CreateRunRequest,
    service: RunService = Depends(get_run_service),
):
    run_id = await service.create_run(task=req.task, cli_display=False)
    await service.start_run(run_id)
    return CreateRunResponse(run_id=run_id)


@router.get(
    "/{run_id}",
    response_model=RunStatusResponse,
    summary="查询任务状态",
    description="""
查询指定 Run 的当前状态。

**状态说明：**
- `pending`：等待执行
- `running`：正在执行
- `completed`：已完成，可查看 `final_answer`
- `failed`：执行失败，可查看 `error`
""",
)
async def get_run(
    run_id: str,
    service: RunService = Depends(get_run_service),
):
    info = service.get_run(run_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} 不存在")
    return RunStatusResponse(**info)


@router.get(
    "/{run_id}/events",
    summary="订阅实时事件流（SSE）",
    description="""
通过 Server-Sent Events 实时订阅 Run 的执行过程。

**事件类型包括：**
- `run_started` / `run_completed` / `run_failed`
- `agent_turn_started` / `agent_turn_ended`
- `action_created` / `action_result`
- `artifact_created` / `artifact_updated`
- `evaluation_completed`
- `agent_handoff`
- `skill_injected`

每个事件为 JSON 格式，包含 `event_type`、`agent_id`、`round_number`、`payload` 等字段。
""",
)
async def stream_events(
    run_id: str,
    service: RunService = Depends(get_run_service),
):
    subscriber = service.subscribe_events(run_id)
    if subscriber is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} 不存在或已结束")

    async def event_generator():
        async for event in subscriber:
            yield {
                "event": event.event_type.value,
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(event_generator())
