#!/usr/bin/env python3
"""CLI entrypoint for the migrated exam generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eduagent_exam import ExamGenerationError, ExamGenerationInputError, build_request, generate_exam_artifacts


def load_input_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    json_path = Path(path)
    if not json_path.is_absolute():
        json_path = PROJECT_ROOT / json_path
    if not json_path.exists():
        raise ExamGenerationInputError(f"输入 JSON 文件不存在：{json_path}")
    with open(json_path, encoding="utf-8") as handle:
        return json.load(handle)


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = load_input_json(args.input_json)
    fields = (
        "subject",
        "knowledge_bases",
        "constraint",
        "language",
        "single_choice_num",
        "multiple_choice_num",
        "true_false_num",
        "fill_blank_num",
        "short_answer_num",
        "programming_num",
        "easy_percentage",
        "medium_percentage",
        "hard_percentage",
        "model_type",
    )
    for field in fields:
        value = getattr(args, field)
        if value is not None:
            payload[field] = value

    if args.use_rag is not None:
        payload["use_rag"] = args.use_rag

    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行迁入 eduagent 的试卷生成能力。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scripts/run_exam.py --subject "大模型" --knowledge-bases "强化学习"
  python scripts/run_exam.py --subject "初中数学" --knowledge-bases "一元二次方程" --single-choice-num 5 --short-answer-num 2
  python scripts/run_exam.py --input-json data/test_inputs.json --use-rag
        """,
    )
    parser.add_argument("--subject", default=None, help="学科或课程名称")
    parser.add_argument("--knowledge-bases", dest="knowledge_bases", default=None, help="考查知识点")
    parser.add_argument("--constraint", default=None, help="附加要求")
    parser.add_argument("--language", default=None, help="出题语言，默认 Chinese")
    parser.add_argument("--single-choice-num", dest="single_choice_num", type=int, default=None, help="单选题数量")
    parser.add_argument("--multiple-choice-num", dest="multiple_choice_num", type=int, default=None, help="多选题数量")
    parser.add_argument("--true-false-num", dest="true_false_num", type=int, default=None, help="判断题数量")
    parser.add_argument("--fill-blank-num", dest="fill_blank_num", type=int, default=None, help="填空题数量")
    parser.add_argument("--short-answer-num", dest="short_answer_num", type=int, default=None, help="简答题数量")
    parser.add_argument("--programming-num", dest="programming_num", type=int, default=None, help="编程题数量")
    parser.add_argument("--easy-percentage", dest="easy_percentage", type=int, default=None, help="简单题比例")
    parser.add_argument("--medium-percentage", dest="medium_percentage", type=int, default=None, help="中等题比例")
    parser.add_argument("--hard-percentage", dest="hard_percentage", type=int, default=None, help="困难题比例")
    parser.add_argument("--model-type", dest="model_type", choices=["QWen", "DeepSeek"], default=None, help="模型类型")
    parser.add_argument("--input-json", default=None, help="从 JSON 文件加载输入")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")

    parser.add_argument("--use-rag", dest="use_rag", action="store_true", help="开启 RAG")
    parser.add_argument("--no-use-rag", dest="use_rag", action="store_false", help="关闭 RAG")
    parser.set_defaults(use_rag=None)
    return parser


def print_human_result(result: dict[str, Any]) -> None:
    print("✅ 试卷生成完成")
    print(f"题目 JSON：{result['result_json_path']}")
    print(f"题目 Markdown：{result['result_md_path']}")
    print(f"Metadata：{result['metadata_path']}")
    print(f"题目数量：{result['question_count']}")
    print(f"摘要：{result['preview']}")


def print_error(error: ExamGenerationError, as_json: bool) -> None:
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
        result = generate_exam_artifacts(request)
    except ExamGenerationInputError as exc:
        print_error(exc, args.json)
        return 2
    except ExamGenerationError as exc:
        print_error(exc, args.json)
        return 1
    except Exception as exc:
        print_error(ExamGenerationError(str(exc)), args.json)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
