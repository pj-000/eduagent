#!/usr/bin/env python3
"""统一任务状态对象，用于串联搜索、工作流生成和执行阶段。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STAGE_NAMES = (
    "framework_research",
    "search",
    "workflow_generation",
    "workflow_execution",
)


def _now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class StageState:
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    detail: str | None = None
    error: str | None = None


@dataclass
class StateEvent:
    timestamp: str
    stage: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class EduAgentTaskState:
    task: str
    focus: str = "all"
    explore_hint: str | None = None
    workflow_mode: str = "auto"
    feature_index: int | None = None
    max_steps: int = 5
    task_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    created_at: str = field(default_factory=_now_iso)
    current_stage: str = "initialized"
    status: str = "pending"
    state_path: str | None = None
    framework_notes: str | None = None
    framework_sources: list[dict[str, Any]] = field(default_factory=list)
    search_report: str | None = None
    workflow_goal: str | None = None
    execution_output: str | None = None
    execution_inputs: dict[str, Any] = field(default_factory=dict)
    framework_json_path: str | None = None
    framework_md_path: str | None = None
    search_json_path: str | None = None
    search_md_path: str | None = None
    workflow_json_path: str | None = None
    workflow_md_path: str | None = None
    result_path: str | None = None
    stages: dict[str, StageState] = field(
        default_factory=lambda: {stage_name: StageState() for stage_name in STAGE_NAMES}
    )
    events: list[StateEvent] = field(default_factory=list)

    def record_event(self, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.events.append(
            StateEvent(
                timestamp=_now_iso(),
                stage=stage,
                message=message,
                payload=payload or {},
            )
        )

    def mark_stage_running(self, stage: str, detail: str | None = None) -> None:
        stage_state = self.stages[stage]
        stage_state.status = "running"
        stage_state.started_at = _now_iso()
        stage_state.detail = detail
        stage_state.error = None
        self.current_stage = stage
        self.status = "running"
        self.record_event(stage, "stage_started", {"detail": detail} if detail else {})

    def mark_stage_completed(self, stage: str, detail: str | None = None) -> None:
        stage_state = self.stages[stage]
        if stage_state.started_at is None:
            stage_state.started_at = _now_iso()
        stage_state.status = "completed"
        stage_state.completed_at = _now_iso()
        stage_state.detail = detail
        stage_state.error = None
        self.current_stage = stage
        if all(item.status == "completed" for item in self.stages.values()):
            self.status = "completed"
        self.record_event(stage, "stage_completed", {"detail": detail} if detail else {})

    def mark_stage_skipped(self, stage: str, detail: str | None = None) -> None:
        stage_state = self.stages[stage]
        stage_state.status = "skipped"
        stage_state.started_at = _now_iso()
        stage_state.completed_at = _now_iso()
        stage_state.detail = detail
        stage_state.error = None
        self.current_stage = stage
        self.record_event(stage, "stage_skipped", {"detail": detail} if detail else {})

    def mark_stage_failed(self, stage: str, error: str) -> None:
        stage_state = self.stages[stage]
        if stage_state.started_at is None:
            stage_state.started_at = _now_iso()
        stage_state.status = "failed"
        stage_state.completed_at = _now_iso()
        stage_state.error = error
        self.current_stage = stage
        self.status = "failed"
        self.record_event(stage, "stage_failed", {"error": error})

    def attach_artifacts(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self) -> Path:
        save_dir = PROJECT_ROOT / "data" / "task_runs"
        save_dir.mkdir(parents=True, exist_ok=True)
        if self.state_path:
            path = Path(self.state_path)
        else:
            path = save_dir / f"task_state_{self.task_id}.json"
            self.state_path = str(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path
