#!/usr/bin/env python3
"""EduAgent workflow CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eduagent_core import run_workflow_pipeline
from eduagent_core.workflow_runner import get_default_explore_hints


def load_inputs(inputs_path: str | None) -> dict:
    if not inputs_path:
        return {}
    with open(inputs_path, encoding="utf-8") as handle:
        return json.load(handle)


def build_parser() -> argparse.ArgumentParser:
    default_explore_hints = get_default_explore_hints()
    parser = argparse.ArgumentParser(
        description="EduAgent 统一入口：接收自然语言任务，自动完成搜索、工作流生成与执行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scripts/run_agent.py --task "设计一个强化学习教案设计与评估工作流"
  python scripts/run_agent.py --task "围绕教师 copilot 自由探索教育创新方向" --focus free
  python scripts/run_agent.py --task "探索 AI 助教在数学课堂中的创新应用并给出落地方案" --focus interaction
  python scripts/run_agent.py --task "调研课堂 XR 与特殊教育辅助技术" --theme "课堂 XR" --theme "特殊教育辅助技术"
  python scripts/run_agent.py --task "调研课堂 XR 与特殊教育辅助技术" --search-mode research
  python scripts/run_agent.py --task "设计一个分数运算分层练习生成流程" --skip-search --mode sequential
        """,
    )
    parser.add_argument("--task", "-t", required=True, help="用自然语言描述要完成的教育任务")
    parser.add_argument(
        "--focus",
        "-f",
        choices=list(default_explore_hints.keys()),
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
    parser.add_argument(
        "--search-mode",
        choices=["quick", "research"],
        default="research",
        help="搜索执行模式：research(重型研究，默认) / quick(快速轻量)",
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
    parser.add_argument("--json", action="store_true", help="以 JSON 形式输出结果")
    return parser


def print_human_result(result: dict) -> None:
    if result["status"] == "error":
        print("\n❌ EduAgent 统一入口执行失败")
        print(f"失败阶段：{result.get('failing_stage')}")
        print(f"错误信息：{result['message']}")
        if result.get("artifacts", {}).get("state_path"):
            print(f"状态快照：{result['artifacts']['state_path']}")
        return

    artifacts = result["artifacts"]
    print("\n" + "=" * 60)
    print("✅ EduAgent 统一任务完成")
    print("=" * 60)
    print(f"任务：{result['task']}")
    print(f"官方资料笔记：{artifacts.get('framework_md_path')}")
    print(f"工作流：{artifacts.get('workflow_json_path')}")
    print(f"结果：{artifacts.get('result_path')}")
    if artifacts.get("state_path"):
        print(f"状态快照：{artifacts['state_path']}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = run_workflow_pipeline(
        task=args.task,
        focus=args.focus,
        themes=args.themes,
        search_mode=args.search_mode,
        hint=args.hint,
        feature=args.feature,
        mode=args.mode,
        skip_search=args.skip_search,
        inputs=load_inputs(args.inputs),
        max_steps=args.max_steps,
        no_save_state=args.no_save_state,
        skip_framework_research=args.skip_framework_research,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human_result(result)
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
