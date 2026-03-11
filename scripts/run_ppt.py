#!/usr/bin/env python3
"""CLI entrypoint for the migrated PPT generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eduagent_ppt import PPTGenerationError, PPTGenerationInputError, build_request, generate_ppt_artifacts


def load_input_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    json_path = Path(path)
    if not json_path.is_absolute():
        json_path = PROJECT_ROOT / json_path
    if not json_path.exists():
        raise PPTGenerationInputError(f"输入 JSON 文件不存在：{json_path}")
    with open(json_path, encoding="utf-8") as handle:
        return json.load(handle)


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = load_input_json(args.input_json)
    fields = ("course", "units", "lessons", "knowledge_points", "constraint", "page_limit", "model_type", "output_mode")
    for field in fields:
        value = getattr(args, field)
        if value is not None:
            payload[field] = value
    if args.use_rag is not None:
        payload["use_rag"] = args.use_rag
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行迁入 eduagent 的 PPT 生成能力。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scripts/run_ppt.py --course "大模型" --knowledge-points "强化学习"
  python scripts/run_ppt.py --course "高中数学" --lessons "分数加减法" --output-mode md
  python scripts/run_ppt.py --course "Python编程" --units "面向对象" --page-limit 20 --use-rag
        """,
    )
    parser.add_argument("--course", default=None, help="课程名称")
    parser.add_argument("--units", default=None, help="单元列表，可用逗号分隔")
    parser.add_argument("--lessons", default=None, help="课时列表，可用逗号分隔")
    parser.add_argument("--knowledge-points", dest="knowledge_points", default=None, help="知识点列表，可用逗号分隔")
    parser.add_argument("--constraint", default=None, help="附加要求")
    parser.add_argument("--page-limit", dest="page_limit", type=int, default=None, help="页面数量限制")
    parser.add_argument("--model-type", dest="model_type", choices=["QWen", "DeepSeek"], default=None, help="模型类型")
    parser.add_argument("--output-mode", dest="output_mode", choices=["md", "ppt"], default=None, help="输出模式：md 或 ppt")
    parser.add_argument("--input-json", default=None, help="从 JSON 文件加载输入")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")

    parser.add_argument("--use-rag", dest="use_rag", action="store_true", help="开启 RAG")
    parser.add_argument("--no-use-rag", dest="use_rag", action="store_false", help="关闭 RAG")
    parser.set_defaults(use_rag=None)
    return parser


def print_human_result(result: dict[str, Any]) -> None:
    print("✅ PPT 生成完成")
    print(f"Markdown：{result['markdown_path']}")
    if result.get("pptx_path"):
        print(f"PPTX：{result['pptx_path']}")
    print(f"Metadata：{result['metadata_path']}")
    print(f"摘要：{result['preview']}")


def print_error(error: PPTGenerationError, as_json: bool) -> None:
    payload = error.to_payload()
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"❌ {payload['message']}")
        if payload.get("missing_fields"):
            print(f"缺失字段：{', '.join(payload['missing_fields'])}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = build_payload(args)
        request = build_request(payload)
        result = generate_ppt_artifacts(request)
    except PPTGenerationInputError as exc:
        print_error(exc, args.json)
        return 2
    except PPTGenerationError as exc:
        print_error(exc, args.json)
        return 1
    except Exception as exc:
        print_error(PPTGenerationError(str(exc)), args.json)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
