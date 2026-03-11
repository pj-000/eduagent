"""Reusable runner for the EduAgent workflow pipeline."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def get_default_explore_hints() -> dict[str, str]:
    from search_edu import DEFAULT_EXPLORE_HINTS

    return DEFAULT_EXPLORE_HINTS


def _load_workflow_dependencies():
    from execute_workflow import build_default_inputs, run_workflow_execution
    from framework_research import build_llm, build_llm_config, run_framework_research
    from generate_workflow import run_workflow_generation
    from search_edu import run_search
    from task_state import EduAgentTaskState

    return {
        "EduAgentTaskState": EduAgentTaskState,
        "build_default_inputs": build_default_inputs,
        "build_llm": build_llm,
        "build_llm_config": build_llm_config,
        "run_framework_research": run_framework_research,
        "run_search": run_search,
        "run_workflow_execution": run_workflow_execution,
        "run_workflow_generation": run_workflow_generation,
    }


def build_search_hint(task: str, focus: str, hint: str | None = None) -> str:
    """Convert a task into a stable search prompt."""

    if hint:
        return hint
    if focus == "free":
        return task
    default_hints = get_default_explore_hints()
    focus_prefix = default_hints.get(focus, default_hints["all"])
    return f"{focus_prefix}\n\n当前用户任务：{task}"


def run_workflow_pipeline(
    *,
    task: str,
    focus: str = "all",
    themes: list[str] | None = None,
    search_mode: str = "research",
    hint: str | None = None,
    feature: int | None = None,
    mode: str = "auto",
    skip_search: bool = False,
    inputs: dict[str, Any] | None = None,
    max_steps: int = 5,
    no_save_state: bool = False,
    skip_framework_research: bool = False,
) -> dict[str, Any]:
    """Execute the four-stage workflow pipeline and return a normalized result."""

    deps = _load_workflow_dependencies()
    search_hint = build_search_hint(task, focus, hint)
    state = deps["EduAgentTaskState"](
        task=task,
        focus=focus,
        explore_hint=search_hint,
        workflow_mode=mode,
        feature_index=feature,
        max_steps=max_steps,
    )

    def persist_state() -> None:
        if not no_save_state:
            state.save()

    persist_state()
    llm = deps["build_llm"](deps["build_llm_config"]())

    try:
        if skip_framework_research:
            state.mark_stage_skipped("framework_research", "skipped_by_user")
            persist_state()
        else:
            state.mark_stage_running("framework_research", detail="fetching_official_evoagentx_docs")
            persist_state()
            framework_bundle = deps["run_framework_research"](task=task, save=True, verbose=True, llm=llm)
            state.attach_artifacts(
                framework_notes=framework_bundle["notes"],
                framework_sources=framework_bundle["sources"],
                framework_json_path=str(framework_bundle["json_path"]) if framework_bundle["json_path"] else None,
                framework_md_path=str(framework_bundle["md_path"]) if framework_bundle["md_path"] else None,
            )
            state.mark_stage_completed("framework_research", detail="official_notes_saved")
            persist_state()

        if skip_search:
            state.mark_stage_skipped("search", "skipped_by_user")
            persist_state()
        else:
            state.mark_stage_running("search", detail="collecting_education_insights")
            persist_state()
            search_bundle = deps["run_search"](
                search_hint,
                focus=focus,
                custom_themes=themes or [],
                search_mode=search_mode,
                save=True,
                verbose=True,
            )
            state.attach_artifacts(
                search_report=search_bundle["result"],
                search_json_path=str(search_bundle["json_path"]) if search_bundle["json_path"] else None,
                search_md_path=str(search_bundle["md_path"]) if search_bundle["md_path"] else None,
            )
            state.mark_stage_completed("search", detail="artifacts_saved")
            persist_state()

        state.mark_stage_running("workflow_generation", detail="building_workflow_graph")
        persist_state()
        workflow_bundle = deps["run_workflow_generation"](
            goal=task,
            input_path=state.search_md_path,
            feature=feature,
            mode=mode,
            retry=3,
            save=True,
            verbose=True,
            llm_config=llm.config,
        )
        state.attach_artifacts(
            workflow_goal=workflow_bundle["goal"],
            workflow_json_path=str(workflow_bundle["json_path"]) if workflow_bundle["json_path"] else None,
            workflow_md_path=str(workflow_bundle["md_path"]) if workflow_bundle["md_path"] else None,
        )
        state.mark_stage_completed("workflow_generation", detail="workflow_saved")
        persist_state()

        state.mark_stage_running("workflow_execution", detail="executing_generated_workflow")
        persist_state()

        execution_inputs = dict(inputs or {})
        if not execution_inputs:
            execution_inputs = deps["build_default_inputs"](workflow_bundle["workflow_graph"], task)
        state.execution_inputs = execution_inputs
        persist_state()

        execution_bundle = deps["run_workflow_execution"](
            workflow_path=state.workflow_json_path,
            inputs=execution_inputs,
            max_steps=max_steps,
            save=True,
            verbose=True,
        )
        state.attach_artifacts(
            execution_output=execution_bundle["output"],
            result_path=str(execution_bundle["result_path"]) if execution_bundle["result_path"] else None,
        )
        state.mark_stage_completed("workflow_execution", detail="result_saved")
        persist_state()
    except Exception as exc:
        failing_stage = state.current_stage if state.current_stage in state.stages else "workflow_execution"
        state.mark_stage_failed(failing_stage, str(exc))
        persist_state()
        return {
            "status": "error",
            "route": "workflow",
            "error_type": "runtime_error",
            "message": str(exc),
            "failing_stage": failing_stage,
            "artifacts": {
                "framework_md_path": state.framework_md_path,
                "search_md_path": state.search_md_path,
                "workflow_json_path": state.workflow_json_path,
                "workflow_md_path": state.workflow_md_path,
                "result_path": state.result_path,
                "state_path": state.state_path,
            },
        }

    return {
        "status": "success",
        "route": "workflow",
        "task": task,
        "artifacts": {
            "framework_md_path": state.framework_md_path,
            "search_md_path": state.search_md_path,
            "workflow_json_path": state.workflow_json_path,
            "workflow_md_path": state.workflow_md_path,
            "result_path": state.result_path,
            "state_path": state.state_path,
        },
        "execution_inputs": state.execution_inputs,
        "execution_output": state.execution_output,
    }
