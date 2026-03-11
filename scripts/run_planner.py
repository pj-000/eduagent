#!/usr/bin/env python3
"""Unified planner CLI for EduAgent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eduagent_core import analyze_task, execute_plan


def load_input_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    json_path = Path(path)
    if not json_path.is_absolute():
        json_path = PROJECT_ROOT / json_path
    if not json_path.exists():
        raise FileNotFoundError(f"输入 JSON 文件不存在：{json_path}")
    with open(json_path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("输入 JSON 顶层必须是对象。")
    return data


def _coerce_value(raw_value: str) -> Any:
    text = raw_value.strip()
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def parse_assignments(assignments: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for item in assignments:
        if "=" not in item:
            raise ValueError(f"无效参数赋值：{item}，应使用 key=value 格式。")
        key, raw_value = item.split("=", 1)
        payload[key.strip()] = _coerce_value(raw_value)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="统一规划入口：分析任务并选择 direct capability 或 workflow pipeline。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scripts/run_planner.py --task "帮我生成一份高中数学教案" --set course=高中数学 --set lessons=分数加减法
  python scripts/run_planner.py --task "先调研再生成一份强化学习教案" --set course=大模型 --set units=强化学习基础
  python scripts/run_planner.py --task "探索 AI 助教课堂应用并给出 workflow" --analyze-only --json
        """,
    )
    parser.add_argument("--task", "-t", required=True, help="自然语言任务描述")
    parser.add_argument("--input-json", default=None, help="从 JSON 文件加载输入")
    parser.add_argument("--set", dest="assignments", action="append", default=[], help="追加输入字段，格式 key=value")
    parser.add_argument("--capability", choices=["lesson_plan", "exam", "ppt"], default=None, help="显式指定 direct capability")
    parser.add_argument(
        "--planner-mode",
        choices=["rule", "hybrid", "llm"],
        default="hybrid",
        help="规划模式：rule 仅规则，hybrid 为规则+LLM，llm 强制优先用模型分析",
    )
    parser.add_argument(
        "--planner-model",
        choices=["QWen", "DeepSeek"],
        default="QWen",
        help="LLM planner 使用的模型类型",
    )
    parser.add_argument("--analyze-only", action="store_true", help="只输出任务分析结果，不执行")
    parser.add_argument("--no-fallback", action="store_true", help="关闭失败回退")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    return parser


def print_human(payload: dict[str, Any]) -> None:
    if "task_family" in payload:
        print(f"分析来源：{payload['analysis_source']}")
        print(f"任务类型：{payload['task_family']}")
        print(f"复杂度：{payload['complexity']}")
        print(f"推荐路线：{payload['recommended_route']}")
        print(f"原因：{payload['reason']}")
        return

    if payload["status"] == "error":
        print(f"❌ Planner 执行失败：{payload['message']}")
        return

    result = payload["result"]
    print(f"✅ Planner 执行完成，路线：{payload['selected_route']}")
    if result.get("route") == "workflow":
        print(f"产物：{json.dumps(result.get('artifacts', {}), ensure_ascii=False)}")
    else:
        print(f"产物：{json.dumps(result.get('artifacts', {}), ensure_ascii=False)}")
        if result.get("preview"):
            print(f"摘要：{result['preview']}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    payload = load_input_json(args.input_json)
    payload.update(parse_assignments(args.assignments))

    result = (
        analyze_task(
            task=args.task,
            payload=payload,
            capability=args.capability,
            planner_mode=args.planner_mode,
            planner_model=args.planner_model,
        ).to_dict()
        if args.analyze_only
        else execute_plan(
            task=args.task,
            payload=payload,
            capability=args.capability,
            allow_fallback=not args.no_fallback,
            planner_mode=args.planner_mode,
            planner_model=args.planner_model,
        )
    )

    if args.json or args.analyze_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)
    return 0 if result.get("status", "success") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
