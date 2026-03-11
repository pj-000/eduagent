#!/usr/bin/env python3
"""EduAgent 统一入口：搜索、生成工作流、执行工作流。"""

from __future__ import annotations

import argparse
import json
import sys

from execute_workflow import build_default_inputs, run_workflow_execution
from framework_research import build_llm, build_llm_config, run_framework_research
from generate_workflow import run_workflow_generation
from search_edu import DEFAULT_EXPLORE_HINTS, run_search
from task_state import EduAgentTaskState


def build_search_hint(task: str, focus: str, hint: str | None = None) -> str:
    """将自然语言任务转换为更稳定的搜索提示。"""
    if hint:
        return hint
    if focus == "free":
        return task
    focus_prefix = DEFAULT_EXPLORE_HINTS.get(focus, DEFAULT_EXPLORE_HINTS["all"])
    return f"{focus_prefix}\n\n当前用户任务：{task}"


def load_inputs(inputs_path: str | None) -> dict:
    if not inputs_path:
        return {}
    with open(inputs_path, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="EduAgent 统一入口：接收自然语言任务，自动完成搜索、工作流生成与执行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scripts/run_agent.py --task "设计一个强化学习教案设计与评估工作流"
  python scripts/run_agent.py --task "围绕教师 copilot 自由探索教育创新方向" --focus free
  python scripts/run_agent.py --task "探索 AI 助教在数学课堂中的创新应用并给出落地方案" --focus interaction
  python scripts/run_agent.py --task "调研课堂 XR 与特殊教育辅助技术" --theme "课堂 XR" --theme "特殊教育辅助技术"
  python scripts/run_agent.py --task "设计一个分数运算分层练习生成流程" --skip-search --mode sequential
        """,
    )
    parser.add_argument("--task", "-t", required=True, help="用自然语言描述要完成的教育任务")
    parser.add_argument(
        "--focus",
        "-f",
        choices=list(DEFAULT_EXPLORE_HINTS.keys()),
        default="all",
        help="搜索阶段的预设方向",
    )
    parser.add_argument(
        "--theme",
        action="append",
        dest="themes",
        default=[],
        help="显式指定搜索主题，可重复传入；传入后优先按这些主题检索",
    )
    parser.add_argument("--hint", "-H", default=None, help="自定义搜索提示（默认根据 task 自动构造）")
    parser.add_argument("--feature", type=int, default=None, help="针对搜索结果中的第 N 个功能点生成 workflow")
    parser.add_argument(
        "--mode",
        "-m",
        choices=["auto", "sequential"],
        default="auto",
        help="工作流生成模式：auto 或 sequential",
    )
    parser.add_argument("--skip-search", action="store_true", help="跳过搜索阶段，直接根据任务生成 workflow")
    parser.add_argument("--inputs", "-i", default=None, help="执行阶段输入 JSON；不提供则自动生成默认输入")
    parser.add_argument("--max-steps", type=int, default=5, help="每个子任务最大执行步数")
    parser.add_argument("--no-save-state", action="store_true", help="不保存任务状态快照")
    parser.add_argument("--skip-framework-research", action="store_true", help="跳过官方资料检索阶段")
    args = parser.parse_args()

    search_hint = build_search_hint(args.task, args.focus, args.hint)
    state = EduAgentTaskState(
        task=args.task,
        focus=args.focus,
        explore_hint=search_hint,
        workflow_mode=args.mode,
        feature_index=args.feature,
        max_steps=args.max_steps,
    )

    def persist_state() -> None:
        if not args.no_save_state:
            state.save()

    persist_state()
    llm = build_llm(build_llm_config())

    try:
        if args.skip_framework_research:
            print("⏭ 跳过官方资料检索阶段")
            state.mark_stage_skipped("framework_research", "skipped_by_user")
            persist_state()
        else:
            state.mark_stage_running("framework_research", detail="fetching_official_evoagentx_docs")
            persist_state()
            framework_bundle = run_framework_research(
                task=args.task,
                save=True,
                verbose=True,
                llm=llm,
            )
            state.attach_artifacts(
                framework_notes=framework_bundle["notes"],
                framework_sources=framework_bundle["sources"],
                framework_json_path=str(framework_bundle["json_path"]) if framework_bundle["json_path"] else None,
                framework_md_path=str(framework_bundle["md_path"]) if framework_bundle["md_path"] else None,
            )
            state.mark_stage_completed("framework_research", detail="official_notes_saved")
            persist_state()

        if args.skip_search:
            print("⏭ 跳过搜索阶段，直接进入工作流生成")
            state.mark_stage_skipped("search", "skipped_by_user")
            persist_state()
        else:
            state.mark_stage_running("search", detail="collecting_education_insights")
            persist_state()
            search_bundle = run_search(
                search_hint,
                focus=args.focus,
                custom_themes=args.themes,
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
        workflow_bundle = run_workflow_generation(
            goal=args.task,
            input_path=state.search_md_path,
            feature=args.feature,
            mode=args.mode,
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

        execution_inputs = load_inputs(args.inputs)
        if not execution_inputs:
            execution_inputs = build_default_inputs(workflow_bundle["workflow_graph"], args.task)
        state.execution_inputs = execution_inputs
        persist_state()

        execution_bundle = run_workflow_execution(
            workflow_path=state.workflow_json_path,
            inputs=execution_inputs,
            max_steps=args.max_steps,
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
        print(f"\n❌ EduAgent 统一入口执行失败：{exc}")
        raise

    print("\n" + "=" * 60)
    print("✅ EduAgent 统一任务完成")
    print("=" * 60)
    print(f"任务：{state.task}")
    print(f"官方资料笔记：{state.framework_md_path}")
    print(f"工作流：{state.workflow_json_path}")
    print(f"结果：{state.result_path}")
    if state.state_path:
        print(f"状态快照：{state.state_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(1)
