#!/usr/bin/env python3
"""Unified CLI entrypoint for specialized EduAgent capabilities."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eduagent_core import describe_capabilities, dispatch_capability


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
        key = key.strip()
        if not key:
            raise ValueError(f"无效参数赋值：{item}，key 不能为空。")
        payload[key] = _coerce_value(raw_value)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="统一执行教案、试卷、PPT 三类 EduAgent 能力。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scripts/run_capability.py --describe
  python scripts/run_capability.py --capability lesson_plan --set course=高中数学 --set lessons=分数加减法
  python scripts/run_capability.py --task "帮我生成一份强化学习试卷" --set subject=大模型 --set knowledge_bases=强化学习
  python scripts/run_capability.py --capability ppt --input-json data/test_inputs.json --json
        """,
    )
    parser.add_argument("--task", "-t", default=None, help="自然语言任务描述，可用于自动识别能力")
    parser.add_argument(
        "--capability",
        "-c",
        choices=["lesson_plan", "exam", "ppt"],
        default=None,
        help="显式指定能力类型",
    )
    parser.add_argument("--input-json", default=None, help="从 JSON 文件加载统一输入")
    parser.add_argument("--set", dest="assignments", action="append", default=[], help="追加输入字段，格式 key=value")
    parser.add_argument("--describe", action="store_true", help="输出能力 schema")
    parser.add_argument("--json", action="store_true", help="以 JSON 形式输出结果")
    return parser


def print_human_result(payload: dict[str, Any]) -> None:
    if payload["status"] == "error":
        print(f"❌ {payload['capability']} 执行失败")
        print(f"错误类型：{payload['error_type']}")
        print(f"错误信息：{payload['message']}")
        if payload.get("missing_fields"):
            print(f"缺失字段：{', '.join(payload['missing_fields'])}")
        return

    print(f"✅ {payload['capability']} 执行完成")
    print(f"标准化请求：{json.dumps(payload['request'], ensure_ascii=False)}")
    if payload.get("artifacts"):
        print(f"产物：{json.dumps(payload['artifacts'], ensure_ascii=False)}")
    if payload.get("metrics"):
        print(f"指标：{json.dumps(payload['metrics'], ensure_ascii=False)}")
    if payload.get("preview"):
        print(f"摘要：{payload['preview']}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.describe:
            result = describe_capabilities(args.capability)
        else:
            payload = load_input_json(args.input_json)
            payload.update(parse_assignments(args.assignments))
            result = dispatch_capability(task=args.task, payload=payload, capability=args.capability)
    except Exception as exc:
        error_payload = {"status": "error", "message": str(exc)}
        if args.json:
            print(json.dumps(error_payload, ensure_ascii=False, indent=2))
        else:
            print(f"❌ {exc}")
        return 1

    if args.json or args.describe:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human_result(result)

    return 0 if result.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
